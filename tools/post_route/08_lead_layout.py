"""08: adopt the project lead's layout tweaks (placement, SPEC 5 "Board" / "Buck layout" / "Timer layout"; 2026-11-05).

What (KiCad python, under timeout, from the project root):

    python.exe -I tools/post_route/08_lead_layout.py --snapshot   once: lead copy -> LEAD_JSON (refuses to overwrite)
    python.exe -I tools/post_route/08_lead_layout.py [--dry-run]  apply LEAD_JSON + ADJUST to the master

1. The lead copied the project to `C:\\git-personal\\pi-car-power-supply - Copy` and moved 32 of the 48 footprints in
   that board (same refs, footprints, fields, nets and paths as the master). `--snapshot` writes every footprint's
   position, orientation, side, reference / value text (absolute position, angle, layer, visibility), footprint id,
   Path and pad nets into `tools/post_route/lead_layout_2026-11-05.json` (committed with the repo: the copy folder
   may be deleted). Applying it moves the master's footprints by reference.
2. J2 (-0.635 mm x) and J5 (-2.54 mm x, +0.038 mm y) are lead-fixed parts the lead moved: an intended lead change.
   The board is saved with them moved; the baseline then changes only through the recorded, guarded
   `tools/check_fixed.py --accept-lead-change J2,J5` (pure translation by those exact vectors). J5's board-level
   pin labels (06's `ACC_N` / `GND` silk texts above J5) move with J5.
3. ADJUST: the lead said "don't take them as gospel: make sure it'll still work". Checked against the hand-solder
   gap rule (>= 0.5 mm courtyard to courtyard), the TPS54336A layout guide (SLVSCD5D 10.1 / fig. 55) and the
   5 A power paths (SPEC 4, 5); six parts moved from the lead's spot, everything else kept exactly:
   - R16 (VSENSE top resistor) to the quiet side of U8, next to R17: the lead's spot put the high-impedance
     `U8_FB` node next to C18's `U8_PH` pad (0.75 mm) and ran it ~15 mm round U8; fig. 55 puts the feedback
     resistors at the VSENSE pin side and routes the VOUT sense line round the outside;
   - D3 + R3 (LED) from between R16 and L1 (0.40 / 0.47 mm gaps, below the 0.5 mm rule) to the free area below
     the compensation parts, still on top and in the open (visible): the only top channel for the `VOUT` run from
     Q1 to the buck input (C15 / C17) is where they sat;
   - R15 (Q1 gate divider) from the strip between the `BATT` run and D5 to above Q5 (its `DRV` pad next to Q5's
     drain): that strip is the `VOUT` run's channel past the `BATT` feed of Q1 (Q1's source pin is above its tab);
   - Q5 +0.5 mm x: Q5-R30 gap 0.30 mm (below 0.5 mm);
   - C19 -0.1 mm x: C19-R18 gap 0.49 mm (below 0.5 mm).
   SW1 (top-actuated slide switch, Nidec CAS-120A: "top setting"), TVS2 next to J1, C30 at Q1 G-S, U5 and its RC
   parts are kept where the lead put them (DECISIONS 2026-11-05 "Lead layout adopted").

Guards: KiCad lock files; LEAD_JSON's ref set = the master's, and per ref the footprint id, Path and pad nets equal
(positions only differ); the J5 pin labels found once; fixed parts other than J2 / J5 unchanged; J2 / J5 exactly the recorded shift; each ADJUST part's pads in the
intended order; every courtyard gap of a moved part >= MIN_GAP_MM. Idempotent: a re-run on the applied board
prints "already applied" and saves nothing. Backup to pi_power_board-backups/ before saving.
"""
import datetime
import json
import math
import pathlib
import shutil
import sys

import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[2]
STEM = 'pi_power_board'
PCB = ROOT / f'{STEM}.kicad_pcb'
LEAD_PCB = ROOT.parent / 'pi-car-power-supply - Copy' / f'{STEM}.kicad_pcb'
LEAD_JSON = pathlib.Path(__file__).resolve().parent / 'lead_layout_2026-11-05.json'
BACKUPS = ROOT / f'{STEM}-backups'

