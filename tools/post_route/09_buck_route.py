"""09: buck, power paths and Q1 tab provisions, as locked copper (routing phase; SPEC 4, 5; 2026-11-05).

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/09_buck_route.py`;
`--dry-run` builds everything and saves nothing):

1. Net classes and board rules in `pi_power_board.kicad_pro` (Default first, then by name, as KiCad saves them):
   Default 0.25 mm / 0.2 mm clearance / via 0.6 / 0.3; `Power` (`/BATT`, `/VOUT`) 3.0 mm, 0.3 mm clearance, via
   0.8 / 0.4; `Power5V` (`/+5V1`) 2.0 mm, 0.2 mm, via 0.8 / 0.4; `Switch` (`/U8_PH`) 1.5 mm, 0.3 mm, via 0.6 / 0.3.
   Board minimums: track 0.2 mm, clearance 0.2 mm, copper to edge 0.3 mm (was 0.5: the VOUT sense line runs
   along the GPIO-notch edge, the only path from Cout round the buck to the VSENSE side; 0.3 mm is the usual
   fab minimum for a routed outline, assumption), hole to hole 0.25 mm. Widths (IPC-2221 external, 1 oz):
   3.0 mm carries 5.3 A at +10 K; IPC-2152 baseline chart (curve fit, no adjacent plane, assumption) gives about
   +27 K at 5 A and +11 K at the 3.5 A of the 12 V case: the 5 A runs here are pours of 3.1 mm or wider and at most
   about 20 mm long. +5V1 3 A: 1.4 mm (IPC-2221, +10 K); pours plus two 0.38 mm necks (top and bottom in parallel)
   between the J2 pin rows, where nothing wider fits.
2. Buck U8 (SLVSCD5D 10.1, fig. 55), locked tracks and vias:
   - hot loop: C17 VIN pad to U8 pin 2 and U8 pin 4 to C17 GND pad, both short and straight on top; C15 next to
     C17; the C15 / C17 / C22-C24 GND pads on one top GND bus to U8 pin 4 and the PowerPAD, with GND vias between
     the capacitors;
   - PH: pin 3 to two vias right at the pin (between the pins and C17), a short wide bottom trace to four vias at
     L1 pad 1 (switch node about 12 mm; SPEC 5 "Buck layout"), and a bottom branch across the VIN pin to the BOOT
     capacitor C18 (fig. 55: "use a bottom layer trace to route the PH signal across the VIN pin to the boot
     capacitor"); BOOT pin 1 to C18 on top;
   - PowerPAD: the footprint's centre and thermal vias into the bottom GND pour (pour: 11);
   - VSENSE: R16 / R17 on the quiet (VSENSE) side; the sense line from C24 (the Cout end) along the top board edge
     round the buck, away from PH / L1; the FB node from pin 5 straight down the left of U8;
   - SS, COMP (bottom jumper from pin 6 under C19), CRC: short scripted traces. The SS / COMP / FB returns go to
     the GND pour (assumption: the pour under U8 is the single join point; fig. 55's separate analog ground trace
     is not drawn).
3. Power paths, as locked zones (filled by this script) and tracks:
   - `BATT` top: J1 pin 3 -> TVS1 -> along the J2 / L1 side -> down to Q1's source pin, with R14 / C30's `BATT`
     pads in the pour (>= 3.1 mm wide);
   - `VOUT`: Q1 tab top pour (as large as TVS2 and the Q1 pins allow) -> 23 vias -> bottom pour from the tab to J4
     pin 1 (TVS2 sits between the tab and J4 on top); the top `VOUT` run from the tab past the `BATT` feed up to the
     buck input (C15 / C17 / U8 pin 2), with D3 / R30 tapped off it;
   - `+5V1`: L1 pad 2 and C22-C24 in one top pour to the J2 VBUS pins (necks above);
   - `ACC_IN`: J1 pin 2 -> TVS2 pad first (top, 1.0 mm), then via the bottom to D5 (no branch before TVS2:
     placement review); TVS2's GND pad on top to J1's GND pin; TVS1's GND pad to the bottom GND by 5 vias;
   - `Q1_G` on top from Q1 pin 1 to C30 and R14, and R15's jumper on the bottom under the `VOUT` run and the
     `BATT` pour (both on top there);
   - a `BATT` via in the `BATT` pour (BATT_FEED_VIA): SW1's feed (signal current) is routed from it by 10.
4. Q1 tab hand-solder provisions (project lead): in the tab pad, 2 solder-feed vias (1.0 mm drill) and 21 thermal
   vias (0.4 mm), all `VOUT`; a board-level B.Mask opening over the tab area (no footprint change), so solder fed
   from the bottom wets the bottom pour and runs up the feed vias; `VOUT` pours on both layers under and round
   the tab. The front tab pad is the footprint's.
5. Everything this script adds is locked; zones are filled one priority at a time.

Guards: KiCad lock files; tools/check_fixed.py before and after; the footprints at the 08 positions this script
was laid out for (ANCHORS); no tracks / vias / non-rule zones on the board before the first run; every planned
item present -> "already applied"; some present -> stop. Seeded uuids (route_lib.save). Backup before saving.
"""
import json
import pathlib
import sys

