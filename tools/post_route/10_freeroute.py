"""10: GND fan-out vias, then Freerouting for the remaining signal nets (routing phase; SPEC 5; 2026-11-05).

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/10_freeroute.py`):

1. GND fan-out (lessons doc: Freerouting doesn't connect a fixed stub to an SMD pad, so GND fan-out is scripted):
   every SMD GND pad not yet touching GND copper from 09 gets a short stub and a via into the bottom GND pour
   (poured by 11). The via spot is searched round the pad (FAN_DIRS directions, FAN_STEP_MM steps): clear of
   every other net's pad, track, via and 09 zone by FAN_CLEAR_MM, its hole clear of every other hole, inside the
   board by FAN_EDGE_MM, and the stub clear too. Shortest stub wins. Seeded order (sorted by reference).
2. Every track and via on the board is locked (09's copper is already), so the Specctra export marks it fixed.
3. Specctra DSN (build/pipwr.dsn), edited before routing:
   - GND and the nets 09 connects completely (DONE_NETS) keep a single pin each in the DSN network: Freerouting
     counts neither a fixed stub ending in an SMD pad nor a plane as a connection and would re-route them; the GND
     pour (11) and the fan-out vias make the GND connections;
   - /BATT keeps only SW1's pin and moves to a DSN class `BattFeed` (BATT_FEED_W_MM, signal current): Freerouting
     joins it to 09's fixed BATT feed via; the other BATT pads are in the 09 `BATT_TOP` pour;
   - the 09 zones (exported as planes, which Freerouting lets other nets cross on a signal layer) become
     keep-outs on their layers; Freerouting items left on DONE_NETS after the import are removed.
4. Freerouting 2.5.0 headless (`-de/-do`, max passes FR_MAX_PASSES, --gui.enabled=false) under FR_TIMEOUT_S;
   the SES is imported; the locked copper must come back unchanged.
5. The ledger (`tools/post_route/10_ledger.json`) lists every item this script added (fan-out and routed), so a
   re-run compares instead of routing again.

Guards: KiCad lock files; check_fixed before and after; 09 applied (its zone names present); no unlocked tracks
before the run; a re-run with the ledger items present prints "already applied"; partial state -> stop.
Backup before saving. Scratch files (DSN, SES, log) are deleted after the import (C: is short of space).
"""
import json
import math
import pathlib
import re
import subprocess
import sys

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import route_lib as rl  # noqa: E402
import toolchain  # noqa: E402

F, B = rl.F, rl.B
NAMESPACE = 'pipwr/10_freeroute'
LEDGER = HERE / '10_ledger.json'
DSN = rl.BUILD / 'pipwr.dsn'
SES = rl.BUILD / 'pipwr.ses'
FR_LOG = rl.BUILD / 'freerouting.log'
ZONES_09 = {'BATT_TOP', 'VOUT_TOP', 'VOUT_BOT', 'P5V_TOP'}

FAN_VIA = (0.6, 0.3)
FAN_STUB_W = 0.4
FAN_CLEAR_MM = 0.25          # other copper (Default class 0.2 + margin)
FAN_CLEAR_POWER_MM = 0.35    # copper of the Power / Switch classes and the 09 zones (0.3 + margin)
FAN_HOLE_MM = 0.3            # hole to hole
FAN_EDGE_MM = 0.4            # via copper to the board edge (rule 0.3 + margin)
FAN_DIRS = 16
FAN_STEP_MM = 0.2
FAN_STEPS = 12
POWER_NETS = {'/BATT', '/VOUT', '/U8_PH', '/+5V1'}
TOUCH_TOL_MM = 0.05

# nets 09 (and the fan-out) connect completely: one pin each in the DSN network, so Freerouting leaves them alone
# (it counts neither a fixed stub ending in an SMD pad nor a plane as a connection); DRC (unconnected 0) is the proof
DONE_NETS = ('GND', '/VOUT', '/+5V1', '/U8_PH', '/U8_BOOT', '/U8_SS', '/U8_COMP', '/U8_CRC', '/U8_FB', '/ACC_IN',
             '/Q1_G')
