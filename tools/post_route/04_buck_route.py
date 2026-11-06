"""04: net classes and DRC rules, then the pre-route copper (buck, power paths, GND fan-out), all locked.

Run (KiCad python, under timeout, from the project root): `python.exe -I tools/post_route/04_buck_route.py`.
Routing phase, overnight 2026-11-04 (SPEC 4 "Current", SPEC 5 "Power copper" / "Buck layout", SLVSCD5D 10.1/10.2).

1. Net classes (`.kicad_pro`, Default first, then by name) and `.kicad_dru`:
   - Default 0.25 mm / clearance 0.2 mm, via 0.6/0.3 (board house minimum 0.15 mm; 0.2 for margin);
   - Power (`/BATT`, `/VOUT`: Q1 source and drain): clearance 0.25 mm (car transients up to the 26 V TVS clamp);
     class width 0.5 mm = the width of the low-current branches (gate network, logic supply, dividers, LED, SW1),
     via 0.8/0.4. The 5 A trunks are zones drawn here, >= 3 mm wide (see below);
   - Power5V (`/+5V1`): 0.5 mm, clearance 0.2, via 0.8/0.4; trunk zones >= 1.5 mm;
   - SW (`/U8_PH`): 0.5 mm, clearance 0.2, via 0.6/0.3 (the PH vias must fit next to pin 3);
   - `.kicad_dru`: minimum track width per class (Freerouting must not thin a power branch) and the power via size.
   Width basis (IPC-2221 external-layer chart, I = 0.048 dT^0.44 A^0.725, A in mil^2, 1 oz = 1.378 mil, dT 10 C):
   5 A -> 2.77 mm, 3 A -> 1.37 mm (`TRUNK_WIDTH_5A_MM`, `TRUNK_WIDTH_3A_MM` below, computed at import).
   Vias: a 0.3 mm via barrel (25 um plating) carries about 1.8 A and a 0.4 mm one about 2.2 A at 10 C (same chart).
2. Buck U8 (SLVSCD5D 10.1 and Figure 55, all top unless noted):
   - VIN: pin 2 -> C17 VIN pad directly (the high-frequency input loop pin 2 -> C17 -> pin 4 is the shortest on the
     board), on to C15 (VIN pad up, under the BOOT pin) and C16 (VIN link between C15 and C16 GND pads), one
     VOUT zone that continues as the VOUT feed corridor down to C14 and C12 (`VOUT_W_RECTS`);
   - GND: pin 4 joined to the C17 GND pad and to top pad 9 by a GND zone above the pins, 5 vias into the bottom
     GND pour; C15/C16 GND pads by vias (they are boxed in by the VIN copper); pad 9 already has its centre hole
     and 10 thermal vias (footprint);
   - PH: a small top area at pin 3 with 4 vias, a short bottom strip (`PH_B_RECTS`) and 4 vias in the L1 pad
     (TI: "use vias to route the PH signal to the bottom side ... short and wide"); the BOOT cap's PH pad by a
     bottom track that crosses under the VIN and BOOT pins (TI: same), BOOT pin -> C18 BOOT pad on top;
   - FB: R16 -> pin 5 -> R17 on the analog side, away from PH and L1. The +5V1 sense into R16 and the analog
     returns (R17, R20, C19, C21, C20: "a separate ground trace joined at one point") are routed by 05 with a
     keep-out over the PH/L1 area; their single join to the power ground is the star via `AGND_STAR`;
   - +5V1: L1 pad 2 down to C22-C24 and C25 (`P5V_RECTS`), necks into J2 VBUS2 (pin 10) and on to VBUS1 (pin 1)
     between the J2 SuperSpeed pins (`J2_NECK_*`: 0.38 mm, the pin field leaves no more at 0.2 mm clearance);
     C26 (west of the VOUT corridor) through a bottom jumper with 2 vias at each end.
3. Power paths:
   - BATT: one top zone from J1 pin 3 over the TVS1 cathode to the Q1 source (>= 4.2 mm wide); C11 by a 0.5 mm branch
     north of the Q1 tab;
   - VOUT: the Q1 tab -> J4 pin 1 trunk on the bottom (`VOUT_B_RECTS`, >= 4.4 mm; it passes J4's GND pin, which the
     top can't), 12 vias 0.8/0.4 in the tab (current and heat into the bottom copper: SPEC 4 Q1, 1 in^2 basis; the
     bottom area is what fits), 8 vias from the bottom zone up into the west island at C12 / C14, whose corridor
     feeds the buck (>= 1.8 mm for <= 2.1 A buck input at 9 V);
4. GND fan-out: one via (two on TVS1/TVS2/C12) next to every SMD GND pad of the logic and power parts, by a seeded
   search (shortest stub, clearances below); the analog returns get none (05).

Lock: every item here is locked (Freerouting gets it as fixed copper; the DSN gets the zones as planes).
Guards: KiCad lock files; nets and pads as expected (pad positions checked against PAD_EXPECT); no track/via/zone
on the board except this script's own; check_fixed PASS afterwards. Idempotent: on a board that has every planned
item the script prints "already applied" and saves nothing; partial state stops it. Backup first; uuids of the new
items reseeded (uuid5), so two runs from the same input give the same file.
"""
import json
import math
import pathlib
import sys