import pcbnew

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import route_lib as rl  # noqa: E402

F, B = rl.F, rl.B
NAMESPACE = 'pipwr/09_buck_route'

# ---------------------------------------------------------------- rules (.kicad_pro)
CLASSES = [  # Default first, then by name
    {'name': 'Default', 'track_width': 0.25, 'clearance': 0.2, 'via_diameter': 0.6, 'via_drill': 0.3},
    {'name': 'Power', 'track_width': 3.0, 'clearance': 0.3, 'via_diameter': 0.8, 'via_drill': 0.4},
    {'name': 'Power5V', 'track_width': 2.0, 'clearance': 0.2, 'via_diameter': 0.8, 'via_drill': 0.4},
    {'name': 'Switch', 'track_width': 1.5, 'clearance': 0.3, 'via_diameter': 0.6, 'via_drill': 0.3},
]
PATTERNS = [('Power', '/BATT'), ('Power', '/VOUT'), ('Power5V', '/+5V1'), ('Switch', '/U8_PH')]
BOARD_RULES = {'min_track_width': 0.2, 'min_clearance': 0.2, 'min_copper_edge_clearance': 0.3,
               'min_hole_to_hole': 0.25}

# ---------------------------------------------------------------- the 08 positions this layout was drawn for
ANCHORS = {'U8': (148.919, 69.795), 'C15': (158.219, 69.245), 'C17': (155.419, 69.155), 'C18': (150.946, 75.152),
           'C19': (145.639, 75.152), 'C20': (149.019, 80.545), 'C22': (161.819, 69.295), 'C24': (169.919, 69.295),
           'L1': (164.719, 78.105), 'R16': (142.0, 80.486), 'R17': (145.866, 80.486), 'R18': (148.152, 75.152),
           'Q1': (163.576, 101.219), 'R14': (163.068, 89.916), 'C30': (163.068, 92.837), 'TVS1': (171.3, 89.55),
           'TVS2': (171.45, 99.822), 'D3': (149.2, 85.0), 'R30': (150.495, 90.932), 'D5': (155.067, 100.838),
           'J1': (179.406, 95.25), 'J2': (180.043, 79.192), 'J4': (177.419, 102.235)}
ANCHOR_TOL_NM = 1000

# ---------------------------------------------------------------- sizes (mm)
W_SIG = 0.25
W_SS = 0.4
W_BOOT = 0.4
W_PIN = 0.6           # stubs at the U8 pins (pin height)
W_CIN = 0.8
W_PAD_LINK = 0.5    # pin 4 to the PowerPAD
W_BUS = 1.0
W_PH = 1.5
W_PH_L1 = 1.0
W_PH_BOOT = 0.6
W_NECK = 0.38         # J2 VBUS between the pin rows
W_VBUS_VIA = 0.6
W_ACC = 1.0
W_ACC_RUN = 0.5
W_TVS2_GND = 1.6
W_TVS1_GND = 2.5
W_GATE = 0.4
W_TAP = 0.5           # D3 / R30 taps off VOUT
VIA_SIG = (0.6, 0.3)
VIA_PWR = (0.8, 0.4)
VIA_FEED = (1.6, 1.0)
VIA_THERM = (0.8, 0.4)
ZONE_CLEARANCE = 0.3
ZONE_MIN_W = 0.25
PRIO_BATT = 3
PRIO_POWER = 2

PH, VOUT, BATT, GND, P5 = '/U8_PH', '/VOUT', '/BATT', 'GND', '/+5V1'