BATT_FEED_PIN = 'SW1-2'      # BATT keeps this pin only: Freerouting joins it to 09's fixed BATT feed via
BATT_FEED_W_MM = 0.5
BATT_FEED_CLEAR_MM = 0.3
FR_MAX_PASSES = 100
FR_TIMEOUT_S = 600


def gnd_pads_to_fan(board):
    """SMD GND pads with no GND track end or via inside them."""
    gnd = [t for t in board.GetTracks() if t.GetNetname() == 'GND']
    out = []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        for pad in fp.Pads():
            if pad.GetNetname() != 'GND' or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            if fp.GetReference() == 'U8':
                continue                       # pin 4 on the 09 bus; pad 9 has the footprint's vias
            bb = pad.GetBoundingBox()
            bb.Inflate(rl.nm(TOUCH_TOL_MM))
            pts = []
            for t in gnd:
                if t.Type() == pcbnew.PCB_VIA_T:
                    pts.append(t.GetPosition())
                else:
                    pts += [t.GetStart(), t.GetEnd()]
            if any(bb.Contains(p) for p in pts if pad.IsOnLayer(F)):
                continue
            out.append((fp.GetReference(), pad))
    return out


def zone_obstacles(board):
    obs = []
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetZoneName() not in ZONES_09:
            continue
        o = z.Outline()
        for k in range(o.OutlineCount()):
            ring = o.Outline(k)
            pts = [(rl.mm(ring.CPoint(i).x), rl.mm(ring.CPoint(i).y)) for i in range(ring.PointCount())]
            for a, b in zip(pts, pts[1:] + pts[:1]):
                obs.append(rl.Obstacle(z.GetNetname(), {z.GetLayer()}, ('seg', a, b, 0.0)))
            obs.append(('poly', z.GetNetname(), z.GetLayer(), pts))
    return obs


def pip(pts, p):
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def find_fanout(board, pad, obs, polys, holes, edges):
    c = pad.GetPosition()
    cx, cy = rl.mm(c.x), rl.mm(c.y)
    bb = pad.GetBoundingBox()
    hx, hy = rl.mm(bb.GetWidth()) / 2, rl.mm(bb.GetHeight()) / 2
    r_via, r_drill = FAN_VIA[0] / 2, FAN_VIA[1] / 2
    best = None
    for k in range(FAN_DIRS):
        a = 2 * math.pi * k / FAN_DIRS
        ux, uy = math.cos(a), math.sin(a)
        # distance from the centre to the pad's bbox edge along the ray
        t_edge = min(hx / abs(ux) if abs(ux) > 1e-9 else math.inf, hy / abs(uy) if abs(uy) > 1e-9 else math.inf)
        for s in range(FAN_STEPS):
            d = t_edge + r_via + FAN_CLEAR_MM + s * FAN_STEP_MM
            p = (cx + ux * d, cy + uy * d)
            if best is not None and d >= best[0]:
                break
            if not via_ok(p, r_via, r_drill, obs, polys, holes, edges):
                continue
            if not stub_ok((cx, cy), p, obs):
                continue
            best = (d, p)
            break
    return None if best is None else best[1]


def clear_for(o):
    return FAN_CLEAR_POWER_MM if o.net in POWER_NETS else FAN_CLEAR_MM


def via_ok(p, r_via, r_drill, obs, polys, holes, edges):
    for o in obs:
        if o.net == 'GND':
            continue
        if o.dist_pt(p) < r_via + clear_for(o):
            return False
    for net, _layer, pts in polys:
        if pip(pts, p):
            return False
    for hx, hy, hr in holes:
        if math.hypot(p[0] - hx, p[1] - hy) < r_drill + hr + FAN_HOLE_MM:
            return False
    for a, b in edges:
        if rl.seg_dist(p, a, b) < r_via + FAN_EDGE_MM:
            return False
    return True


def stub_ok(a, b, obs):
    half = FAN_STUB_W / 2
    for o in obs:
        if o.net == 'GND' or F not in o.layers:
            continue
        if o.dist_seg(a, b) < half + clear_for(o):
            return False
    return True