import pcbnew

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import route_lib as rl  # noqa: E402

NAMESPACE = 'pi-car-power-supply/tools/post_route/04_buck_route'

# ---------------------------------------------------------------- width basis (IPC-2221 external chart)
IPC_K_EXT = 0.048
IPC_DT_EXP = 0.44
IPC_A_EXP = 0.725
DT_C = 10.0
OZ1_MIL = 1.378
MIL_MM = 25.4e-3
PLATING_MM = 25e-3


def ipc_width_mm(amps):
    area = (amps / (IPC_K_EXT * DT_C ** IPC_DT_EXP)) ** (1 / IPC_A_EXP)
    return area / OZ1_MIL * MIL_MM


def via_amps(drill_mm):
    area_mil2 = math.pi * drill_mm * PLATING_MM / MIL_MM ** 2
    return IPC_K_EXT * DT_C ** IPC_DT_EXP * area_mil2 ** IPC_A_EXP


I_POWER_A = 5.0
I_5V_A = 3.0
TRUNK_WIDTH_5A_MM = ipc_width_mm(I_POWER_A)
TRUNK_WIDTH_3A_MM = ipc_width_mm(I_5V_A)

# ---------------------------------------------------------------- net classes
CLASSES = {   # name: (track, clearance, via dia, via drill)
    'Default': (0.25, 0.2, 0.6, 0.3),
    'Power': (0.5, 0.25, 0.8, 0.4),
    'Power5V': (0.5, 0.2, 0.8, 0.4),
    'SW': (0.5, 0.2, 0.6, 0.3),
}
PATTERNS = [('Power', '/BATT'), ('Power', '/VOUT'), ('Power5V', '/+5V1'), ('SW', '/U8_PH')]
RULES = {'min_clearance': 0.15, 'min_track_width': 0.2}
TRACK_WIDTHS = [0.0, 0.25, 0.5, 1.0, 1.5, 3.0]
VIA_SIZES = [(0.0, 0.0), (0.6, 0.3), (0.8, 0.4)]
DRU_TEXT = """(version 1)
# 04_buck_route.py: power branches keep the class width (no thin necks from the autorouter)
(rule "Power track width"
  (condition "A.NetClass == 'Power'")
  (constraint track_width (min 0.5mm)))
(rule "Power5V track width"
  (condition "A.NetClass == 'Power5V'")
  (constraint track_width (min 0.5mm)))
(rule "SW track width"
  (condition "A.NetClass == 'SW'")
  (constraint track_width (min 0.5mm)))
# power vias: 0.8 / 0.4 (about 2.2 A each)
(rule "Power via"
  (condition "A.Type == 'Via' && (A.NetClass == 'Power' || A.NetClass == 'Power5V')")
  (constraint via_diameter (min 0.8mm))
  (constraint hole_size (min 0.4mm)))
"""

# ---------------------------------------------------------------- sizes (mm)
SIG_VIA = (0.6, 0.3)
PWR_VIA = (0.8, 0.4)
ZONE_MIN_W = 0.25
PWR_CLR = 0.25
DEF_CLR = 0.2
PRIO_POWER = 2
BOOT_W = 0.4
FB_W = 0.25
BRANCH_W = 0.5
PH_BOOT_W = 0.4
JUMPER_W = 0.5