# ---------------------------------------------------------------- tracks: (net, layer, points, width)
PH_A, PH_B = (153.45, 69.16), (154.30, 69.16)          # PH vias at pin 3
PH_BOOT_VIA = (151.4, 73.3)                            # PH via at C18
PH_L1_VIAS = [(158.4, 75.6), (159.2, 75.6), (160.0, 75.6), (160.8, 75.6)]
PH_L1_PAD_Y = 76.8                                      # stub ends inside L1 pad 1
COMP_VIA_PIN, COMP_VIA_R18 = (144.6, 69.16), (148.15, 73.4)
VBUS_VIAS = [(173.6, 78.2), (173.6, 79.2)]
VBUS_Y = 78.69                                          # between the J2 pin rows (pins 8/9, 17/18)
J2_PIN1_X = 180.04
ACC_VIA_TVS2, ACC_VIA_D5 = (169.6, 96.0), (155.07, 103.7)
BATT_FEED_VIA = (160.5, 91.35)                          # SW1's BATT feed leaves the BATT pour here (bottom, 10)
GATE_VIA_R15, GATE_VIA_C30 = (153.7, 86.2), (164.07, 91.36)   # Q1_G jumper under the VOUT run and the BATT pour
TVS1_GND_VIAS = [(169.35, 91.3), (169.35, 92.25), (169.35, 93.2), (168.3, 91.75), (168.3, 92.75)]
BUS_VIAS = [(156.73, 67.75), (159.8, 67.75), (163.85, 67.75), (167.9, 67.75)]
TAB = (160.68, 99.28, 166.48, 105.68)                   # Q1 tab pad (footprint), for the B.Mask opening
FEED_VIAS = [(162.0, 102.48), (165.15, 102.48)]
THERM_X = (161.3, 162.45, 163.6, 164.75, 165.9)
THERM_Y = (100.0, 101.2, 103.76, 104.96)
THERM_EXTRA = [(163.6, 102.48)]
THERM_VIAS = [(x, y) for y in THERM_Y for x in THERM_X] + THERM_EXTRA

TRACKS = [
    # buck: PH out of pin 3, down to L1, branch to C18
    (PH, F, [(152.5, 69.16), PH_A, PH_B], W_PIN),
    (PH, B, [PH_A, PH_B], W_PIN),
    (PH, B, [PH_B, PH_L1_VIAS[0]], W_PH),
    (PH, B, [PH_L1_VIAS[0], PH_L1_VIAS[-1]], W_PH_L1),
    *[(PH, F, [v, (v[0], PH_L1_PAD_Y)], W_PIN) for v in PH_L1_VIAS],
    (PH, B, [PH_A, (152.3, 72.9), PH_BOOT_VIA], W_PH_BOOT),
    (PH, F, [PH_BOOT_VIA, (151.0, 73.9)], W_PH_BOOT),
    ('/U8_BOOT', F, [(152.35, 71.7), (152.35, 76.2), (151.3, 76.2)], W_BOOT),
    # hot loop and GND bus
    (VOUT, F, [(152.5, 70.43), (154.9, 70.43)], W_PIN),
    (VOUT, F, [(155.4, 70.5), (158.2, 70.8)], W_CIN),
    (GND, F, [(152.5, 67.89), (150.6, 67.89), (149.9, 68.6)], W_PAD_LINK),
    (GND, F, [(152.5, 67.89), (154.9, 67.89)], W_PIN),
    (GND, F, [(155.4, 67.75), (169.92, 67.75)], W_BUS),
    # SS, COMP, CRC, FB, VOUT sense
    ('/U8_SS', F, [(145.5, 71.7), (145.6, 73.9)], W_SS),
    ('/U8_COMP', F, [COMP_VIA_PIN, (145.4, 69.16)], W_SS),
    ('/U8_COMP', B, [COMP_VIA_PIN, (144.6, 73.4), COMP_VIA_R18], W_SIG),
    ('/U8_CRC', F, [(148.0, 76.5), (147.55, 77.3), (147.55, 81.6), (148.6, 81.6)], W_SIG),
    ('/U8_FB', F, [(145.4, 67.89), (143.6, 67.89), (143.6, 81.49), (142.4, 81.49)], W_SIG),
    ('/U8_FB', F, [(143.6, 81.49), (145.6, 81.49)], W_SIG),
    (P5, F, [(170.6, 70.85), (171.9, 70.85), (171.9, 66.55), (142.0, 66.55), (142.0, 79.3)], W_SIG),
    # +5V1 to J2 VBUS (pins 10 and 1): necks on both layers
    (P5, F, [(173.9, VBUS_Y), (J2_PIN1_X, VBUS_Y)], W_NECK),
    (P5, B, [VBUS_VIAS[0], VBUS_VIAS[1]], W_VBUS_VIA),
    (P5, B, [(VBUS_VIAS[0][0], VBUS_Y), (J2_PIN1_X, VBUS_Y)], W_NECK),
    # ACC_IN: J1 pin 2 -> TVS2 -> bottom -> D5
    ('/ACC_IN', F, [(179.41, 91.44), (173.6, 91.44), (173.6, 94.3), (171.9, 96.0)], W_ACC),
    ('/ACC_IN', F, [(171.0, 96.0), ACC_VIA_TVS2], W_ACC_RUN),
    ('/ACC_IN', B, [ACC_VIA_TVS2, (157.0, 96.0), (155.07, 97.93), ACC_VIA_D5], W_ACC_RUN),
    ('/ACC_IN', F, [ACC_VIA_D5, (155.07, 102.5)], W_ACC_RUN),
    # TVS returns
    (GND, F, [(172.0, 102.0), (174.6, 102.0), (174.6, 96.6), (176.3, 95.25), (179.41, 95.25)], W_TVS2_GND),
    (GND, F, [(168.3, 92.25), (170.6, 92.25)], W_TVS1_GND),
    # Q1 gate, VOUT taps
    ('/Q1_G', F, [(164.07, 89.92), (164.1, 92.84), (164.1, 94.3), (165.86, 95.6)], W_GATE),
    ('/Q1_G', F, [GATE_VIA_R15, (153.7, 87.3)], W_GATE),
    ('/Q1_G', B, [GATE_VIA_R15, (158.9, 86.2), GATE_VIA_C30], W_GATE),
    (VOUT, F, [(150.7, 85.0), (150.7, 89.2)], W_TAP),
    (VOUT, F, [(151.0, 84.5), (153.6, 84.3)], W_TAP),
]