def fanout(board):
    obs_all = rl.board_obstacles(board, {})
    zobs = zone_obstacles(board)
    polys = [z[1:] for z in zobs if isinstance(z, tuple)]
    obs = [o for o in obs_all if F in o.layers or B in o.layers] + [z for z in zobs if not isinstance(z, tuple)]
    holes = [o.hole for o in obs_all if o.hole]
    edges = rl.edge_segments(board)
    added = []
    for ref, pad in gnd_pads_to_fan(board):
        p = find_fanout(board, pad, obs, polys, holes, edges)
        if p is None:
            raise SystemExit(f'{ref} pad {pad.GetNumber()}: no fan-out via spot found: stop')
        c = pad.GetPosition()
        a = (rl.mm(c.x), rl.mm(c.y))
        p = (round(p[0], 3), round(p[1], 3))
        v = rl.add_via(board, 'GND', p, *FAN_VIA)
        t = rl.add_track(board, 'GND', F, a, p, FAN_STUB_W)
        added += [v, t]
        r_via = FAN_VIA[0] / 2
        obs.append(rl.Obstacle('GND', {F, B}, ('circle', p[0], p[1], r_via), (p[0], p[1], FAN_VIA[1] / 2)))
        holes.append((p[0], p[1], FAN_VIA[1] / 2))
        print(f'  fan-out {ref}.{pad.GetNumber()}: via at {p}, stub {math.dist(a, p):.2f} mm')
    return added


def adjust_dsn():
    txt = DSN.read_text(encoding='utf-8')
    for netname in DONE_NETS:
        m = re.search(r'\(net ' + re.escape(netname) + r'\s*\(pins ([^)]*)\)', txt)
        if not m:
            raise SystemExit(f'DSN: net {netname} pins not found')
        first = m.group(1).split()[0]
        txt = txt[:m.start(1)] + first + txt[m.end(1):]
    m = re.search(r'\(net /BATT\s*\(pins ([^)]*)\)', txt)
    if not m or BATT_FEED_PIN not in m.group(1).split():
        raise SystemExit(f'DSN: net /BATT without {BATT_FEED_PIN}')
    txt = txt[:m.start(1)] + BATT_FEED_PIN + txt[m.end(1):]
    m = re.search(r'\(class Power ([^(]*)\(', txt)
    if not m or '/BATT' not in m.group(1).split():
        raise SystemExit('DSN: class Power without /BATT')
    txt = txt[:m.start(1)] + m.group(1).replace('/BATT', '', 1) + txt[m.end(1):]
    i = txt.index('(class Power ')
    feed = (f'(class BattFeed /BATT\n      (circuit\n        (use_via "Via[0-1]_600:300_um")\n      )\n'
            f'      (rule\n        (width {BATT_FEED_W_MM * 1e3:.0f})\n        (clearance {BATT_FEED_CLEAR_MM * 1e3:.0f})\n'
            f'      )\n    )\n    ')
    if '"Via[0-1]_600:300_um"' not in txt:
        raise SystemExit('DSN: default via padstack name not found')
    txt = txt[:i] + feed + txt[i:]
    # the zone outlines come out as planes; Freerouting lets other nets through a plane on a signal layer, so
    # each becomes a keep-out on its layer (its own net is complete, or fed from a fixed via: BATT)
    txt, n_planes = re.subn(r'\(plane \S+ \(polygon', '(keepout "" (polygon', txt)
    if n_planes != len(ZONES_09):
        raise SystemExit(f'DSN: {n_planes} planes, want {len(ZONES_09)} (the 09 zones)')
    DSN.write_text(txt, encoding='utf-8', newline='')
    print(f'DSN: {len(DONE_NETS)} nets reduced to one pin ({", ".join(DONE_NETS)}), /BATT in class BattFeed, '
          f'{n_planes} zone planes -> keep-outs')