# ---------------------------------------------------------------- copper plan (rects x0, y0, x1, y1)
VOUT_W_RECTS = [      # top: pin 2 -> C17 -> C15 / C16 -> corridor -> C14 -> C12 (one VOUT zone)
    (156.20, 71.76, 157.60, 72.31),     # pin 2 -> C17 VIN pad
    (156.47, 71.85, 159.45, 74.00),     # C17 VIN pad area (0.25 from the BOOT pin)
    (155.00, 74.00, 159.45, 76.45),     # down to C15
    (154.30, 75.12, 156.10, 76.45),     # C15 VIN pad
    (156.37, 74.00, 159.45, 84.00),     # east corridor past C15/C16 GND pads
    (152.00, 79.83, 156.37, 80.65),     # link to C16 VIN pad (between the C15 and C16 GND pads)
    (151.68, 80.65, 153.00, 82.70),     # C16 VIN pad
    (155.13, 82.95, 156.95, 93.50),     # corridor between C26 and R15
    (155.13, 93.50, 158.55, 97.05),     # C14 VOUT pad
    (153.20, 95.53, 158.60, 100.15),    # via island north of C12
    (153.00, 100.15, 157.40, 102.65),   # C12 + pad
]
VOUT_W_VIAS = [(x, y) for y in (96.8, 98.6) for x in (154.2, 155.4, 156.6, 157.8)]
Q1_TAB_VIAS = [(x, y) for y in (96.6, 98.64, 100.7) for x in (163.0, 164.6, 166.2, 167.7)]
VOUT_B_RECTS = [      # bottom: under C12 / Q1 -> J4 pin 1
    (153.50, 96.50, 176.17, 105.93),
    (176.17, 96.50, 178.20, 100.98),    # past J4 pin 2 (GND)
    (178.67, 96.50, 182.60, 103.60),    # J4 pin 1
]
BATT_T_RECTS = [
    (170.30, 89.15, 176.00, 96.96),     # TVS1 cathode, Q1 source
    (176.00, 92.69, 180.41, 96.96),     # J1 pin 3 (0.25 from J1 pin 2)
]
C11_BRANCH = [(160.4, 92.41), (161.7, 93.71), (161.7, 95.0), (170.6, 95.0)]
GND_BUCK_RECTS = [
    (153.50, 67.40, 159.03, 69.80),     # above pins 4 / C17 GND, joins top pad 9
    (157.57, 69.78, 159.03, 70.95),     # C17 GND pad
]
GND_BUCK_VIAS = [(x, 68.0) for x in (154.6, 155.6, 156.6, 157.6, 158.6)]
C15_GND_RECTS = [(154.30, 76.70, 156.10, 79.58)]
C15_GND_VIAS = [(154.75, 77.15), (155.65, 77.15)]
C16_GND_PATH = [(154.9, 82.5), (154.1, 83.3)]
C16_GND_VIAS = [(154.1, 83.3)]
PH_T_RECTS = [(156.00, 70.05, 157.35, 71.50), (154.22, 70.47, 156.22, 71.06)]
PH_VIAS_U8 = [(156.45, 70.35), (157.05, 70.35), (156.45, 71.2), (157.05, 71.2)]
PH_B_RECTS = [(156.10, 70.00, 161.75, 72.05)]
PH_VIAS_L1 = [(160.5, 70.9), (161.3, 70.9), (160.5, 71.7), (161.3, 71.7)]
PH_BOOT_B = [(156.75, 72.0), (156.75, 75.6), (154.3, 75.6), (153.65, 77.6)]
PH_BOOT_VIA = (153.65, 77.6)
PH_BOOT_T = [(153.65, 77.6), (152.4, 78.338)]
BOOT_T = [(154.45, 73.305), (154.45, 74.3), (153.2, 74.3), (152.4, 76.263)]
FB_T = [(149.05, 67.35), (149.05, 69.495), (146.65, 69.495)]
J2_NECK_Y = (78.50, 78.88)
P5V_RECTS = [
    (169.45, 70.35, 173.55, 73.85),     # L1 pad 2
    (169.20, 73.85, 173.80, 78.10),
    (159.70, 77.90, 175.13, 79.80),     # C25 .. C22 band
    (159.70, 78.45, 161.30, 83.40),     # C25 + pad and its jumper vias
    (175.13, J2_NECK_Y[0], 177.48, J2_NECK_Y[1]),   # neck into J2 pin 10 (between pins 17 / 18)
    (177.48, J2_NECK_Y[0], 180.68, J2_NECK_Y[1]),   # pin 10 -> pin 1 (between pins 8 / 9)
]
C25_JUMPER_VIAS = [(160.1, 82.85), (160.9, 82.85)]
C26_JUMPER_VIAS = [(151.3, 84.75), (151.3, 85.65)]
C26_JUMPER_B = [(160.9, 82.85), (160.1, 82.85), (158.2, 84.75), (151.3, 84.75), (151.3, 85.65)]
C26_STUB_T = [(151.3, 84.75), (152.4, 84.75)]
AGND_STAR = (150.9, 76.2)

