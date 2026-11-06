"""11: GND pours, stitching, review fixes of the Freerouting output, silk (routing phase; SPEC 5; 2026-11-05).

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/11_cleanup.py`;
`--dry-run` saves nothing):

1. Freerouting output review (lessons doc "Review its output"):
   - track widths: every routed track below W_SIG_MM (Freerouting necks down at the U5 / SOT pins) is widened to
     W_SIG_MM, or to the widest of WIDTH_STEPS_MM that keeps CLEAR_MM to every other net (never below the board
     minimum);
   - vias: every routed via gets the signal via size ROUTED_VIA (Freerouting set one 0.6 / 0.4 mm: a 0.1 mm ring);
   - endpoints: every track end within SNAP_TOL_MM of another track end, a via or a pad centre of its net is moved
     onto it exactly (nm); zero-length segments removed;
   - acute angles between two segments of one net and layer meeting at a point: counted and refused (stop);
   - every power-net track and via is 09's (no thin power neck from Freerouting), except SW1's BATT feed at
     BATT_FEED_W_MM (signal current): checked, stop otherwise.
2. GND pours: `GND_BOT` (B.Cu) and `GND_TOP` (F.Cu) over the whole board outline, priority 0 (the 09 power
   pours win), clearance 0.3 mm, min width 0.25 mm, thermal reliefs on THT pads (hand soldering), solid on SMD
   pads and vias, islands removed always.
   J2's inner GND pins 13 and 7 (boxed in by the signal pins) get 0.38 mm ties (J2_GND_TIES).
3. Stitching vias (0.6 / 0.3 mm GND) on a STITCH_PITCH_MM grid wherever both GND fills hold the whole via with
   STITCH_MARGIN_MM to spare and every hole is STITCH_HOLE_MM away; then refill.
4. Silk: a reference on F.Silkscreen that overlaps a pad, a via or another footprint's silk moves to F.Fab
   (06's convention: refs on silk where unambiguous; tools/render_assembly.py draws every reference anyway).
   J1 / J4 / J5 pin labels (board texts) untouched.
5. Everything on the board locked.

Guards: lock files; check_fixed before and after; 10 applied (its ledger); a re-run with the GND zones and the
11 ledger present prints "already applied". Seeded uuids; backup before saving; zones refilled one priority at a
time.
"""
import json
import math
import pathlib
import sys

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import route_lib as rl  # noqa: E402

F, B = rl.F, rl.B
NAMESPACE = 'pipwr/11_cleanup'
LEDGER_10 = HERE / '10_ledger.json'
LEDGER = HERE / '11_ledger.json'
W_SIG_MM = 0.25
WIDTH_STEPS_MM = (0.25, 0.23, 0.2)
CLEAR_MM = 0.2
CLEAR_POWER_MM = 0.3
POWER_NETS = {'/BATT', '/VOUT', '/U8_PH', '/+5V1'}
BATT_FEED_W_MM = 0.5         # = 10's BattFeed class: SW1's BATT feed, signal current
SNAP_TOL_MM = 2e-3
ROUTED_VIA = (0.6, 0.3)
ACUTE_DEG = 90.0
ANGLE_TOL_DEG = 0.5
GND_ZONES = (('GND_BOT', B), ('GND_TOP', F))
GND_CLEARANCE = 0.3
GND_MIN_W = 0.25
STITCH_PITCH_MM = 5.0
STITCH_VIA = (0.6, 0.3)
STITCH_MARGIN_MM = 0.3
STITCH_HOLE_MM = 0.5
STITCH_SAMPLES = 16
SILK_REF_MARGIN_MM = 0.0
# J2's inner GND pins (13, 7) sit inside the pin field: a 0.38 mm top tie each, through the gaps between the
# signal-pin rows, to a GND pin the pour reaches (4, 16) and on to the free area right of the pins
J2_GND_TIES = [(F, (176.84, 72.69), (180.04, 72.69)), (B, (176.84, 72.69), (180.04, 72.69)),
               (F, (175.34, 75.69), (181.6, 75.69))]      # pin 13 on both layers (its bottom spokes alone
#                                                           reach an island); pin 7 on top (USB D shorts below)
W_J2_TIE = 0.38


def narrow_fix(board, obs):
    changed = 0
    for t in board.GetTracks():
        if t.IsLocked() or t.Type() == pcbnew.PCB_VIA_T or rl.mm(t.GetWidth()) >= W_SIG_MM - 1e-6:
            continue
        a = (rl.mm(t.GetStart().x), rl.mm(t.GetStart().y))
        b = (rl.mm(t.GetEnd().x), rl.mm(t.GetEnd().y))
        for w in WIDTH_STEPS_MM:
            ok = True
            for o in obs:
                if o.net == t.GetNetname() or t.GetLayer() not in o.layers:
                    continue
                c = CLEAR_POWER_MM if o.net in POWER_NETS else CLEAR_MM
                if o.dist_seg(a, b) < w / 2 + c - 1e-6:
                    ok = False
                    break
            if ok:
                t.SetWidth(rl.nm(w))
                changed += 1
                break
        else:
            raise SystemExit(f'track {t.GetNetname()} at {a}: no width >= {WIDTH_STEPS_MM[-1]} mm fits: stop')
    return changed


