"""05: bring pi_power_board.kicad_pcb in line with the CD4541B schematic (SPEC 7) and rotate J1/J4/J5 (SPEC 5).

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/05_sync_cd4541.py`):

1. Sync, like "Update PCB from Schematic", from the FROZEN netlist build/placement_netlist_snapshot.xml (44 board
   parts; 2026-11-05 12:58, taken before another agent started adding simulation models to the schematic). The
   schematic is not read or exported:
   - removes the footprints of the parts no longer in the netlist: exactly REMOVED (the LM2903B / 64-part design
     leftovers); MH1-MH4 (board-only, no schematic link) stay untouched;
   - adds the new parts (exactly NEW) from the library, with Path = /sheet-tstamps/symbol-uuid, Sheetname,
     Sheetfile, Value and the symbol fields, staged in a grid left of the board for 06_placement.py;
   - re-loads from the library, at the same position / orientation / side / lock, every part whose footprint,
     value, fields or pad nets differ from the netlist (C22-C24 1206 -> 1210, C8, R8, D6, D7, ...);
   - sets every pad net from the netlist (no-connect pins get KiCad's single-pad `unconnected-(...)` nets) and
     drops the unused old nets;
   - Sim.* fields are ignored (not written, not compared): the coordinator reconciles them after the sim agent.
   Helpers (library load, fields, Path, uuid5 reseed) are 01_update_from_schematic.py's, imported read-only, so
   the result is what 01 would write from the same netlist.
2. Lead decision 2026-11-05 (SPEC 5 "Fixed positions", DECISIONS): J1, J4 and J5 are rotated 180 deg about the
   centre of their pad row, so the wire entries (footprint local +y, Phoenix 1727010 / 1727023 drawing: the pins
   sit 3.6 mm from the wire-entry face; lessons doc) face outward. The set of pad locations stays the same; the
   pin order along the row reverses and the nets follow the pins. Result: J1 entry +x (board right edge), J4 +y
   (bottom edge), J5 -y (top edge). The footprint origin is pad 1, so the origin moves to the old last-pad
   location. tools/fixed_baseline.json is updated for exactly this change by
   `tools/check_fixed.py --accept-lead-change J1,J4,J5` (run after this script).

Why: the board still carried the 64-part LM2903B placement; DRC parity reported the removed parts as extra, the
new ones missing and the changed nets as conflicts. J1/J4/J5 faced their wire entries into the board (J4 into J1).

Guards: stops on KiCad lock files, on a board-only or missing part set other than REMOVED / NEW, on a missing
library footprint, on a netlist pin with no pad, if J2 or MH1-MH4 would move, if a J1/J4/J5 pad would leave the
lead's pad-location set, or if J1/J4/J5 are in neither the lead's orientation nor the rotated one. Idempotent:
on an applied board it prints "already applied" and saves nothing. Backup to pi_power_board-backups/ first.
"""
import datetime
import importlib.util
import math
import pathlib
import shutil
import sys

import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


upd = _load('upd01', '01_update_from_schematic.py')      # helpers only; its main() is not run

STEM = 'pi_power_board'
PCB = ROOT / f'{STEM}.kicad_pcb'
BACKUPS = ROOT / f'{STEM}-backups'
SNAPSHOT = ROOT / 'build' / 'placement_netlist_snapshot.xml'
SNAPSHOT_PARTS = 44
SIM_PREFIX = 'Sim.'
REMOVED = set('C2 C3 C4 C5 C6 C7 C9 C11 C12 C13 C14 C16 C21 C25 C26 D1 D2 DZ1 DZ2 Q2 Q4 '
              'R1 R2 R4 R5 R6 R7 R9 R11 R12 R13 R19 R20 R22 U3 U4'.split())
NEW = set('C29 C30 D7 Q5 Q6 R25 R26 R27 R28 R29 R30 R31 U5'.split())
ROTATE_180 = ('J1', 'J4', 'J5')
UNTOUCHED = ('J2', 'MH1', 'MH2', 'MH3', 'MH4')
# the lead's orientation of each terminal (tools/fixed_baseline.json, 2026-11-04) and the rotated one
LEAD_ANGLE = {'J1': -90.0, 'J4': 180.0, 'J5': 0.0}
HALF_TURN_DEG = 180.0
PAD_TOL_NM = 1000
ANGLE_TOL_DEG = 1e-3
STAGE_X0_MM = 95.0               # staging grid for new parts, left of the board (06 places them)
STAGE_Y0_MM = 66.0
STAGE_PITCH_MM = 8.0
STAGE_COLS = 3