# pads the plan relies on: (ref, pad) -> (net, x, y) centre
PAD_EXPECT = {
    ('U8', '1'): ('/U8_BOOT', 155.215, 73.305), ('U8', '2'): ('/VOUT', 155.215, 72.035),
    ('U8', '3'): ('/U8_PH', 155.215, 70.765), ('U8', '4'): ('GND', 155.215, 69.495),
    ('U8', '5'): ('/U8_FB', 149.365, 69.495), ('C17', '1'): ('/VOUT', 158.3, 72.438),
    ('C17', '2'): ('GND', 158.3, 70.362), ('C15', '1'): ('/VOUT', 155.2, 75.787), ('C15', '2'): ('GND', 155.2, 78.912),
    ('C16', '1'): ('/VOUT', 152.338, 81.8), ('C16', '2'): ('GND', 155.463, 81.8),
    ('C18', '1'): ('/U8_BOOT', 152.4, 76.263), ('C18', '2'): ('/U8_PH', 152.4, 78.338),
    ('L1', '1'): ('/U8_PH', 162.0, 72.1), ('L1', '2'): ('/+5V1', 171.5, 72.1),
    ('R16', '2'): ('/U8_FB', 149.05, 67.35), ('R17', '1'): ('/U8_FB', 146.65, 69.25),
    ('C12', '1'): ('/VOUT', 155.2, 101.4), ('C14', '2'): ('/VOUT', 157.137, 95.15),
    ('Q1', '2'): ('/VOUT', 165.29, 98.64), ('Q1', '3'): ('/BATT', 171.59, 96.36),
    ('TVS1', '1'): ('/BATT', 172.4, 92.55), ('J1', '3'): ('/BATT', 179.406, 95.25),
    ('J4', '1'): ('/VOUT', 181.229, 102.235), ('J4', '2'): ('GND', 177.419, 102.235),
    ('C11', '1'): ('/BATT', 160.4, 92.412), ('C25', '1'): ('/+5V1', 160.5, 80.2), ('C26', '1'): ('/+5V1', 152.8, 85.55),
    ('C22', '1'): ('/+5V1', 171.6, 79.108), ('J2', '10'): ('/+5V1', 177.478, 79.192),
    ('J2', '1'): ('/+5V1', 180.678, 79.192),
}
POS_TOL_MM = 2e-3

# GND fan-out: pads and via count; the search
FANOUT = {('C11', '2'): 1, ('C12', '2'): 2, ('C2', '2'): 1, ('C22', '2'): 1, ('C23', '2'): 1, ('C24', '2'): 1,
          ('C25', '2'): 1, ('C26', '2'): 1, ('C3', '2'): 1, ('C4', '2'): 1, ('C5', '2'): 1, ('C6', '2'): 1,
          ('C7', '2'): 1, ('C8', '2'): 1, ('C9', '2'): 1, ('DZ1', '2'): 1, ('Q2', '2'): 1, ('Q4', '2'): 1,
          ('R1', '2'): 1, ('R3', '2'): 1, ('R5', '2'): 1, ('R7', '2'): 1, ('R8', '2'): 1, ('TVS1', '2'): 2,
          ('TVS2', '2'): 2, ('U3', '2'): 1, ('U4', '1'): 1}
