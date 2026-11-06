"""Post-route edit 16 (2026-11-06, U8 datasheet review): buck TPS54336A values and layout per SLVSCD5D 10.1.

Run with KiCad's python from the project root (KiCad must not have the board open):

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" -I tools/post_route/16_buck_layout.py [--dry-run] [--root DIR]

--root DIR works on DIR/pi_power_board.kicad_pcb (a scratch copy with the project files); default: the master.

What and why (SPEC 4 "Buck U8", SPEC 5 "Buck layout", SPEC 7; DECISIONS 2026-11-06 rows; reports/ic_review.md):
- Fields from the schematic netlist (tools/post_sch/16): L1 SRP1038A-150M, R16 73.2k, R17 13.7k, R18 7.32k (Value and
  every symbol field); C31 (C_1206, second 10 uF input capacitor) and C32 (C_1210, fourth 47 uF output capacitor)
  added from the library with Path / Sheetname / Sheetfile / fields / pad nets, uuid5 uuids.
- Power block: U8, C17, C15 and their local copper (PH vias and stubs, VIN / GND links, the C15 GND fan-out via)
  moved as one rigid block by BLOCK_MOVE, from the top edge to below J5. The hot loop geometry (fig. 55) is
  unchanged; the left side of U8 is now free of J5.
- FB: R16 / R17 above U8 pin 5 (U8_FB node 5.5 mm of trace, was 18.6 mm); the +5V1 sense line from C24 along the top
  edge now ends at R16 pin 1 (the long run is the low-impedance VOUT sense, 10.1).
- COMP / SS: R18 at pin 6, C20 below it, C19 at pin 8, all F.Cu on the side away from U8_PH (COMP ran on B.Cu
  1.37 mm from PH).
- Analog ground (10.1): R17, C19 and C20 return by separate F.Cu traces to the PowerPAD (R17 at the top end of pad 9,
  C19 + C20 joined at its bottom end: two landing points on the one pad, no loop); rule area AGND_KEEPOUT (F.Cu, no zone fill only) keeps the GND pour off them.
- C18 below C17 (BOOT from pin 1; PH by a B.Cu branch and a via at its PH pad). C31 below C15 on the VOUT pour, GND by
  two vias. L1 moved right by L1_MOVE (C15 courtyard gap). C32 left of C22 on the Cout GND bus.
- PH: B.Cu 1.5 mm trace from the block's PH via to L1's via row (shorter than before); L1's vias / stubs follow L1.
- Zones: VOUT_TOP re-drawn around the moved block (top edge just below the PH via row, the D3 / C18 / C31 area),
  P5V_TOP extended left over C32. Refill (route_lib.refill, a fresh load, one priority level at a time).
- Old copper of U8_FB / U8_COMP / U8_CRC / U8_SS / U8_BOOT, the old C18 PH branch, the old PH B.Cu run, the old
  fan-out vias of C19 / C20 / R17, one stitching via under C20 and one under C32, the VOUT stub where C18 now sits,
  and the old +5V1 sense drop at x 142 are deleted. Everything else is untouched; J1 / J2 / J4 / J5 / MH1-4, the
  outline and the lead's rule areas are not touched (tools/check_fixed.py).

Guards: every listed footprint at its old place (apply) or at its target (then every target is checked and the
script prints "already applied"); every copper item to edit found exactly once (net, layer, ends within 1 um);
zone outlines equal to the recorded old ones. Backup first. Footprints changed: references to F.Fab (the assembly
drawing carries them), U8's Value and D3's reference (over C18's PH pad mask) to F.Fab.
"""
import importlib.util
import pathlib
import shutil
import sys
import datetime

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(HERE))
import route_lib  # noqa: E402


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


upd = _load('upd01', '01_update_from_schematic.py')      # helpers only; its main() is not run

