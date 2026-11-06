"""07: placement staff review fixes (placement phase, SPEC 5 "Board" / "Buck layout" / "Timer layout", SPEC 7; 2026-11-05).

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/07_placement_review.py`;
`--dry-run` prints the result and never saves the master):

- D4 Path re-linked to the symbol in the frozen netlist snapshot (`build/placement_netlist_snapshot.xml`).
  05 kept the old D4 footprint because its footprint, value, fields and pad nets matched, but its Path still
  named the old symbol uuid; the snapshot's D4 (restored in the schematic) has a new one. DRC parity falls back
  to the reference, so it didn't report it, but "Update PCB from Schematic" without "re-link by reference"
  would delete D4 and add a new one off-board. Path only: nothing else on D4 changes;
- four parts turned or nudged in place (MOVES): the pad that faces the rest of its net, shorter traces:
  - R30 180 deg: its `VOUT` pad faces the VOUT up-run (right), its `VDD_TMR` pad faces C8 / D7 (left);
  - D4 180 deg: its `SW1_C` pad faces SW1 (left), its `ACC_S` pad faces R8 / D5 (right);
  - R3 180 deg: its `D3_K` pad faces the D3 cathode (up);
  - C18 down by C18_SHIFT_MM: U8-C18 courtyard gap from just above the 0.5 mm minimum to >= 1.0 mm (hand
    assembly), the BOOT trace a little longer (SLVSCD5D 10.1 allows it: the BOOT cap is not in the hot loop);
- the turned parts keep their reference text where 06 put it (absolute position and angle), so no label
  ends up next to a neighbour.

Why: placement staff review 2026-11-05 (DECISIONS "Placement staff review"). The rest of 06's placement was
checked and kept (buck, power corner, timer, TVS2 by D5: DECISIONS).

Guards: stops on KiCad lock files; on any MOVES part not at its 06 position or its 07 target; on a D4 Path other
than the old or the snapshot one; if the snapshot's D4 uuid is not SNAPSHOT_D4_UUID; if any other footprint
(position, orientation, side, Path) or the fixed parts change; if a moved part's courtyard comes closer than
MIN_GAP_MM to another courtyard. Idempotent: a re-run on the applied board prints "already applied" and saves
nothing. Backup to pi_power_board-backups/ before saving. 06 is history after this (a re-run would undo it).
"""
import datetime
import math
import pathlib
import shutil
import sys
import xml.etree.ElementTree as ET

import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[2]
STEM = 'pi_power_board'
PCB = ROOT / f'{STEM}.kicad_pcb'
SNAPSHOT = ROOT / 'build' / 'placement_netlist_snapshot.xml'
BACKUPS = ROOT / f'{STEM}-backups'

FIXED = ('J1', 'J2', 'J4', 'J5', 'MH1', 'MH2', 'MH3', 'MH4')
C18_SHIFT_MM = 0.5
# ref: ((x, y, rot) as 06 placed it, (x, y, rot) target) mm / deg
MOVES = {
    'R30': ((148.0, 85.6, 0), (148.0, 85.6, 180)),
    'D4': ((134.3, 84.0, 0), (134.3, 84.0, 180)),
    'R3': ((129.6, 85.6, 90), (129.6, 85.6, 270)),
    'C18': ((156.1, 74.0, 0), (156.1, 74.0 + C18_SHIFT_MM, 0)),
}
D4_OLD_PATH = '/89f5635d-23da-405a-a0a1-1d51f366ea60'
SNAPSHOT_D4_UUID = '0df2549a-6a52-54d0-b791-da5148488ab2'
MIN_GAP_MM = 0.5
POS_TOL_NM = 1000
EPS_MM = 1e-6


def mm(v):
    return pcbnew.FromMM(v)


def norm(deg):
    return round(deg) % 360


def state(fp):
    p = fp.GetPosition()
    return (p.x, p.y, norm(fp.GetOrientationDegrees()), fp.IsFlipped(), fp.GetPath().AsString())


def at(fp, xyr):
    p = fp.GetPosition()
    return (abs(p.x - mm(xyr[0])) <= POS_TOL_NM and abs(p.y - mm(xyr[1])) <= POS_TOL_NM
            and norm(fp.GetOrientationDegrees()) == norm(xyr[2]))