VIAS = [  # (net, xy, (dia, drill))
    (PH, PH_A, VIA_SIG), (PH, PH_B, VIA_SIG), (PH, PH_BOOT_VIA, VIA_SIG),
    *[(PH, v, VIA_SIG) for v in PH_L1_VIAS],
    ('/U8_COMP', COMP_VIA_PIN, VIA_SIG), ('/U8_COMP', COMP_VIA_R18, VIA_SIG),
    *[(GND, v, VIA_SIG) for v in BUS_VIAS],
    *[(P5, v, VIA_SIG) for v in VBUS_VIAS],
    ('/ACC_IN', ACC_VIA_TVS2, VIA_SIG), ('/ACC_IN', ACC_VIA_D5, VIA_SIG), (BATT, BATT_FEED_VIA, VIA_SIG),
    ('/Q1_G', GATE_VIA_R15, VIA_SIG), ('/Q1_G', GATE_VIA_C30, VIA_SIG),
    *[(GND, v, VIA_PWR) for v in TVS1_GND_VIAS],
    *[(VOUT, v, VIA_FEED) for v in FEED_VIAS],
    *[(VOUT, v, VIA_THERM) for v in THERM_VIAS],
]

ZONES = [  # (name, net, layer, rects, priority)
    ('BATT_TOP', BATT, F, [(159.9, 84.8, 180.6, 88.9), (159.9, 88.9, 163.0, 97.4)], PRIO_BATT),
    ('VOUT_TOP', VOUT, F, [(156.2, 97.75, 169.6, 106.1), (156.2, 84.0, 159.5, 97.75),
                           (153.0, 72.3, 157.7, 84.6), (153.0, 69.5, 159.3, 72.3)], PRIO_POWER),
    ('VOUT_BOT', VOUT, B, [(156.5, 97.75, 178.6, 106.1)], PRIO_POWER),
    ('P5V_TOP', P5, F, [(160.2, 69.9, 173.0, 72.2), (163.0, 72.2, 174.4, 80.2)], PRIO_POWER),
]
MASK_NAME_LAYER = pcbnew.B_Mask


def update_project():
    pro = rl.PRO
    d = json.loads(pro.read_text(encoding='utf-8'))
    ns = d['net_settings']
    old = {c['name']: c for c in ns['classes']}
    template = old['Default']
    classes = []
    for c in CLASSES:
        base = dict(old.get(c['name'], template))
        base.update(c)
        if c['name'] != 'Default':
            base['priority'] = CLASSES.index(c) - 1
        classes.append(base)
    want_patterns = [{'netclass': c, 'pattern': p} for c, p in PATTERNS]
    rules = d['board']['design_settings']['rules']
    changed = (ns['classes'] != classes or ns.get('netclass_patterns') != want_patterns
               or any(rules.get(k) != v for k, v in BOARD_RULES.items()))
    if not changed:
        return False
    ns['classes'] = classes
    ns['netclass_patterns'] = want_patterns
    rules.update(BOARD_RULES)
    return d