STEM = 'pi_power_board'
TOL_NM = 1000
MM = pcbnew.FromMM
BLOCK = ('U8', 'C17', 'C15')
BLOCK_MOVE = (-1.3, 9.205)
L1_MOVE = (1.0, 0.0)
FIELD_REFS = ('L1', 'R16', 'R17', 'R18')
NEW_REFS = ('C31', 'C32')
# ref: (old x, y, rot) -> (new x, y, rot); block and L1 targets follow from the moves
OLD = {'U8': (148.919, 69.795, 180.0), 'C17': (155.419, 69.155, 90.0), 'C15': (158.219, 69.245, 90.0),
       'L1': (164.719, 78.105, 0.0), 'R16': (142.0, 80.486, -90.0), 'R17': (145.866, 80.486, 90.0),
       'R18': (148.152, 75.152, -90.0), 'C19': (145.639, 75.152, -90.0), 'C20': (149.019, 80.545, 90.0),
       'C18': (150.946, 75.152, 90.0)}
NEW = {'R16': (144.2, 73.8, -90.0), 'R17': (146.75, 73.8, -90.0), 'R18': (140.95, 77.25, 180.0),
       'C20': (138.65, 80.72, -90.0), 'C19': (141.25, 81.0, -90.0), 'C18': (153.6, 82.8, -90.0),
       'C31': (156.919, 84.05, 90.0), 'C32': (157.98, 69.295, 90.0)}
for _r in BLOCK:
    NEW[_r] = (OLD[_r][0] + BLOCK_MOVE[0], OLD[_r][1] + BLOCK_MOVE[1], OLD[_r][2])
NEW['L1'] = (OLD['L1'][0] + L1_MOVE[0], OLD['L1'][1] + L1_MOVE[1], OLD['L1'][2])

F, B = 'F.Cu', 'B.Cu'
# copper: ('seg', net, layer, x1, y1, x2, y2) / ('via', net, x, y)
DELETE = [
    ('seg', '/U8_FB', F, 143.6, 81.49, 145.6, 81.49), ('seg', '/U8_FB', F, 145.4, 67.89, 143.6, 67.89),
    ('seg', '/U8_FB', F, 143.6, 81.49, 142.4, 81.49), ('seg', '/U8_FB', F, 143.6, 67.89, 143.6, 81.49),
    ('seg', '/U8_COMP', F, 144.6, 69.16, 145.4, 69.16), ('via', '/U8_COMP', 144.6, 69.16),
    ('via', '/U8_COMP', 148.15, 73.4), ('seg', '/U8_COMP', B, 144.6, 69.16, 144.6, 73.4),
    ('seg', '/U8_COMP', B, 144.6, 73.4, 148.15, 73.4),
    ('seg', '/U8_CRC', F, 147.55, 77.3, 147.55, 81.6), ('seg', '/U8_CRC', F, 148.0, 76.5, 147.55, 77.3),
    ('seg', '/U8_CRC', F, 147.55, 81.6, 148.6, 81.6),
    ('seg', '/U8_SS', F, 145.5, 71.7, 145.6, 73.9),
    ('seg', '/U8_BOOT', F, 152.35, 76.2, 151.3, 76.2), ('seg', '/U8_BOOT', F, 152.35, 71.7, 152.35, 76.2),
    ('seg', '/U8_PH', F, 151.4, 73.3, 151.0, 73.9), ('via', '/U8_PH', 151.4, 73.3),
    ('seg', '/U8_PH', B, 153.45, 69.16, 152.3, 72.9), ('seg', '/U8_PH', B, 152.3, 72.9, 151.4, 73.3),
    ('seg', '/U8_PH', B, 154.3, 69.16, 158.4, 75.6),
    ('seg', 'GND', F, 145.639, 76.189, 145.639, 77.327), ('via', 'GND', 145.639, 77.327),
    ('seg', 'GND', F, 149.019, 79.507, 149.019, 78.37), ('via', 'GND', 149.019, 78.37),
    ('seg', 'GND', F, 145.866, 79.486, 145.866, 78.336), ('via', 'GND', 145.866, 78.336),
    ('via', 'GND', 139.475, 80.895), ('via', 'GND', 156.73, 67.75),
    ('seg', '/VOUT', F, 151.0, 84.5, 153.6, 84.3),
    ('seg', '/+5V1', F, 142.0, 66.65, 142.0, 79.3),
]
MOVE_BLOCK_ITEMS = [
    ('seg', '/U8_PH', F, 152.5, 69.16, 153.45, 69.16), ('seg', '/U8_PH', F, 153.45, 69.16, 154.3, 69.16),
    ('seg', '/U8_PH', B, 153.45, 69.16, 154.3, 69.16), ('via', '/U8_PH', 153.45, 69.16),
    ('via', '/U8_PH', 154.3, 69.16),
    ('seg', 'GND', F, 150.6, 67.89, 149.9, 68.6), ('seg', 'GND', F, 152.5, 67.89, 154.9, 67.89),
    ('seg', 'GND', F, 152.5, 67.89, 150.6, 67.89), ('seg', 'GND', F, 158.219, 67.683, 159.27, 68.734),
    ('via', 'GND', 159.27, 68.734),
    ('seg', '/VOUT', F, 152.5, 70.43, 154.9, 70.43), ('seg', '/VOUT', F, 155.4, 70.5, 158.2, 70.8),
]
MOVE_L1_ITEMS = [('via', '/U8_PH', x, 75.6) for x in (158.4, 159.2, 160.0, 160.8)] + \
    [('seg', '/U8_PH', F, x, 75.6, x, 76.8) for x in (158.4, 159.2, 160.0, 160.8)] + \
    [('seg', '/U8_PH', B, 158.4, 75.6, 160.8, 75.6)]