FIXED = ('J1', 'J2', 'J4', 'J5', 'MH1', 'MH2', 'MH3', 'MH4')
LEAD_MOVED_FIXED = {'J2': (-635_000, 0), 'J5': (-2_540_000, 38_000)}    # nm, = check_fixed LEAD_SHIFTS_NM
J5_LABELS = ('ACC_N', 'GND')        # 06's silk pin labels above J5 (board texts), moved with J5
J5_LABEL_BOX_MM = (135.0, 65.0, 146.0, 68.5)       # where 06 put them (x0, y0, x1, y1)
MIN_GAP_MM = 0.5
POS_TOL_NM = 1000
EPS_MM = 1e-6
# ref: (x mm, y mm, orientation deg, (pad that must be left / top of the other, axis)) - the lead's spot is in LEAD_JSON
ADJUST = {
    'R16': (142.0, 80.486, -90.0, ('1', '2', 'y')),     # +5V1 pad above the U8_FB pad (FB level with R17's)
    'D3': (149.2, 85.0, 0.0, ('1', '2', 'x')),          # cathode left (to R3), VOUT right (to the VOUT run)
    'R3': (143.6, 85.0, 180.0, ('2', '1', 'x')),        # GND left, D3_K right (to D3)
    'R15': (153.7, 88.5, -90.0, ('1', '2', 'y')),       # Q1_G above, DRV below (to Q5's drain)
    'Q5': (154.17, 94.361, 90.0, None),
    'C19': (145.639, 75.152, -90.0, None),
}


def nm(v):
    return int(round(v * 1e6))


def norm(deg):
    return round(deg, 3) % 360.0


def field_rec(t):
    p = t.GetPosition()
    return {'pos': [p.x, p.y], 'angle': t.GetTextAngleDegrees(), 'layer': t.GetLayerName(), 'visible': t.IsVisible()}


def fp_rec(f):
    p = f.GetPosition()
    return {'pos': [p.x, p.y], 'angle': f.GetOrientationDegrees(), 'flipped': f.IsFlipped(),
            'fpid': f.GetFPIDAsString(), 'path': f.GetPath().AsString(),
            'nets': sorted([pd.GetNumber(), pd.GetNetname()] for pd in f.Pads()),
            'ref': field_rec(f.Reference()), 'value': field_rec(f.Value())}


def snapshot():
    if LEAD_JSON.exists():
        raise SystemExit(f'{LEAD_JSON.name} exists: the lead snapshot is taken once and never overwritten')
    board = pcbnew.LoadBoard(str(LEAD_PCB))
    data = {'source': str(LEAD_PCB), 'date': '2026-11-05',
            'footprints': {f.GetReference(): fp_rec(f) for f in board.GetFootprints()}}
    LEAD_JSON.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'snapshot written: {LEAD_JSON.name} ({len(data["footprints"])} footprints from {LEAD_PCB})')


def crt_poly(f):
    c = f.GetCourtyard(pcbnew.F_CrtYd)
    if not c.OutlineCount():
        raise SystemExit(f'{f.GetReference()}: no courtyard')
    return c


def gap_mm(a, b):
    pa, pb = crt_poly(a), crt_poly(b)
    if pa.Collide(pb):
        return 0.0
    oa, ob = pa.Outline(0), pb.Outline(0)
    d = min(min(ob.Distance(oa.CPoint(k), True) for k in range(oa.PointCount())),
            min(oa.Distance(ob.CPoint(k), True) for k in range(ob.PointCount())))
    return d / 1e6


def at_xyr(f, x, y, r):
    p = f.GetPosition()
    return abs(p.x - x) <= POS_TOL_NM and abs(p.y - y) <= POS_TOL_NM and \
        min((norm(f.GetOrientationDegrees()) - norm(r)) % 360, (norm(r) - norm(f.GetOrientationDegrees())) % 360) < 1e-3


def set_field(t, rec):
    t.SetPosition(pcbnew.VECTOR2I(*rec['pos']))
    t.SetTextAngleDegrees(rec['angle'])


def target(ref, lead):
    """(x nm, y nm, deg) the master should end at."""
    if ref in ADJUST:
        x, y, r, _ = ADJUST[ref]
        return nm(x), nm(y), r
    rec = lead[ref]
    return rec['pos'][0], rec['pos'][1], rec['angle']


def j5_labels(board):
    x0, y0, x1, y1 = (nm(v) for v in J5_LABEL_BOX_MM)
    out = []
    for d in board.GetDrawings():
        if d.GetClass() == 'PCB_TEXT' and d.GetLayer() == pcbnew.F_SilkS and d.GetText() in J5_LABELS:
            p = d.GetPosition()
            if x0 <= p.x <= x1 and y0 <= p.y <= y1:
                out.append(d)
    if sorted(d.GetText() for d in out) != sorted(J5_LABELS):
        raise SystemExit(f'J5 pin labels: found {[d.GetText() for d in out]}, want {J5_LABELS}: stop')
    return out