FAN_SEARCH_R = 3.0
FAN_STEP = 0.05
FAN_CLR = 0.25              # via / stub to any other net (the largest class clearance)
FAN_OWN_PAD_GAP = 0.15      # via copper outside its own pad (no via in pad)
FAN_HOLE_GAP = 0.3          # hole to hole (board rule 0.25)
FAN_EDGE_CLR = 0.5          # board rule copper to edge
FAN_STUB_W = 0.4
ANALOG_BOX = (144.7, 66.0, 151.0, 86.3)    # no fan-out vias here (analog returns: 05)


def update_project():
    """Net classes, patterns, rules, size lists in .kicad_pro; .kicad_dru. Returns True if anything changed."""
    text = rl.PRO.read_text(encoding='utf-8')
    d = json.loads(text)
    if json.dumps(d, indent=2) + '\n' != text:
        raise SystemExit('.kicad_pro does not round-trip through json: format changed, stop')
    ns = d['net_settings']
    default = next(c for c in ns['classes'] if c['name'] == 'Default')
    classes = []
    for prio, name in enumerate(['Default'] + sorted(n for n in CLASSES if n != 'Default')):
        c = dict(default)
        w, clr, vd, vdr = CLASSES[name]
        c.update(name=name, track_width=w, clearance=clr, via_diameter=vd, via_drill=vdr)
        if name != 'Default':
            c['priority'] = prio - 1
        classes.append(dict(sorted(c.items())))
    ns['classes'] = classes
    ns['netclass_patterns'] = [{'netclass': c, 'pattern': p} for c, p in PATTERNS]
    ds = d['board']['design_settings']
    ds['rules'].update(RULES)
    ds['track_widths'] = TRACK_WIDTHS
    ds['via_dimensions'] = [{'diameter': a, 'drill': b} for a, b in VIA_SIZES]
    new = json.dumps(d, indent=2) + '\n'
    changed = new != text
    if changed:
        rl.backup(rl.PRO)
        rl.PRO.write_text(new, encoding='utf-8', newline='')
    if not rl.DRU.exists() or rl.DRU.read_text(encoding='utf-8') != DRU_TEXT:
        if rl.DRU.exists():
            rl.backup(rl.DRU)
        rl.DRU.write_text(DRU_TEXT, encoding='utf-8', newline='')
        changed = True
    return changed


def check_pads(board):
    for (ref, num), (netname, x, y) in PAD_EXPECT.items():
        fp = board.FindFootprintByReference(ref)
        pads = [p for p in fp.Pads() if p.GetNumber() == num]
        if not pads:
            raise SystemExit(f'{ref}.{num} missing')
        p = pads[0]
        pos = p.GetPosition()
        if p.GetNetname() != netname or abs(rl.mm(pos.x) - x) > POS_TOL_MM or abs(rl.mm(pos.y) - y) > POS_TOL_MM:
            raise SystemExit(f'{ref}.{num}: {p.GetNetname()} at ({rl.mm(pos.x):.3f}, {rl.mm(pos.y):.3f}), '
                             f'plan expects {netname} at ({x}, {y}): placement changed, re-plan')