def planned_keys():
    keys = set()
    for netname, layer, pts, w in TRACKS:
        for a, b in zip(pts[:-1], pts[1:]):
            keys.add(rl.planned_track_key(netname, layer, a, b, w))
    for netname, xy, (dia, drill) in VIAS:
        keys.add(rl.planned_via_key(netname, xy, dia, drill))
    return keys


def check_anchors(board):
    for ref, (x, y) in ANCHORS.items():
        p = board.FindFootprintByReference(ref).GetPosition()
        if abs(p.x - rl.nm(x)) > ANCHOR_TOL_NM or abs(p.y - rl.nm(y)) > ANCHOR_TOL_NM:
            raise SystemExit(f'{ref} at ({p.x / 1e6:.3f}, {p.y / 1e6:.3f}), not the 08 position {x, y}: stop')


def add_mask_opening(board):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetLayer(MASK_NAME_LAYER)
    s.SetStart(rl.P(TAB[0], TAB[1]))
    s.SetEnd(rl.P(TAB[2], TAB[3]))
    s.SetFilled(True)
    s.SetWidth(0)
    s.SetLocked(True)
    board.Add(s)


def has_mask_opening(board):
    for d in board.GetDrawings():
        if d.GetLayer() == MASK_NAME_LAYER and d.GetShape() == pcbnew.SHAPE_T_RECT:
            s, e = d.GetStart(), d.GetEnd()
            if (s.x, s.y, e.x, e.y) == tuple(rl.nm(v) for v in TAB):
                return True
    return False


def main():
    rl.guard_locks()
    rl.check_fixed()
    pro_new = update_project()
    before_text = rl.PCB.read_text(encoding='utf-8')
    board = pcbnew.LoadBoard(str(rl.PCB))
    check_anchors(board)
    have = {rl.track_key(t) for t in board.GetTracks()}
    want = planned_keys()
    zones_have = {z.GetZoneName() for z in board.Zones() if not z.GetIsRuleArea()}
    zones_want = {z[0] for z in ZONES}
    if want <= have and zones_want <= zones_have and has_mask_opening(board) and not pro_new:
        print('already applied: every 09 track, via, zone and the B.Mask opening present; rules set; nothing saved')
        return
    if (want & have) or (zones_want & zones_have) or has_mask_opening(board):
        raise SystemExit(f'partly applied ({len(want & have)} of {len(want)} items, zones {zones_want & zones_have}): '
                         'stop (restore the backup)')
    if any(True for _ in board.GetTracks()) or zones_have:
        raise SystemExit('the board already has copper that 09 did not lay out: stop')

    for netname, layer, pts, w in TRACKS:
        rl.add_path(board, netname, layer, pts, w)
    for netname, xy, (dia, drill) in VIAS:
        rl.add_via(board, netname, xy, dia, drill)
    for name, netname, layer, rects, prio in ZONES:
        rl.add_zone(board, name, netname, layer, rects, prio, ZONE_CLEARANCE, ZONE_MIN_W, pcbnew.ZONE_CONNECTION_FULL)
    add_mask_opening(board)
    n_t = sum(len(t[2]) - 1 for t in TRACKS)
    print(f'  {n_t} track segments, {len(VIAS)} vias ({len(FEED_VIAS)} feed + {len(THERM_VIAS)} thermal in the Q1 '
          f'tab), {len(ZONES)} zones, B.Mask opening {TAB}')
    if '--dry-run' in sys.argv:
        print('dry run: nothing saved')
        return
    rl.backup(rl.PCB)
    if pro_new:
        rl.backup(rl.PRO)
        rl.PRO.write_text(json.dumps(pro_new, indent=2) + '\n', encoding='utf-8')
        print('  .kicad_pro: net classes', [c['name'] for c in CLASSES], 'patterns', PATTERNS, 'rules', BOARD_RULES)
    rl.save(board, before_text, NAMESPACE)
    rl.refill()
    rl.check_fixed()
    print('saved and filled')


if __name__ == '__main__':
    main()