def main():
    if '--snapshot' in sys.argv:
        snapshot()
        return
    locks = sorted(ROOT.glob('~*.lck'))
    if locks:
        raise SystemExit(f'KiCad lock files present ({[p.name for p in locks]}): close KiCad first')
    lead = json.loads(LEAD_JSON.read_text(encoding='utf-8'))['footprints']
    board = pcbnew.LoadBoard(str(PCB))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    if set(fps) != set(lead):
        raise SystemExit(f'ref sets differ: {sorted(set(fps) ^ set(lead))}: stop')
    for ref, f in fps.items():
        cur = fp_rec(f)
        for k in ('fpid', 'path', 'nets', 'flipped'):
            if cur[k] != lead[ref][k]:
                raise SystemExit(f'{ref}: {k} differs from the lead copy ({cur[k]} vs {lead[ref][k]}): stop')

    # pre-08 positions: every footprint the lead did not move is already at the lead's position
    todo = []
    for ref, f in fps.items():
        x, y, r = target(ref, lead)
        if at_xyr(f, x, y, r):
            continue
        todo.append(ref)
    if not todo:
        print('already applied: every footprint at its lead / ADJUST position; nothing saved')
        return

    labels = j5_labels(board)
    j5_before = fps['J5'].GetPosition()
    fixed_before = {r: (fps[r].GetPosition().x, fps[r].GetPosition().y, norm(fps[r].GetOrientationDegrees()))
                    for r in FIXED}
    for ref in sorted(todo):
        f = fps[ref]
        rec = lead[ref]
        f.SetOrientationDegrees(rec['angle'])
        f.SetPosition(pcbnew.VECTOR2I(*rec['pos']))
        set_field(f.Reference(), rec['ref'])
        set_field(f.Value(), rec['value'])
        if ref in ADJUST:
            x, y, r, _ = ADJUST[ref]
            # move from the lead's spot: fields keep their placement relative to the part
            f.SetOrientationDegrees(r)
            f.SetPosition(pcbnew.VECTOR2I(nm(x), nm(y)))
        print(f'  {ref}: -> ({f.GetPosition().x / 1e6:.3f}, {f.GetPosition().y / 1e6:.3f}, '
              f'{f.GetOrientationDegrees():.0f}){"  (ADJUST)" if ref in ADJUST else ""}')
    d5 = fps['J5'].GetPosition() - j5_before
    for t in labels:
        t.Move(d5)

    # guards
    for r in FIXED:
        p = fps[r].GetPosition()
        dx, dy = p.x - fixed_before[r][0], p.y - fixed_before[r][1]
        want = LEAD_MOVED_FIXED.get(r, (0, 0))
        moved_now = r in todo
        if norm(fps[r].GetOrientationDegrees()) != fixed_before[r][2]:
            raise SystemExit(f'{r}: orientation changed: not saved')
        if moved_now and (abs(dx - want[0]) > POS_TOL_NM or abs(dy - want[1]) > POS_TOL_NM):
            raise SystemExit(f'{r}: moved by ({dx}, {dy}) nm, not the recorded {want}: not saved')
        if not moved_now and r not in LEAD_MOVED_FIXED and (dx or dy):
            raise SystemExit(f'{r}: fixed part moved: not saved')
    for ref, (_x, _y, _r, order) in ADJUST.items():
        if order is None:
            continue
        a, b, axis = order
        pads = {p.GetNumber(): p.GetPosition() for p in fps[ref].Pads()}
        lo, hi = (pads[a].x, pads[b].x) if axis == 'x' else (pads[a].y, pads[b].y)
        if not lo < hi:
            raise SystemExit(f'{ref}: pad {a} not {"left of" if axis == "x" else "above"} pad {b}: not saved')
    worst = math.inf
    for ref in todo:
        if ref.startswith(('J', 'MH')):
            continue
        g = min(gap_mm(fps[ref], fps[q]) for q in fps if q != ref)
        worst = min(worst, g)
        if g < MIN_GAP_MM - EPS_MM:
            near = min((q for q in fps if q != ref), key=lambda q: gap_mm(fps[ref], fps[q]))
            raise SystemExit(f'{ref}: courtyard gap {g:.2f} mm to {near} below {MIN_GAP_MM} mm: not saved')
    print(f'  {len(todo)} footprints moved; smallest courtyard gap of a moved part {worst:.2f} mm; '
          f'J5 labels moved by ({d5.x / 1e6:.3f}, {d5.y / 1e6:.3f}) mm')
    if '--dry-run' in sys.argv:
        print('dry run: master not saved')
        return
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    shutil.copy2(PCB, BACKUPS / f'{STEM}_{stamp}.kicad_pcb')
    print(f'backup {STEM}-backups/{STEM}_{stamp}.kicad_pcb')
    pcbnew.SaveBoard(str(PCB), board)
    print('saved; now: tools/check_fixed.py --accept-lead-change J2,J5')


if __name__ == '__main__':
    main()