def snap(board):
    """Move track ends within SNAP_TOL_MM of an anchor of their net exactly onto it."""
    tol = rl.nm(SNAP_TOL_MM)
    anchors = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            anchors.setdefault(p.GetNetname(), []).append(p.GetPosition())
    tracks = [t for t in board.GetTracks()]
    for t in tracks:
        if t.Type() == pcbnew.PCB_VIA_T:
            anchors.setdefault(t.GetNetname(), []).append(t.GetPosition())
        else:
            anchors.setdefault(t.GetNetname(), []).extend([t.GetStart(), t.GetEnd()])
    n = 0
    for t in tracks:
        if t.Type() == pcbnew.PCB_VIA_T or t.IsLocked():
            continue
        for getter, setter in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
            p = getter()
            for q in anchors.get(t.GetNetname(), []):
                d = math.hypot(p.x - q.x, p.y - q.y)
                if 0 < d <= tol:
                    setter(pcbnew.VECTOR2I(q.x, q.y))
                    n += 1
                    break
    zero = [t for t in tracks if t.Type() != pcbnew.PCB_VIA_T and t.GetStart() == t.GetEnd()]
    for t in zero:
        board.Remove(t)
    return n, len(zero)


def acute_angles(board):
    ends = {}
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        for p, q in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            ends.setdefault((t.GetNetname(), t.GetLayer(), p.x, p.y), []).append((q.x - p.x, q.y - p.y))
    bad = []
    for (netname, layer, x, y), vs in ends.items():
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                (ax, ay), (bx, by) = vs[i], vs[j]
                la, lb = math.hypot(ax, ay), math.hypot(bx, by)
                if la == 0 or lb == 0:
                    continue
                ang = math.degrees(math.acos(max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))))
                if ang < ACUTE_DEG - ANGLE_TOL_DEG:
                    bad.append((netname, layer, x / 1e6, y / 1e6, round(ang, 1)))
    return bad


def check_power_copper(board):
    """Freerouting may only have routed SW1's BATT feed (BattFeed width) on a power net."""
    for t in board.GetTracks():
        if t.GetNetname() not in POWER_NETS or t.IsLocked():
            continue
        if t.GetNetname() == '/BATT' and (t.Type() == pcbnew.PCB_VIA_T or
                                          abs(rl.mm(t.GetWidth()) - BATT_FEED_W_MM) < 1e-6):
            continue
        raise SystemExit(f'Freerouting copper on power net {t.GetNetname()} (not the BATT feed): stop')


def outline_rects(board):
    poly = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(poly, False)
    return poly


def add_gnd_zone(board, name, layer, outline):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(rl.net(board, 'GND'))
    z.SetZoneName(name)
    o = z.Outline()
    o.RemoveAllContours()
    ring = outline.Outline(0)
    o.NewOutline()
    for i in range(ring.PointCount()):
        pt = ring.CPoint(i)
        o.Append(pt.x, pt.y)
    z.SetAssignedPriority(0)
    z.SetLocalClearance(rl.nm(GND_CLEARANCE))
    z.SetMinThickness(rl.nm(GND_MIN_W))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
    z.SetThermalReliefGap(rl.nm(0.3))
    z.SetThermalReliefSpokeWidth(rl.nm(0.5))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetLocked(True)
    board.Add(z)
    return z


def fill(board):
    board.BuildConnectivity()
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    filler = pcbnew.ZONE_FILLER(board)
    for prio in sorted({z.GetAssignedPriority() for z in zones}, reverse=True):
        level = pcbnew.ZONES()
        for z in zones:
            if z.GetAssignedPriority() == prio:
                level.append(z)
        if not filler.Fill(level):
            raise SystemExit('zone fill failed')


def stitch(board):
    fills = []
    for name, layer in GND_ZONES:
        z = next(z for z in board.Zones() if z.GetZoneName() == name)
        fills.append(z.GetFilledPolysList(layer))
    holes = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetDrillSize().x > 0:
                holes.append((p.GetPosition().x, p.GetPosition().y, p.GetDrillSize().x / 2))
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            holes.append((t.GetPosition().x, t.GetPosition().y, t.GetDrillValue() / 2))
    bb = board.GetBoardEdgesBoundingBox()
    r = rl.nm(STITCH_VIA[0] / 2 + STITCH_MARGIN_MM)
    rd = rl.nm(STITCH_VIA[1] / 2)
    step = rl.nm(STITCH_PITCH_MM)
    added = []
    y = bb.GetTop() + step // 2
    while y < bb.GetBottom():
        x = bb.GetLeft() + step // 2
        while x < bb.GetRight():
            ring = [pcbnew.VECTOR2I(int(x + r * math.cos(2 * math.pi * k / STITCH_SAMPLES)),
                                    int(y + r * math.sin(2 * math.pi * k / STITCH_SAMPLES)))
                    for k in range(STITCH_SAMPLES)] + [pcbnew.VECTOR2I(x, y)]
            if all(f.Contains(p) for f in fills for p in ring) and \
                    all(math.hypot(x - hx, y - hy) >= rd + hr + rl.nm(STITCH_HOLE_MM) for hx, hy, hr in holes):
                v = rl.add_via(board, 'GND', (rl.mm(x), rl.mm(y)), *STITCH_VIA)
                added.append(v)
                holes.append((x, y, rd))
            x += step
        y += step
    return added