def run_freerouting():
    tc = toolchain.Toolchain()
    cmd = [str(tc.java), '-jar', str(tc.freerouting_jar), '-de', str(DSN), '-do', str(SES),
           f'--router.autorouter.max_passes={FR_MAX_PASSES}', '--gui.enabled=false']
    with open(FR_LOG, 'w', encoding='utf-8') as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=FR_TIMEOUT_S, check=True)
    for ln in FR_LOG.read_text(encoding='utf-8', errors='replace').splitlines():
        if 'completed' in ln.lower() or 'unrouted' in ln.lower():
            print('  fr:', ln.split('INFO', 1)[-1].strip()[:200])


def canon(key):
    """Item key as a JSON string (tuples and lists alike), for set comparisons with the ledger. Track width and via
    size are left out: 11 widens Freerouting's neck-downs and sets its vias to one size (same items, same places)."""
    k = json.loads(json.dumps(key))
    return json.dumps(k[:-1] if k[0] == 'trk' else k[:4])


def main():
    rl.guard_locks()
    rl.check_fixed()
    board = pcbnew.LoadBoard(str(rl.PCB))
    names = {z.GetZoneName() for z in board.Zones()}
    if not ZONES_09 <= names:
        raise SystemExit('09 not applied (zones missing): stop')
    unlocked = [t for t in board.GetTracks() if not t.IsLocked()]
    if LEDGER.exists():
        want = {canon(k) for k in json.loads(LEDGER.read_text(encoding='utf-8'))['items']}
        have = {canon(rl.track_key(t)) for t in board.GetTracks()}
        if want <= have:
            print(f'already applied: the {len(want)} ledger items are on the board; nothing saved')
            return
        raise SystemExit('ledger exists but its items are not all on the board: stop (restore the backup)')
    if unlocked:
        raise SystemExit(f'{len(unlocked)} unlocked tracks/vias before routing: stop')
    before_text = rl.PCB.read_text(encoding='utf-8')

    added = fanout(board)
    for t in board.GetTracks():
        t.SetLocked(True)
    fixed = {rl.track_key(t) for t in board.GetTracks()}
    rl.BUILD.mkdir(exist_ok=True)
    if not pcbnew.ExportSpecctraDSN(board, str(DSN)):
        raise SystemExit('DSN export failed')
    adjust_dsn()
    run_freerouting()
    if not pcbnew.ImportSpecctraSES(board, str(SES)):
        raise SystemExit('SES import failed')
    after_locked = {rl.track_key(t) for t in board.GetTracks() if t.IsLocked()}
    if after_locked != fixed:
        raise SystemExit(f'locked copper changed by the import ({len(fixed - after_locked)} missing): not saved')
    junk = [t for t in board.GetTracks() if not t.IsLocked() and t.GetNetname() in DONE_NETS]
    for t in junk:                      # Freerouting's fan-out stubs on nets it was told to leave alone
        board.Remove(t)
    print(f'  removed {len(junk)} Freerouting items on DONE_NETS')
    routed = [t for t in board.GetTracks() if not t.IsLocked()]
    bottom = sum(rl.mm(t.GetLength()) for t in routed if t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() == B)
    vias = sum(1 for t in routed if t.Type() == pcbnew.PCB_VIA_T)
    print(f'  routed: {len(routed)} items, {vias} vias, bottom track length {bottom:.1f} mm')
    items = [rl.track_key(t) for t in added] + [rl.track_key(t) for t in routed]
    if '--dry-run' in sys.argv:
        print('dry run: nothing saved')
        return
    rl.backup(rl.PCB)
    rl.save(board, before_text, NAMESPACE)
    b2 = pcbnew.LoadBoard(str(rl.PCB))
    have = {rl.track_key(t) for t in b2.GetTracks()}
    missing = [k for k in items if k not in have]
    if missing:
        raise SystemExit(f'{len(missing)} added items not found after save: ledger not written')
    LEDGER.write_text(json.dumps({'items': [list(k) for k in items]}, indent=0) + '\n', encoding='utf-8')
    for p in (DSN, SES, FR_LOG):
        p.unlink(missing_ok=True)
    rl.check_fixed()
    print(f'saved; ledger {LEDGER.name} ({len(items)} items); scratch files deleted')


if __name__ == '__main__':
    main()