def plan_fixed():
    """The fixed (non-searched) items: list of ('track', net, layer, a, b, w) / ('via', net, xy, dia, drill) /
    ('zone', name, net, layer, rects, clearance, connection)."""
    FULL = pcbnew.ZONE_CONNECTION_FULL
    items = []

    def path(netname, layer, pts, w):
        for a, b in zip(pts[:-1], pts[1:]):
            items.append(('track', netname, layer, a, b, w))

    def vias(netname, pts, size):
        for p in pts:
            items.append(('via', netname, p) + size)

    items.append(('zone', 'VOUT_W_T', '/VOUT', rl.F, VOUT_W_RECTS, PWR_CLR, FULL))
    items.append(('zone', 'VOUT_B', '/VOUT', rl.B, VOUT_B_RECTS, PWR_CLR, FULL))
    items.append(('zone', 'BATT_T', '/BATT', rl.F, BATT_T_RECTS, PWR_CLR, FULL))
    items.append(('zone', 'GND_BUCK_T', 'GND', rl.F, GND_BUCK_RECTS, DEF_CLR, FULL))
    items.append(('zone', 'GND_C15_T', 'GND', rl.F, C15_GND_RECTS, PWR_CLR, FULL))
    items.append(('zone', 'PH_T', '/U8_PH', rl.F, PH_T_RECTS, DEF_CLR, FULL))
    items.append(('zone', 'PH_B', '/U8_PH', rl.B, PH_B_RECTS, DEF_CLR, FULL))
    items.append(('zone', 'P5V_T', '/+5V1', rl.F, P5V_RECTS, DEF_CLR, FULL))
    vias('/VOUT', VOUT_W_VIAS, PWR_VIA)
    vias('/VOUT', Q1_TAB_VIAS, PWR_VIA)
    path('/BATT', rl.F, C11_BRANCH, BRANCH_W)
    vias('GND', GND_BUCK_VIAS, SIG_VIA)
    vias('GND', C15_GND_VIAS, SIG_VIA)
    path('GND', rl.F, C16_GND_PATH, FAN_STUB_W)
    vias('GND', C16_GND_VIAS, SIG_VIA)
    vias('/U8_PH', PH_VIAS_U8, SIG_VIA)
    vias('/U8_PH', PH_VIAS_L1, SIG_VIA)
    path('/U8_PH', rl.B, PH_BOOT_B, PH_BOOT_W)
    vias('/U8_PH', [PH_BOOT_VIA], SIG_VIA)
    path('/U8_PH', rl.F, PH_BOOT_T, PH_BOOT_W)
    path('/U8_BOOT', rl.F, BOOT_T, BOOT_W)
    path('/U8_FB', rl.F, FB_T, FB_W)
    vias('/+5V1', C25_JUMPER_VIAS, PWR_VIA)
    vias('/+5V1', C26_JUMPER_VIAS, PWR_VIA)
    path('/+5V1', rl.B, C26_JUMPER_B, JUMPER_W)
    path('/+5V1', rl.F, C26_STUB_T, JUMPER_W)
    vias('GND', [AGND_STAR], SIG_VIA)
    return items


def zone_key(z):
    o = z.Outline()
    pts = tuple((o.CVertex(i).x, o.CVertex(i).y) for i in range(o.TotalVertices()))
    return ('zone', z.GetZoneName(), z.GetNetname(), z.GetLayer(), pts)


def planned_key(it, board):
    if it[0] == 'track':
        return rl.planned_track_key(it[1], it[2], it[3], it[4], it[5])
    if it[0] == 'via':
        return rl.planned_via_key(it[1], it[2], it[3], it[4])
    ps = rl.rects_poly(it[4])
    pts = tuple((ps.CVertex(i).x, ps.CVertex(i).y) for i in range(ps.TotalVertices()))
    return ('zone', it[1], it[2], it[3], pts)


def apply_fixed(board, items):
    for it in items:
        if it[0] == 'track':
            rl.add_track(board, it[1], it[2], it[3], it[4], it[5])
        elif it[0] == 'via':
            rl.add_via(board, it[1], it[2], it[3], it[4])
        else:
            rl.add_zone(board, it[1], it[2], it[3], it[4], PRIO_POWER, it[5], ZONE_MIN_W, it[6])


def zone_rects_of(items):
    out = {}
    for it in items:
        if it[0] == 'zone':
            out.setdefault((it[2], it[3]), []).extend(it[4])
    return out