def silk_fix(board):
    """References on F.Silkscreen over a pad / via / other silk -> F.Fab."""
    copper = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            copper.append(p.GetBoundingBox())
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            copper.append(t.GetBoundingBox())
    margin = rl.nm(SILK_REF_MARGIN_MM)
    moved = []
    fps = list(board.GetFootprints())
    for fp in fps:
        ref = fp.Reference()
        if ref.GetLayer() != pcbnew.F_SilkS or not ref.IsVisible():
            continue
        bb = ref.GetBoundingBox()
        bb.Inflate(margin)
        hit = any(bb.Intersects(c) for c in copper)
        if not hit:
            for other in fps:
                if other is fp:
                    continue
                silk = [g for g in other.GraphicalItems() if g.GetLayer() == pcbnew.F_SilkS]
                if other.Reference().GetLayer() == pcbnew.F_SilkS and other.Reference().IsVisible():
                    silk.append(other.Reference())
                if any(bb.Intersects(g.GetBoundingBox()) for g in silk):
                    hit = True
                if hit:
                    break
        if hit:
            ref.SetLayer(pcbnew.F_Fab)
            moved.append(fp.GetReference())
    return moved


def main():
    rl.guard_locks()
    rl.check_fixed()
    if not LEDGER_10.exists():
        raise SystemExit('10 not applied (no ledger): stop')
    before_text = rl.PCB.read_text(encoding='utf-8')
    board = pcbnew.LoadBoard(str(rl.PCB))
    names = {z.GetZoneName() for z in board.Zones()}
    if LEDGER.exists() and all(n in names for n, _ in GND_ZONES):
        want = {json.dumps(k) for k in json.loads(LEDGER.read_text(encoding='utf-8'))['vias']}
        have = {json.dumps(rl.track_key(t)) for t in board.GetTracks()}
        if want <= have:
            print(f'already applied: GND zones and the {len(want)} stitching vias present; nothing saved')
            return
        raise SystemExit('11 ledger exists but not all its vias are on the board: stop')
    if any(n in names for n, _ in GND_ZONES):
        raise SystemExit('GND zones present without the 11 ledger: stop')
    check_power_copper(board)

    obs = rl.board_obstacles(board, {})
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        o = z.Outline()
        for k in range(o.OutlineCount()):
            ring = o.Outline(k)
            pts = [(rl.mm(ring.CPoint(i).x), rl.mm(ring.CPoint(i).y)) for i in range(ring.PointCount())]
            for a, b in zip(pts, pts[1:] + pts[:1]):
                obs.append(rl.Obstacle(z.GetNetname(), {z.GetLayer()}, ('seg', a, b, 0.0)))
    widened = narrow_fix(board, obs)
    resized = 0
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T and not t.IsLocked() and                 (t.GetWidth(F), t.GetDrillValue()) != (rl.nm(ROUTED_VIA[0]), rl.nm(ROUTED_VIA[1])):
            if rl.mm(t.GetWidth(F)) > ROUTED_VIA[0] + 1e-6:
                raise SystemExit(f'routed via larger than {ROUTED_VIA}: stop')
            t.SetWidth(rl.nm(ROUTED_VIA[0]))
            t.SetDrill(rl.nm(ROUTED_VIA[1]))
            resized += 1
    snapped, zero = snap(board)
    bad = acute_angles(board)
    if bad:
        raise SystemExit(f'acute angles: {bad[:10]}: stop')
    print(f'  widened {widened} tracks, resized {resized} vias, snapped {snapped} track ends, removed {zero} zero-length segments, '
          '0 acute angles')
    for layer, a, b in J2_GND_TIES:
        rl.add_track(board, 'GND', layer, a, b, W_J2_TIE)
    outline = outline_rects(board)
    for name, layer in GND_ZONES:
        add_gnd_zone(board, name, layer, outline)
    fill(board)
    vias = stitch(board)
    fill(board)
    moved = silk_fix(board)
    for t in board.GetTracks():
        t.SetLocked(True)
    print(f'  GND zones {[n for n, _ in GND_ZONES]}, {len(vias)} stitching vias, refs to F.Fab: {moved}')
    if '--dry-run' in sys.argv:
        print('dry run: nothing saved')
        return
    rl.backup(rl.PCB)
    keys = [list(rl.track_key(v)) for v in vias] + [list(rl.planned_track_key('GND', layer, a, b, W_J2_TIE))
                                                    for layer, a, b in J2_GND_TIES]
    rl.save(board, before_text, NAMESPACE)
    rl.refill()
    LEDGER.write_text(json.dumps({'vias': keys}, indent=0) + '\n', encoding='utf-8')
    rl.check_fixed()
    print('saved, filled')


if __name__ == '__main__':
    main()