def read_snapshot():
    upd.NETLIST = SNAPSHOT
    comps, pin_net = upd.read_netlist()
    if len(comps) != SNAPSHOT_PARTS:
        raise SystemExit(f'{SNAPSHOT.name}: {len(comps)} parts, expected {SNAPSHOT_PARTS}')
    for c in comps.values():
        c['fields'] = {k: v for k, v in c['fields'].items() if not k.startswith(SIM_PREFIX)}
    return comps, pin_net


def angle_eq(a, b):
    d = (a - b) % 360.0
    return min(d, 360.0 - d) <= ANGLE_TOL_DEG


def pad_set(fp):
    return sorted((p.GetPosition().x, p.GetPosition().y) for p in fp.Pads())


def same_set(a, b):
    return len(a) == len(b) and all(abs(x[0] - y[0]) <= PAD_TOL_NM and abs(x[1] - y[1]) <= PAD_TOL_NM
                                    for x, y in zip(a, b))


def row_centre(fp):
    pts = [p.GetPosition() for p in fp.Pads()]
    return pcbnew.VECTOR2I(sum(p.x for p in pts) // len(pts), sum(p.y for p in pts) // len(pts))


def rotate_terminals(fps):
    """Rotate J1/J4/J5 180 deg about their pad-row centre. Returns the refs rotated."""
    done = []
    for ref in ROTATE_180:
        fp = fps[ref]
        ang = fp.GetOrientationDegrees()
        if angle_eq(ang, LEAD_ANGLE[ref] + HALF_TURN_DEG):
            continue
        if not angle_eq(ang, LEAD_ANGLE[ref]):
            raise SystemExit(f'{ref}: orientation {ang} is neither the lead\'s {LEAD_ANGLE[ref]} nor rotated')
        before = pad_set(fp)
        by_num = {p.GetNumber(): (p.GetPosition().x, p.GetPosition().y) for p in fp.Pads()}
        fp.Rotate(row_centre(fp), pcbnew.EDA_ANGLE(HALF_TURN_DEG, pcbnew.DEGREES_T))
        if not same_set(before, pad_set(fp)):
            raise SystemExit(f'{ref}: the rotation moved a pad off the lead\'s pad locations: not saved')
        n = len(by_num)
        for p in fp.Pads():                     # pin k now sits where pin n+1-k was
            want = by_num[str(n + 1 - int(p.GetNumber()))]
            got = (p.GetPosition().x, p.GetPosition().y)
            if abs(want[0] - got[0]) > PAD_TOL_NM or abs(want[1] - got[1]) > PAD_TOL_NM:
                raise SystemExit(f'{ref}: pad {p.GetNumber()} is not at the old pad {n + 1 - int(p.GetNumber())}')
        done.append(ref)
    return done


def wire_entry(fp):
    """Board direction of the footprint's local +y (the wire-entry face). KiCad orientation t turns local (x, y)
    into board (x cos t + y sin t, -x sin t + y cos t) (y down), so local +y goes to (sin t, cos t)."""
    t = math.radians(fp.GetOrientationDegrees())
    names = {(1, 0): '+x (right edge)', (-1, 0): '-x (left)', (0, 1): '+y (bottom edge)', (0, -1): '-y (top edge)'}
    return names[(round(math.sin(t)), round(math.cos(t)))]


def main():
    locks = sorted(ROOT.glob('~*.lck'))
    if locks:
        raise SystemExit(f'KiCad lock files present ({[p.name for p in locks]}): close KiCad first')
    comps, pin_net = read_snapshot()
    board = pcbnew.LoadBoard(str(PCB))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    if any(r not in fps for r in ROTATE_180 + UNTOUCHED):
        raise SystemExit(f'fixed parts missing: {[r for r in ROTATE_180 + UNTOUCHED if r not in fps]}')
    untouched_before = {r: (fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees(),
                            pad_set(fps[r])) for r in UNTOUCHED}

    extra = {r for r in fps if r not in comps and not upd.UNLINKED_OK.match(r)}
    missing = {r for r in comps if r not in fps}
    if extra and extra != REMOVED:
        raise SystemExit(f'unexpected board-only parts {sorted(extra ^ REMOVED)} (expected exactly REMOVED)')
    if missing and missing != NEW:
        raise SystemExit(f'unexpected missing parts {sorted(missing ^ NEW)} (expected exactly NEW)')
    todo = sorted(r for r in comps if r in fps and not upd.fp_matches(fps[r], comps[r], pin_net))

    removed = []    # removed footprints stay referenced until the save (KiCad 10 SWIG: lessons doc)
    for r in sorted(extra):
        removed.append(fps.pop(r))
        board.Remove(removed[-1])

    nets = {}
    for name in sorted(set(pin_net.values())):
        n = board.FindNet(name)
        if n is None:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
        nets[name] = n

    written, staged = [], 0
    for ref in sorted(missing) + todo:
        comp = comps[ref]
        old = fps.get(ref)
        fp = upd.load_lib_fp(comp['footprint'])
        fp.SetParent(board)
        upd.apply_fields(fp, ref, comp, upd.want_path(comp, old))
        if old is not None:
            if old.IsFlipped():
                raise SystemExit(f'{ref}: bottom-side part: unexpected (everything is top side)')
            fp.SetOrientation(old.GetOrientation())
            fp.SetPosition(old.GetPosition())
            fp.SetLocked(old.IsLocked())
            removed.append(old)
            board.Remove(old)
        else:
            fp.SetPosition(pcbnew.VECTOR2I_MM(STAGE_X0_MM + STAGE_PITCH_MM * (staged % STAGE_COLS),
                                              STAGE_Y0_MM + STAGE_PITCH_MM * (staged // STAGE_COLS)))
            staged += 1
        board.Add(fp)
        fps[ref] = fp
        written.append(ref)

    for ref in sorted(comps):                   # every pad net from the netlist
        fp = fps[ref]
        pads = {}
        for p in fp.Pads():
            pads.setdefault(p.GetNumber(), []).append(p)
        want = {pin: net for (r, pin), net in pin_net.items() if r == ref}
        for pin in want:
            if pin not in pads:
                raise SystemExit(f'{ref}: netlist pin {pin} has no pad in {comps[ref]["footprint"]}')
        for num, plist in pads.items():
            if num == '':                       # unnumbered paste-only pads (Q1 TO-252): no net
                continue
            for p in plist:
                net = want.get(num)
                if net is None:
                    raise SystemExit(f'{ref}: pad {num} not in the netlist')
                if p.GetNetname() != net:
                    p.SetNet(nets[net])

    rotated = rotate_terminals(fps)

    for r in UNTOUCHED:
        f = fps[r]
        now = (f.GetPosition().x, f.GetPosition().y, f.GetOrientationDegrees(), pad_set(f))
        if now[:3] != untouched_before[r][:3] or not same_set(now[3], untouched_before[r][3]):
            raise SystemExit(f'{r} would move: not saved')

    for r in ROTATE_180:
        f = fps[r]
        print(f'{r}: orientation {f.GetOrientationDegrees():g}, origin ({f.GetPosition().x / 1e6:.4f}, '
              f'{f.GetPosition().y / 1e6:.4f}) mm, wire entry {wire_entry(f)}, pins '
              + ', '.join(f'{p.GetNumber()}={p.GetNetname()}@({p.GetPosition().x / 1e6:.3f},'
                          f'{p.GetPosition().y / 1e6:.3f})' for p in sorted(f.Pads(), key=lambda p: p.GetNumber())))

    if not extra and not written and not rotated:
        print('already applied: footprints, fields and pad nets match the snapshot; J1/J4/J5 rotated; '
              'nothing saved')
        return
    board.RemoveUnusedNets(None)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_pcb'
    shutil.copy2(PCB, backup)
    print(f'backup {backup.relative_to(ROOT)}')
    pcbnew.SaveBoard(str(PCB), board)
    text = PCB.read_text(encoding='utf-8')
    PCB.write_text(upd.reseed_uuids(text, set(written)), encoding='utf-8', newline='')
    pcbnew.SaveBoard(str(PCB), pcbnew.LoadBoard(str(PCB)))     # footprint order follows the seeded uuids
    print(f'removed {len(extra)} {sorted(extra)}; added {len(missing)} {sorted(missing)} (staged off-board); '
          f're-loaded {len(todo)} {todo}; rotated {rotated}; {len(nets)} nets')


if __name__ == '__main__':
    main()