def crt_box(fp):
    c = fp.GetCourtyard(pcbnew.F_CrtYd)
    b = c.BBox() if c.OutlineCount() else fp.GetBoundingBox(False)
    return (b.GetLeft() / 1e6, b.GetTop() / 1e6, b.GetRight() / 1e6, b.GetBottom() / 1e6)


def gap(a, b):
    dx = max(b[0] - a[2], a[0] - b[2])
    dy = max(b[1] - a[3], a[1] - b[3])
    if dx < 0 and dy < 0:
        return max(dx, dy)
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def snapshot_d4_path():
    root = ET.parse(SNAPSHOT).getroot()
    for c in root.find('components'):
        if c.get('ref') == 'D4':
            sheet = c.find('sheetpath').get('tstamps')
            uuids = c.findtext('tstamps').split()
            if uuids != [SNAPSHOT_D4_UUID]:
                raise SystemExit(f'snapshot D4 uuid {uuids} is not {SNAPSHOT_D4_UUID}: stop')
            return sheet + uuids[0]
    raise SystemExit('D4 not in the snapshot: stop')


def main():
    locks = sorted(ROOT.glob('~*.lck'))
    if locks:
        raise SystemExit(f'KiCad lock files present ({[p.name for p in locks]}): close KiCad first')
    want_d4 = snapshot_d4_path()
    board = pcbnew.LoadBoard(str(PCB))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    before = {r: state(f) for r, f in fps.items()}

    todo = []
    for ref, (old, new) in MOVES.items():
        fp = fps[ref]
        if at(fp, new):
            continue
        if not at(fp, old):
            raise SystemExit(f'{ref} is neither at its 06 position {old} nor at the 07 target {new}: stop')
        todo.append(ref)
    d4_path = fps['D4'].GetPath().AsString()
    if d4_path not in (D4_OLD_PATH, want_d4):
        raise SystemExit(f'D4 Path {d4_path}: neither the old nor the snapshot one: stop')

    for ref in todo:
        fp = fps[ref]
        t = fp.Reference()
        ref_pos, ref_ang = t.GetPosition(), t.GetTextAngleDegrees()
        _old, (x, y, r) = MOVES[ref]
        fp.SetOrientationDegrees(r)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        if norm(_old[2]) != norm(r):            # turned in place: the reference stays where 06 put it
            t.SetPosition(ref_pos)
            t.SetTextAngleDegrees(ref_ang)
        print(f'  {ref}: {_old} -> {(x, y, r)}')
    path_changed = d4_path != want_d4
    if path_changed:
        fps['D4'].SetPath(pcbnew.KIID_PATH(want_d4))
        print(f'  D4 Path {d4_path} -> {want_d4}')

    after = {r: state(f) for r, f in fps.items()}
    for r in fps:
        if r in MOVES or r == 'D4':
            continue
        if before[r] != after[r]:
            raise SystemExit(f'{r} changed unexpectedly: not saved')
    if any(after[r][3] for r in MOVES) or any(after[r][4] != before[r][4] for r in MOVES if r != 'D4'):
        raise SystemExit('a moved part is on the bottom side or changed its Path: not saved')
    boxes = {r: crt_box(f) for r, f in fps.items()}
    for ref in MOVES:
        g = min(gap(boxes[ref], boxes[q]) for q in fps if q != ref)
        print(f'  {ref}: smallest courtyard gap {g:.2f} mm')
        if g < MIN_GAP_MM - EPS_MM:
            raise SystemExit(f'{ref}: courtyard gap {g:.2f} mm below {MIN_GAP_MM} mm: not saved')
    if any(before[r][:4] != after[r][:4] for r in FIXED):
        raise SystemExit('a fixed footprint moved: not saved')

    if not todo and not path_changed:
        print('already applied: MOVES at their targets, D4 Path = snapshot; nothing saved')
        return
    if '--dry-run' in sys.argv:
        print(f'dry run: {len(todo)} parts would move, D4 Path {"would change" if path_changed else "ok"}; '
              'master not saved')
        return
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_pcb'
    shutil.copy2(PCB, backup)
    print(f'backup {backup.relative_to(ROOT)}')
    pcbnew.SaveBoard(str(PCB), board)
    print(f'saved: {len(todo)} parts moved, D4 Path {"re-linked" if path_changed else "unchanged"}')


if __name__ == '__main__':
    main()