# (old seg, new ends): +5V1 sense line now ends above R16; Cout GND bus now starts at C32's GND pad
RESHAPE = [(('seg', '/+5V1', F, 171.9, 66.65, 142.0, 66.65), (171.9, 66.65, 144.2, 66.65)),
           (('seg', 'GND', F, 155.4, 67.75, 169.92, 67.75), (157.98, 67.75, 169.92, 67.75))]
W_SIG, W_GND_A, W_BOOT, W_PH_BR, W_PH, W_C31 = 0.25, 0.3, 0.4, 0.6, 1.5, 0.6
VIA_D, VIA_DRILL = 0.6, 0.3
C18_PH_VIA = (155.0, 83.8375)                    # right of C18's PH pad, clear of D3's silk
EP_TOP, EP_BOT = (147.619, 77.0), (147.619, 81.2)        # analog ground ends inside pad 9 (U8 at y 79.0)
ADD_SEGS = [
    ('/+5V1', F, W_SIG, [(144.2, 66.65), (144.2, 72.8)]),                       # sense line to R16 pin 1
    ('/U8_FB', F, W_SIG, [(144.2, 74.8), (144.2, 77.095)]),                     # R16 pin 2 to U8 pin 5
    ('/U8_FB', F, W_SIG, [(144.2, 74.8), (146.75, 72.8)]),                      # R16 pin 2 to R17 pin 1
    ('/U8_COMP', F, W_SIG, [(144.0, 78.365), (142.9, 78.365), (141.95, 77.25)]),
    ('/U8_CRC', F, W_SIG, [(139.95, 77.25), (138.65, 79.6825)]),
    ('/U8_SS', F, W_SIG, [(144.0, 80.905), (142.6, 80.905), (141.25, 79.9625)]),
    ('GND', F, W_GND_A, [(146.75, 74.8), EP_TOP]),                               # R17 return to pad 9
    ('GND', F, W_GND_A, [(138.65, 81.7575), (138.65, 83.0), (147.619, 83.0), EP_BOT]),  # C20 return to pad 9
    ('GND', F, W_GND_A, [(141.25, 82.0375), (141.25, 83.0)]),                   # C19 return to that trace
    ('/U8_BOOT', F, W_BOOT, [(151.2, 80.905), (152.6, 80.905), (153.6, 81.7625)]),
    ('/U8_PH', F, W_PH_BR, [(153.6, 83.8375), C18_PH_VIA]),                      # C18 PH pad to its via
    ('/U8_PH', B, W_PH_BR, [(152.15, 78.365), C18_PH_VIA]),                      # C18 PH branch
    ('/U8_PH', B, W_PH, [(153.0, 78.365), (159.4, 75.6)]),                      # block PH via to L1 via row
    ('GND', F, W_C31, [(156.919, 82.4875), (158.45, 82.4875)]),                 # C31 GND pad to its vias
    ('GND', F, W_C31, [(158.45, 82.0), (158.45, 83.0)]),
]
ADD_VIAS = [('/U8_PH', *C18_PH_VIA), ('GND', 158.45, 82.0), ('GND', 158.45, 83.0)]
ZONES = {
    'VOUT_TOP': ([(159.3, 72.3), (157.7, 72.3), (157.7, 84.0), (159.5, 84.0), (159.5, 97.75), (169.6, 97.75),
                  (169.6, 106.1), (156.2, 106.1), (156.2, 97.75), (156.2, 84.6), (153.0, 84.6), (153.0, 72.3),
                  (153.0, 69.5), (159.3, 69.5)],
                 [(150.3, 78.75), (158.3, 78.75), (158.3, 84.0), (159.5, 84.0), (159.5, 97.75), (169.6, 97.75),
                  (169.6, 106.1), (156.2, 106.1), (156.2, 86.3), (150.3, 86.3)]),
    'P5V_TOP': ([(173.0, 72.2), (174.4, 72.2), (174.4, 80.2), (163.0, 80.2), (163.0, 72.2), (160.2, 72.2),
                 (160.2, 69.9), (173.0, 69.9)],
                [(173.0, 72.2), (174.4, 72.2), (174.4, 80.2), (164.0, 80.2), (164.0, 72.2), (156.2, 72.2),
                 (156.2, 69.9), (173.0, 69.9)]),
}
KEEPOUT_NAME = 'AGND_KEEPOUT'
KEEPOUT = [(137.3, 76.0), (143.0, 76.0), (143.0, 71.6), (148.1, 71.6), (148.1, 76.35), (146.0, 76.35),
           (146.0, 81.85), (148.3, 81.85), (148.3, 83.6), (137.3, 83.6)]