def fanout(board, items):
    """One or two GND vias per FANOUT pad: shortest stub from the pad centre that clears everything."""
    obs = rl.board_obstacles(board, zone_rects_of(items))
    edges = rl.edge_segments(board)
    poly = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(poly, True)
    r_via, r_drill = SIG_VIA[0] / 2, SIG_VIA[1] / 2
    half = FAN_STUB_W / 2
    added, failed = [], []
    for (ref, num), count in sorted(FANOUT.items()):
        pad = next(p for p in board.FindFootprintByReference(ref).Pads() if p.GetNumber() == num)
        if pad.GetNetname() != 'GND':
            raise SystemExit(f'{ref}.{num} is not GND')
        own = rl.pad_obstacle(pad)
        c = (rl.mm(pad.GetPosition().x), rl.mm(pad.GetPosition().y))
        for k in range(count):
            best = None
            n = int(FAN_SEARCH_R / FAN_STEP)
            for i in range(-n, n + 1):
                for j in range(-n, n + 1):
                    v = (round(c[0] + i * FAN_STEP, 3), round(c[1] + j * FAN_STEP, 3))
                    L = math.hypot(v[0] - c[0], v[1] - c[1])
                    if L > FAN_SEARCH_R or (best and L >= best[0]):
                        continue
                    if own.dist_pt(v) < r_via + FAN_OWN_PAD_GAP:
                        continue
                    if ANALOG_BOX[0] <= v[0] <= ANALOG_BOX[2] and ANALOG_BOX[1] <= v[1] <= ANALOG_BOX[3]:
                        continue
                    if not poly.Contains(rl.P(*v)) or min(rl.seg_dist(v, a, b) for a, b in edges) < r_via + FAN_EDGE_CLR:
                        continue
                    ok = True
                    for o in obs:
                        if o.hole and math.hypot(v[0] - o.hole[0], v[1] - o.hole[1]) < r_drill + o.hole[2] + FAN_HOLE_GAP:
                            ok = False
                            break
                        if o.net == 'GND':
                            continue
                        if o.dist_pt(v) < r_via + FAN_CLR:
                            ok = False
                            break
                        if rl.F in o.layers and o.dist_seg(c, v) < half + FAN_CLR:
                            ok = False
                            break
                    if ok:
                        best = (L, v)
            if not best:
                failed.append(f'{ref}.{num}')
                break
            v = best[1]
            added.append((ref, num, c, v))
            obs.append(rl.Obstacle('GND', {rl.F, rl.B}, ('circle', v[0], v[1], r_via), (v[0], v[1], r_drill)))
            obs.append(rl.Obstacle('GND', {rl.F}, ('seg', c, v, half)))
    if failed:
        raise SystemExit(f'GND fan-out: no via spot for {failed}')
    for ref, num, c, v in added:
        rl.add_track(board, 'GND', rl.F, c, v, FAN_STUB_W)
        rl.add_via(board, 'GND', v, *SIG_VIA)
    return added


def main():
    rl.guard_locks()
    print(f'IPC-2221 external, 1 oz, +{DT_C:.0f} C: {I_POWER_A} A -> {TRUNK_WIDTH_5A_MM:.2f} mm, '
          f'{I_5V_A} A -> {TRUNK_WIDTH_3A_MM:.2f} mm; via 0.3 mm {via_amps(0.3):.1f} A, 0.4 mm {via_amps(0.4):.1f} A')
    if update_project():
        print('net classes / rules written (.kicad_pro, .kicad_dru)')
    else:
        print('net classes / rules: already applied')
    board = pcbnew.LoadBoard(str(rl.PCB))
    check_pads(board)
    items = plan_fixed()
    want = {planned_key(it, board) for it in items}
    have_tracks = {rl.track_key(t) for t in board.GetTracks()}
    have_zones = {zone_key(z) for z in board.Zones() if not z.GetIsRuleArea()}
    have = have_tracks | have_zones
    present = want & have
    if present == want:
        fan_pads = [(r, n) for (r, n) in FANOUT]
        gnd_vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == 'GND']
        if len(gnd_vias) < sum(FANOUT.values()) + len(GND_BUCK_VIAS) + len(C15_GND_VIAS) + 2:
            raise SystemExit('fixed items present but the GND fan-out is incomplete: partial state, stop')
        print(f'already applied ({len(want)} fixed items, {len(fan_pads)} fan-out pads)')
        return
    if present:
        raise SystemExit(f'partial state: {len(present)} of {len(want)} planned items present, stop')
    if have_tracks or have_zones:
        raise SystemExit(f'the board already has {len(have_tracks)} tracks/vias and {len(have_zones)} zones '
                         'that are not this script\'s: stop')
    before = rl.PCB.read_text(encoding='utf-8')
    apply_fixed(board, items)
    added = fanout(board, items)
    print(f'fixed items: {len(items)}; GND fan-out vias: {len(added)}')
    for ref, num, c, v in added:
        print(f'  {ref}.{num}: via at ({v[0]:.2f}, {v[1]:.2f}), stub {math.hypot(v[0]-c[0], v[1]-c[1]):.2f} mm')
    rl.backup()
    rl.save(board, before, NAMESPACE)
    rl.refill()
    text = rl.PCB.read_text(encoding='utf-8')
    rl.PCB.write_text(rl.reseed_uuids(text, rl.uuids_in(before), NAMESPACE), encoding='utf-8', newline='')
    rl.check_fixed()


if __name__ == '__main__':
    main()