VALUE_TO_FAB = ('U8',)
REF_TO_FAB = ('D3',)                             # its silk reference would sit on C18's PH pad mask


def near(a, b):
    return abs(MM(a) - b) <= TOL_NM


def at(fp):
    p = fp.GetPosition()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), fp.GetOrientationDegrees()


def same_place(fp, want):
    x, y, r = want
    p = fp.GetPosition()
    d = (fp.GetOrientationDegrees() - r) % 360.0
    return near(x, p.x) and near(y, p.y) and min(d, 360.0 - d) < 1e-3


def find(board, item):
    hits = []
    for t in board.GetTracks():
        if t.GetNetname() != item[1]:
            continue
        if item[0] == 'via':
            if t.Type() == pcbnew.PCB_VIA_T and near(item[2], t.GetPosition().x) and near(item[3], t.GetPosition().y):
                hits.append(t)
        elif t.Type() == pcbnew.PCB_TRACE_T and t.GetLayerName() == item[2]:
            a, b = t.GetStart(), t.GetEnd()
            x1, y1, x2, y2 = item[3:]
            if (near(x1, a.x) and near(y1, a.y) and near(x2, b.x) and near(y2, b.y)) or \
                    (near(x1, b.x) and near(y1, b.y) and near(x2, a.x) and near(y2, a.y)):
                hits.append(t)
    return hits


def one(board, item):
    hits = find(board, item)
    if len(hits) != 1:
        raise SystemExit(f'unexpected state: {len(hits)} matches for {item}')
    return hits[0]


def shifted(item, d):
    if item[0] == 'via':
        return item[:2] + (item[2] + d[0], item[3] + d[1])
    return item[:3] + (item[3] + d[0], item[4] + d[1], item[5] + d[0], item[6] + d[1])


def outline(zone):
    o = zone.Outline()
    return [(pcbnew.ToMM(o.CVertex(i).x), pcbnew.ToMM(o.CVertex(i).y)) for i in range(o.TotalVertices())]


def same_outline(zone, pts):
    cur = outline(zone)
    return len(cur) == len(pts) and all(abs(a - c) < 1e-3 and abs(b - d) < 1e-3 for (a, b), (c, d) in zip(cur, pts))


def set_outline(zone, pts):
    o = zone.Outline()
    o.RemoveAllContours()
    o.NewOutline()
    for x, y in pts:
        o.Append(MM(x), MM(y))


def zone_by_name(board, name):
    z = [z for z in board.Zones() if z.GetZoneName() == name]
    if len(z) != 1:
        raise SystemExit(f'unexpected state: {len(z)} zones named {name}')
    return z[0]


def add_track(board, net, layer, w, a, b):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(MM(a[0]), MM(a[1])))
    t.SetEnd(pcbnew.VECTOR2I(MM(b[0]), MM(b[1])))
    t.SetWidth(MM(w))
    t.SetLayer(board.GetLayerID(layer))
    t.SetNet(board.FindNet(net))
    t.SetLocked(True)
    board.Add(t)


def add_via(board, net, x, y):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetWidth(MM(VIA_D))
    v.SetDrill(MM(VIA_DRILL))
    v.SetNet(board.FindNet(net))
    v.SetLocked(True)
    board.Add(v)


def check_applied(board, fps, comps):
    errs = [r for r, w in NEW.items() if not same_place(fps[r], w)]
    for item in DELETE:
        if find(board, item):
            errs.append(f'still there: {item}')
    for item in MOVE_BLOCK_ITEMS:
        if len(find(board, shifted(item, BLOCK_MOVE))) != 1:
            errs.append(f'not moved: {item}')
    for item in MOVE_L1_ITEMS:
        if len(find(board, shifted(item, L1_MOVE))) != 1:
            errs.append(f'not moved: {item}')
    for name, (_, pts) in ZONES.items():
        if not same_outline(zone_by_name(board, name), pts):
            errs.append(f'zone {name} outline')
    if len([z for z in board.Zones() if z.GetZoneName() == KEEPOUT_NAME]) != 1:
        errs.append('keep-out missing')
    for ref in FIELD_REFS + NEW_REFS:
        if fps[ref].GetValue() != comps[ref]['value']:
            errs.append(f'{ref} value')
    for ref in REF_TO_FAB + tuple(NEW):
        if fps[ref].Reference().GetLayer() != pcbnew.F_Fab:
            errs.append(f'{ref} reference not on F.Fab')
    return errs


def main():
    argv = sys.argv[1:]
    dry = '--dry-run' in argv
    root = pathlib.Path(argv[argv.index('--root') + 1]).resolve() if '--root' in argv else ROOT
    pcb = root / f'{STEM}.kicad_pcb'
    upd.SCH = root / f'{STEM}.kicad_sch'
    upd.NETLIST = root / 'build' / 'netlist_16.xml'
    upd.export_netlist()
    comps, pin_net = upd.read_netlist()
    board = pcbnew.LoadBoard(str(pcb))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    if all(r in fps for r in NEW_REFS):
        errs = check_applied(board, fps, comps)
        if errs:
            raise SystemExit('unexpected state (partly applied?):\n  ' + '\n  '.join(errs))
        print('already applied')
        return 0
    if any(r in fps for r in NEW_REFS):
        raise SystemExit('unexpected state: only one of C31 / C32 on the board')
    bad = [f'{r} at {at(fps[r])}' for r, w in OLD.items() if not same_place(fps[r], w)]
    if bad:
        raise SystemExit('unexpected state: not at the recorded places: ' + ', '.join(bad))
    for ref in NEW_REFS + FIELD_REFS:
        if ref not in comps:
            raise SystemExit(f'{ref} not in the schematic netlist: run tools/post_sch/16 first')
    for name, (old_pts, _) in ZONES.items():
        if not same_outline(zone_by_name(board, name), old_pts):
            raise SystemExit(f'unexpected state: zone {name} outline {outline(zone_by_name(board, name))}')
    dels = [one(board, i) for i in DELETE]
    blk = [one(board, i) for i in MOVE_BLOCK_ITEMS]
    l1i = [one(board, i) for i in MOVE_L1_ITEMS]
    resh = [(one(board, i), e) for i, e in RESHAPE]
    if dry:
        print(f'dry run: {len(dels)} deletions, {len(blk) + len(l1i)} moved copper items, {len(NEW)} footprints '
              f'placed, {len(ADD_SEGS)} new track runs; nothing written')
        return 0
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    backups = root / f'{STEM}-backups'
    backups.mkdir(exist_ok=True)
    shutil.copy2(pcb, backups / f'{STEM}_{stamp}_post_route16.kicad_pcb')
    # fields of the changed parts
    for ref in FIELD_REFS:
        upd.apply_fields(fps[ref], ref, comps[ref], upd.want_path(comps[ref], fps[ref]))
    # new parts from the library
    keep = []
    for ref in NEW_REFS:
        fp = upd.load_lib_fp(comps[ref]['footprint'])
        board.Add(fp)
        keep.append(fp)
        upd.apply_fields(fp, ref, comps[ref], upd.want_path(comps[ref], None))
        for p in fp.Pads():
            p.SetNet(board.FindNet(pin_net[(ref, p.GetNumber())]))
        fps[ref] = fp
    # copper
    for t in dels:
        board.Remove(t)
    for t in blk:
        t.Move(pcbnew.VECTOR2I(MM(BLOCK_MOVE[0]), MM(BLOCK_MOVE[1])))
    for t in l1i:
        t.Move(pcbnew.VECTOR2I(MM(L1_MOVE[0]), MM(L1_MOVE[1])))
    for t, (x1, y1, x2, y2) in resh:
        t.SetStart(pcbnew.VECTOR2I(MM(x1), MM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(MM(x2), MM(y2)))
    # footprints
    for ref, (x, y, r) in NEW.items():
        fp = fps[ref]
        fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        fp.SetOrientationDegrees(r)
        fp.Reference().SetLayer(pcbnew.F_Fab)
    for ref in VALUE_TO_FAB:
        fps[ref].Value().SetLayer(pcbnew.F_Fab)
    for ref in REF_TO_FAB:
        fps[ref].Reference().SetLayer(pcbnew.F_Fab)
    for net, layer, w, pts in ADD_SEGS:
        for a, b in zip(pts, pts[1:]):
            add_track(board, net, layer, w, a, b)
    for net, x, y in ADD_VIAS:
        add_via(board, net, x, y)
    for name, (_, pts) in ZONES.items():
        set_outline(zone_by_name(board, name), pts)
    ko = pcbnew.ZONE(board)
    ko.SetIsRuleArea(True)
    ko.SetLayer(pcbnew.F_Cu)
    ko.SetZoneName(KEEPOUT_NAME)
    ko.SetDoNotAllowZoneFills(True)
    ko.SetDoNotAllowTracks(False)
    ko.SetDoNotAllowVias(False)
    ko.SetDoNotAllowPads(False)
    ko.SetDoNotAllowFootprints(False)
    set_outline(ko, KEEPOUT)
    ko.SetLocked(True)
    board.Add(ko)
    pcbnew.SaveBoard(str(pcb), board)
    del keep
    text = pcb.read_text(encoding='utf-8')
    pcb.write_text(upd.reseed_uuids(text, set(NEW_REFS)), encoding='utf-8', newline='')
    pcbnew.SaveBoard(str(pcb), pcbnew.LoadBoard(str(pcb)))
    route_lib.refill(pcb)
    print(f'applied: {len(NEW)} footprints placed, C31 / C32 added, {len(dels)} items deleted, copper re-routed, '
          f'zones refilled; backup {stamp}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
