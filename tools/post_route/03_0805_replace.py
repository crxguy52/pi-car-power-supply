"""03: 0805 footprint swap and re-placement of every movable part (placement phase, SPEC 5/6/7; overnight 2026-11-04).

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/03_0805_replace.py`):

- swap: exports the schematic netlist (01's helpers) and replaces every footprint whose schematic footprint changed
  from 1206 to 0805 HandSolder (tools/post_sch/02_0805_footprints.py: exactly SWAPPED) with a fresh library copy at
  the same position/orientation, keeping the fields, Path, Sheetname/Sheetfile and pad nets (01's apply_fields and
  netlist nets; uuids reseeded with 01's uuid5 scheme, so the result equals what 01 would write). Any other
  footprint/schematic difference stops the script (run 01 for that);
- place: every part except the fixed ones (J1, J2, J4, J5, MH1-MH4) has a planned target in TARGETS. The anchors
  (TARGETS up to N_ANCHORS_AFTER: buck, power path, SW1, C12, C26, U4/C9) are legalized first, in order, by a
  staged courtyard legalizer (02's search: GAP_MM within NEAR_SHIFT_MM, then MIN_GAP_MM, then further out). The
  other parts are then (1) spread by seeded simulated annealing from their targets with soft courtyard constraints,
  (2) legalized largest courtyard first, (3) improved by annealing with hard constraints (>= GAP_MM). Cost: net
  half-perimeters over pads (GND excluded: bottom pour + vias; power nets weighted), RULES (pad pairs kept close:
  decoupling, gate network, J5 series resistor, buck FB/COMP/EN/SS at their pins) and the distance from TARGETS
  (keeps the planned clusters). ANALOG parts stay left of ANALOG_MAX_X_MM. All parts top side. Every part must land
  on the board: the script stops (saves nothing) if one doesn't. Seeded: same inputs, same result;
- silkscreen: references on F.SilkS where free (02's place_refs, else F.Fab only: listed), J1/J4/J5 pin names kept.

Why: at 1206 the board was full (02 parked R11/D1/D4/D5 off-board; DECISIONS 2026-11-04 "Small-signal passives
1206 -> 0805"). With 31 passives at 0805 every part fits, at >= GAP_MM courtyard gaps where the legalizer finds
them (hand soldering), and with room left for routing. This script supersedes 02's TARGETS (02's own placement is
the agent's work, not the lead's; 02 is now historical: a re-run of 02 would undo this placement).

Layout (left -> right; top = GPIO header edge), SLVSCD5D 10.1 and SPEC 5 "Buck layout":
- buck along the top next to J2, as 02: U8 rotated 180 deg (power pins GND/PH/VIN/BOOT toward L1, VSENSE/COMP/EN/SS
  away from the switch node); C17 at VIN/GND between U8 and L1; C15 under the BOOT pin, VIN pad up (fed from pin 2
  via C17's VIN pad); C18 left of C15 under the U8 body; C16 below them; FB divider between J5 and U8, EN/SS/COMP
  below-left of U8 (away from L1 and the PH node); C22-C24 and C25 under L1 next to the J2 VBUS pins;
- power path on the right in front of J1: TVS1/TVS2 (anodes at the J1 GND pin), C11, D5 at ACC_IN; Q1 below them
  with its source next to J1 BATT and its tab (VOUT) toward the board centre; R14/C13 under the Q1 gate pin, DZ2
  between Q1 and C12, R15/C14 above C12 (no room at the gate pin: Q1_G is a slow node); C12 (VOUT bulk, tall) at
  the bottom centre, not in front of a terminal. The strip under Q1 is left for the VOUT path to J4 pin 1 (or a
  bottom-layer VOUT strip: routing phase);
- logic (the TARGETS plan: the annealing moves these non-anchor parts by up to about 2 cm where that shortens nets
  (D6, R6 and C2 moved most); the run prints each part's distance from its target):
  J5 status (Q4, R6/R7/C3, R21) at J5, C3 at the Q4 gate (RULES); timer U4 with C9 at pins 8/1, R22 at pins 2/6, C4 at pin 5, C5/C6/R9/D6 on
  C5_T; comparator U3 with R4/R5/R8/R11/R12/C8 around it; OR network (D1, D2, R1, R2, C2) and Q2 between the timer
  and Q1; logic supply R13/DZ1/C7; LED D3/R3 and SW1 (top-actuated slide; nothing tall next to it) + D4 at the
  bottom edge.
- terminal wire entries (TODO 4): the strips in front of J1 (-x side) and J5 (+y side) carry only low SMD parts
  (no electrolytic or inductor); J4's entry faces J1 or the board edge (lead decision pending).

Guards: stops on KiCad lock files, on a footprint/schematic difference other than SWAPPED, on a missing or extra
footprint, on a bottom-side part, if a part can't be placed, if a fixed item would move (tools/check_fixed.py must
PASS afterwards). Idempotent: the swap is skipped where the board already has the 0805 footprint, and the placement
depends only on TARGETS, so a re-run on the applied board prints "already applied" and saves nothing.
Backup to pi_power_board-backups/ before saving.
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


upd = _load('post_route_01', '01_update_from_schematic.py')     # netlist, library load, fields, uuid reseed
plc = _load('post_route_02', '02_placement.py')                 # courtyard legalizer, silk references, pin labels

STEM = 'pi_power_board'
PCB = ROOT / f'{STEM}.kicad_pcb'
BACKUPS = ROOT / f'{STEM}-backups'

FIXED = plc.FIXED
R_1206 = 'Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder'
C_1206 = 'Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder'
R_0805 = 'Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder'
C_0805 = 'Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder'
SWAP_FROM_TO = {R_1206: R_0805, C_1206: C_0805}
SWAPPED = set(('R1 R2 R3 R4 R5 R6 R7 R8 R9 R11 R12 R14 R15 R16 R17 R18 R19 R20 R22 '
               'C2 C3 C4 C7 C8 C9 C13 C17 C18 C19 C20 C21').split())

GAP_MM = 0.5                 # courtyard-to-courtyard target (hand soldering)
MIN_GAP_MM = 0.25            # fallback where the target gap can't be had
LAST_GAP_MM = 0.1            # last resort
NEAR_SHIFT_MM = 2.0          # first search radius: a part stays this close to its target at a smaller gap
STEP_MM = plc.STEP_MM
MAX_SHIFT_MM = plc.MAX_SHIFT_MM
ROT_PENALTY_MM = plc.ROT_PENALTY_MM
POS_TOL_NM = 1000

# placement after the anchors (seeded, reproducible): (1) spread = simulated annealing of the non-anchor parts from
# their TARGETS with soft constraints (courtyard overlap at GAP_MM and area off the board penalised, the weight
# ramping up), low temperature so the planned clusters stay; (2) the staged legalizer, largest courtyard first;
# (3) improve = the same annealing with hard constraints (every move keeps >= GAP_MM). Cost = net half-perimeters
# over pad positions (GND excluded: bottom pour + vias), power nets weighted, plus RULES as pad-to-pad distances.
ANNEAL_SEED = 1
SPREAD_ITERS = 400000
SPREAD_T0_MM = 1.0
SPREAD_T1_MM = 0.02
SPREAD_MAX_STEP_MM = 4.0
SPREAD_PENALTY0 = 0.5          # per mm2 of overlap, at the start
SPREAD_PENALTY1 = 2.0e3        # at the end (overlaps ~0 before the legalizer)
SPREAD_AREA_WEIGHT = 4.0       # off-board and ANALOG keep-left area, relative to courtyard overlap
ANNEAL_ITERS = 100000
ANNEAL_T0_MM = 0.5
ANNEAL_T1_MM = 0.01
ANNEAL_MAX_STEP_MM = 2.0
ANNEAL_MIN_STEP_MM = 0.25
ANNEAL_SWAP_SHARE = 0.25
ANNEAL_ROT_SHARE = 0.2
GRID_MM = 0.05
# buck analog parts (VSENSE/COMP/EN/SS networks) stay left of this x: U8's analog pins face -x, L1 and the PH
# node are on the +x side (SLVSCD5D 10.1)
ANALOG = ('R16', 'R17', 'R18', 'C19', 'C20', 'C21', 'R19', 'R20')
ANALOG_MAX_X_MM = 152.3
EXCLUDED_NETS = ('GND',)
NET_WEIGHT = {'/BATT': 2.0, '/VOUT': 2.0, '/+5V1': 2.0}
RULE_WEIGHT = 3.0
TARGET_WEIGHT = 1.0          # per mm (Manhattan) from the part's TARGETS position
# placement rules (SPEC 7 notes, SLVSCD5D 10.1): pad pairs kept close
RULES = [
    (('R22', '2'), ('U4', '2')), (('C4', '1'), ('U4', '5')),
    (('C8', '1'), ('U3', '5')), (('C8', '2'), ('U3', '2')),
    (('R21', '2'), ('J5', '2')), (('D5', '2'), ('TVS2', '1')), (('Q4', '3'), ('R21', '1')),
    (('R17', '1'), ('U8', '5')), (('R16', '2'), ('U8', '5')), (('R18', '1'), ('U8', '6')),
    (('C21', '1'), ('U8', '6')), (('R20', '1'), ('U8', '7')), (('C19', '1'), ('U8', '8')),
    (('R15', '1'), ('Q1', '1')), (('DZ2', '2'), ('Q1', '1')), (('C14', '1'), ('Q1', '1')), (('R15', '2'), ('Q2', '3')),
    (('D4', '2'), ('SW1', '1')), (('R3', '1'), ('D3', '1')), (('R13', '2'), ('DZ1', '1')),
    (('C3', '1'), ('Q4', '1')),      # STAT_G filter at the Q4 gate (staff review)
]
N_ANCHORS_AFTER = 'C9'       # TARGETS up to this ref: anchors, legalized in this order and then kept

# placement order = priority; (ref, x, y, rot, may_rotate), mm / deg. The lead's positions (02 LEAD) are the
# targets of R1/R2/R3/R6/R7/C2/C3/D3 and U4 (old circuit; kept where the new one allows)
LEAD = plc.LEAD
TARGETS = [
    # buck (SLVSCD5D 10.1): U8 and L1 as 02; C17 (0805) centred between U8 and L1; C15 (10 uF) right under the
    # BOOT pin with its VIN pad up (VIN from pin 2 through C17's VIN pad: short input loop, staff review), C18 left
    # of it under the U8 body (BOOT trace between pad 9 and C15); C16 below them (not under the analog pins);
    # Cout C22-C24 and C25 under L1 at the J2 VBUS pins
    ('U8', 152.29, 71.4, 180, False), ('C17', 158.05, 71.4, 90, False), ('L1', 166.75, 72.1, 0, False),
    ('C15', 155.2, 77.1, 270, False), ('C18', 152.4, 77.3, 270, False), ('C16', 153.9, 81.55, 0, False),
    ('C22', 171.6, 80.67, 270, False), ('C23', 168.9, 80.67, 270, False), ('C24', 166.2, 80.67, 270, False),
    ('C25', 161.0, 82.9, 270, False),
    # power path: TVS1/TVS2 in front of J1 (anodes at the J1 GND pin), C11 next to them, Q1 source at J1 BATT;
    # under Q1 next to its gate pin: C13, R14
    ('TVS1', 172.4, 89.85, 90, False), ('TVS2', 167.3, 89.85, 90, False), ('C11', 160.4, 90.6, 90, False),
    ('Q1', 166.8, 98.64, 180, False), ('R14', 170.6, 104.4, 0, False), ('C13', 165.5, 104.4, 0, False),
    # SW1 at the bottom edge (top-actuated slide), the tall C12 at the bottom centre, C26 (port 2 bulk)
    ('SW1', 140.0, 103.1, 0, False), ('C12', 151.5, 101.4, 180, False), ('C26', 153.3, 88.0, 270, False),
    # timer core: U4 at the lead's position, C9 across pins 8/1 (shortest supply loop)
    ('U4', *LEAD['U4'], False), ('C9', 133.86, 78.95, 180, False),
    # Q1 gate: DZ2 (G-S clamp) between C12 and Q1, R15 and C14 above C12
    ('DZ2', 160.0, 100.5, 90, True), ('R15', 159.6, 94.3, 0, True), ('C14', 155.2, 94.4, 0, True),
    # J5 status (Q4 drain -> R21 -> J5 pin 2) in front of J5's wire entry (low parts only); STAT_G divider in the
    # top-left tab
    ('Q4', 139.9, 78.85, 90, True), ('R21', 143.2, 78.0, 90, True), ('R6', 130.5, 70.0, 90, True),
    ('R7', 133.0, 70.0, 90, True), ('C3', 130.5, 74.3, 90, True),
    # buck analog: FB divider between J5 and U8, EN/SS/COMP below-left of U8 (away from L1 and PH)
    ('R16', 146.62, 69.4, 270, False), ('R17', 146.62, 73.7, 270, False), ('R20', 148.3, 76.6, 0, True),
    ('C19', 148.0, 79.0, 0, True), ('R18', 148.0, 81.5, 0, True), ('C21', 144.4, 82.7, 90, True),
    ('C20', 145.5, 85.9, 0, True), ('R19', 145.5, 79.0, 90, True),
    # timer: R22 at pins 2/6, C4 at pin 5, C5_T cluster (C5, C6, R9, D6) below U4
    ('R22', 128.6, 83.06, 90, True), ('C4', 140.0, 85.0, 0, True), ('C5', 131.0, 87.6, 0, True),
    ('C6', 131.0, 90.4, 0, True), ('R9', 136.0, 87.3, 0, True), ('D6', 136.8, 90.6, 0, True),
    # comparator U3 with C8, R12 (CMP_OUT -> C5_T), VOUT divider R4/R5, ACC divider R11/R8
    ('U3', 143.8, 89.8, 0, True), ('C8', 143.8, 93.3, 0, True), ('R12', 140.0, 91.5, 90, True),
    ('R4', 147.9, 88.3, 90, True), ('R5', 147.9, 92.6, 90, True), ('R11', 148.6, 96.0, 0, True),
    ('R8', 144.6, 95.6, 0, True),
    # ACC sense diode at TVS2 (anode at ACC_IN)
    ('D5', 163.2, 91.0, 270, True),
    # OR network (D2 from U4 pin 3, D1 from ACC_S, R2 -> DRV_G) and Q2 at the left, toward R15
    ('D2', 128.8, 96.0, 90, True), ('D1', 131.7, 96.0, 90, True), ('R2', 134.5, 96.5, 90, True),
    ('R1', 137.0, 96.5, 90, True), ('C2', 139.0, 94.2, 0, True), ('Q2', 141.0, 97.9, 0, True),
    # logic supply (from VOUT through R13), LED, ACC sense diode from SW1
    ('DZ1', 132.5, 100.7, 0, True), ('R13', 135.0, 93.6, 0, True), ('C7', 128.6, 91.3, 90, True),
    ('D3', 129.5, 104.6, 0, True), ('R3', 134.6, 104.6, 0, True), ('D4', 143.8, 103.1, 90, True),
]


def legalize(local, x, y, rot, may_rotate, placed, offsets, max_x=math.inf):
    """Nearest legal (x, y, rot, gap): 02's search, staged so that a part keeps its target neighbourhood at a
    smaller gap before it moves far for a larger one. Stages (gap, radius): GAP and MIN_GAP within NEAR_SHIFT_MM,
    then GAP, MIN_GAP and LAST_GAP anywhere in `offsets`."""
    rots = [rot] + ([(rot + 90) % 360] if may_rotate else [])
    stages = [(GAP_MM, NEAR_SHIFT_MM), (MIN_GAP_MM, NEAR_SHIFT_MM), (GAP_MM, math.inf), (MIN_GAP_MM, math.inf),
              (LAST_GAP_MM, math.inf)]
    for g, radius in stages:
        best = None
        for r in rots:
            pen = 0.0 if r == rot else ROT_PENALTY_MM
            lb = local[r]
            for dx, dy in offsets:
                d = math.hypot(dx, dy)
                if d > radius or (best is not None and d + pen >= best[0]):
                    break
                bx = (lb[0] + x + dx, lb[1] + y + dy, lb[2] + x + dx, lb[3] + y + dy)
                if not plc.allowed(bx) or bx[2] > max_x:
                    continue
                if all(plc.separated(bx, o, g - 1e-9) for o in placed):
                    best = (d + pen, x + dx, y + dy, r)
                    break
        if best is not None:
            return best[1], best[2], best[3], g
    return None


def plan(targets, local, obstacles, near, far):
    """02's plan() with this script's legalizer and the ANALOG keep-left limit. ({ref: (x, y, rot, gap)}, failed)."""
    placed = list(obstacles)
    out, failed = {}, []
    for ref, x, y, rot, may_rotate in targets:
        max_x = ANALOG_MAX_X_MM if ref in ANALOG else math.inf
        res = legalize(local[ref], x, y, rot, may_rotate, placed, near, max_x)
        if res is None:
            res = legalize(local[ref], x, y, rot, True, placed, far, max_x)
        if res is None:
            failed.append(ref)
            continue
        out[ref] = res
        placed.append(plc.box_at(local[ref][res[2]], res[0], res[1]))
    return out, failed


def snap(v):
    return round(v / GRID_MM) * GRID_MM


def _overlap(a, b, g):
    """Overlap area of box a grown by g with box b (mm2)."""
    w = min(a[2] + g, b[2]) - max(a[0] - g, b[0])
    h = min(a[3] + g, b[3]) - max(a[1] - g, b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _inter(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _off_board(b):
    """Courtyard area outside the allowed area (union of plc.BODY and plc.LEFT_TABS), mm2."""
    both = (max(plc.BODY[0], plc.LEFT_TABS[0]), max(plc.BODY[1], plc.LEFT_TABS[1]),
            min(plc.BODY[2], plc.LEFT_TABS[2]), min(plc.BODY[3], plc.LEFT_TABS[3]))
    inside = _inter(b, plc.BODY) + _inter(b, plc.LEFT_TABS) - _inter(b, both)
    return (b[2] - b[0]) * (b[3] - b[1]) - inside


class Wire:
    """Cost of a placement: weighted net half-perimeters over pads + RULES distances + distance of each moving
    part from its TARGETS position (keeps the planned clusters)."""

    def __init__(self, pos, padoff, fixed_pads, nets, targets):
        self.pos, self.padoff, self.fixed_pads, self.targets = pos, padoff, fixed_pads, targets
        self.nodes = {n: v for n, v in nets.items() if n not in EXCLUDED_NETS and len(v) > 1}
        self.by_ref = {}
        for n, v in self.nodes.items():
            for ref, _p in v:
                self.by_ref.setdefault(ref, set()).add(('net', n))
        for i, (a, b) in enumerate(RULES):
            self.by_ref.setdefault(a[0], set()).add(('rule', i))
            self.by_ref.setdefault(b[0], set()).add(('rule', i))
        for r in targets:
            self.by_ref.setdefault(r, set()).add(('tgt', r))

    def pad_xy(self, ref, pad):
        if ref in self.pos:
            x, y, rot = self.pos[ref]
            ox, oy = self.padoff[ref][rot][pad]
            return x + ox, y + oy
        return self.fixed_pads[(ref, pad)]

    def term(self, k):
        kind, key = k
        if kind == 'net':
            pts = [self.pad_xy(r, p) for r, p in self.nodes[key]]
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            return NET_WEIGHT.get(key, 1.0) * ((max(xs) - min(xs)) + (max(ys) - min(ys)))
        if kind == 'tgt':
            (x, y, _r), (tx, ty) = self.pos[key], self.targets[key]
            return TARGET_WEIGHT * (abs(x - tx) + abs(y - ty))
        (ra, pa), (rb, pb) = RULES[key]
        (xa, ya), (xb, yb) = self.pad_xy(ra, pa), self.pad_xy(rb, pb)
        return RULE_WEIGHT * (abs(xa - xb) + abs(ya - yb))

    def keys(self, refs):
        """Cost terms touching `refs`, sorted: a fixed summation order keeps the run reproducible (string hashes
        are randomised per process)."""
        return sorted(set().union(*(self.by_ref.get(r, set()) for r in refs)))

    def total(self):
        return sum(self.term(k) for k in self.keys(self.by_ref))


def spread(start, refs, local, padoff, fixed_pads, static, nets, targets):
    """Seeded annealing of `refs` from `start` ({ref: (x, y, rot)}) with soft courtyard constraints against each
    other and the `static` boxes (fixed parts, anchors). Returns {ref: (x, y, rot)}: targets for the legalizer."""
    import random
    rnd = random.Random(ANNEAL_SEED)
    pos = {r: list(v) for r, v in start.items()}
    wire = Wire(pos, padoff, fixed_pads, nets, targets)
    refs = sorted(refs)

    def boxof(r, v):
        return plc.box_at(local[r][v[2]], v[0], v[1])
    box = {r: boxof(r, pos[r]) for r in refs}

    def pen(r, b, skip):
        s = _off_board(b) * SPREAD_AREA_WEIGHT
        if r in ANALOG and b[2] > ANALOG_MAX_X_MM:
            s += (b[2] - ANALOG_MAX_X_MM) * (b[3] - b[1]) * SPREAD_AREA_WEIGHT
        s += sum(_overlap(b, o, GAP_MM) for o in static)
        s += sum(_overlap(b, box[o], GAP_MM) for o in refs if o != r and o not in skip)
        return s

    for it in range(SPREAD_ITERS):
        frac = it / SPREAD_ITERS
        temp = SPREAD_T0_MM * (SPREAD_T1_MM / SPREAD_T0_MM) ** frac
        lam = SPREAD_PENALTY0 * (SPREAD_PENALTY1 / SPREAD_PENALTY0) ** frac
        step = max(ANNEAL_MIN_STEP_MM, SPREAD_MAX_STEP_MM * (1.0 - frac))
        a = refs[rnd.randrange(len(refs))]
        if rnd.random() < ANNEAL_SWAP_SHARE:
            b = refs[rnd.randrange(len(refs))]
            if b == a:
                continue
            new = {a: [pos[b][0], pos[b][1], pos[a][2]], b: [pos[a][0], pos[a][1], pos[b][2]]}
        else:
            rot = pos[a][2]
            if rnd.random() < ANNEAL_ROT_SHARE:
                rot = (rot + 90 * rnd.randrange(1, 4)) % 360
            new = {a: [snap(pos[a][0] + rnd.uniform(-step, step)), snap(pos[a][1] + rnd.uniform(-step, step)), rot]}
        nbox = {r: boxof(r, v) for r, v in new.items()}
        skip = tuple(new)
        old_pen = sum(pen(r, box[r], skip) for r in new)
        new_pen = sum(pen(r, nbox[r], skip) for r in new)
        if len(new) == 2:
            old_pen += _overlap(box[a], box[b], GAP_MM)
            new_pen += _overlap(nbox[a], nbox[b], GAP_MM)
        keys = wire.keys(new)
        old_cost = sum(wire.term(k) for k in keys) + lam * old_pen
        saved = {r: pos[r] for r in new}
        pos.update(new)
        delta = sum(wire.term(k) for k in keys) + lam * new_pen - old_cost
        if delta <= 0 or rnd.random() < math.exp(-delta / temp):
            box.update(nbox)
        else:
            pos.update(saved)
    return {r: tuple(pos[r]) for r in refs}


def improve(result, movable_refs, local, padoff, fixed_pads, obstacles, nets, targets):
    """Seeded annealing of `movable_refs` on the legalized `result` ({ref: (x, y, rot, gap)}) with hard
    constraints (every move keeps >= GAP_MM, ANALOG keep-left); every other part stays.
    Returns (new result, final cost); gap = smallest courtyard gap of the part."""
    import random
    rnd = random.Random(ANNEAL_SEED)
    pos = {r: [v[0], v[1], v[2]] for r, v in result.items()}
    box = {r: plc.box_at(local[r][pos[r][2]], pos[r][0], pos[r][1]) for r in pos}
    refs = sorted(movable_refs)
    wire = Wire(pos, padoff, fixed_pads, nets, targets)

    def legal(ref, b, skip):
        if not plc.allowed(b) or (ref in ANALOG and b[2] > ANALOG_MAX_X_MM):
            return False
        if not all(plc.separated(b, o, GAP_MM - 1e-9) for o in obstacles):
            return False
        return all(plc.separated(b, box[o], GAP_MM - 1e-9) for o in box if o != ref and o not in skip)

    for it in range(ANNEAL_ITERS):
        frac = it / ANNEAL_ITERS
        temp = ANNEAL_T0_MM * (ANNEAL_T1_MM / ANNEAL_T0_MM) ** frac
        step = max(ANNEAL_MIN_STEP_MM, ANNEAL_MAX_STEP_MM * (1.0 - frac))
        a = refs[rnd.randrange(len(refs))]
        if rnd.random() < ANNEAL_SWAP_SHARE:
            b = refs[rnd.randrange(len(refs))]
            if b == a:
                continue
            new = {a: [pos[b][0], pos[b][1], pos[a][2]], b: [pos[a][0], pos[a][1], pos[b][2]]}
        else:
            rot = pos[a][2]
            if rnd.random() < ANNEAL_ROT_SHARE:
                rot = (rot + 90 * rnd.randrange(1, 4)) % 360
            new = {a: [snap(pos[a][0] + rnd.uniform(-step, step)), snap(pos[a][1] + rnd.uniform(-step, step)), rot]}
        nbox = {r: plc.box_at(local[r][v[2]], v[0], v[1]) for r, v in new.items()}
        if not all(legal(r, nbox[r], tuple(new)) for r in new):
            continue
        if len(new) == 2 and not plc.separated(nbox[a], nbox[b], GAP_MM - 1e-9):
            continue
        keys = wire.keys(new)
        old_cost = sum(wire.term(k) for k in keys)
        saved = {r: pos[r] for r in new}
        pos.update(new)
        delta = sum(wire.term(k) for k in keys) - old_cost
        if delta <= 0 or rnd.random() < math.exp(-delta / temp):
            box.update(nbox)
        else:
            pos.update(saved)
    out = {}
    for r, (x, y, rot) in pos.items():
        others = [box[o] for o in box if o != r] + list(obstacles)
        out[r] = (x, y, rot, round(min(plc.gap(box[r], o) for o in others), 3))
    return out, wire.total()


def swap_footprints(board, fps):
    """Replace the SWAPPED footprints still on 1206 with their 0805 schematic footprint. Returns the swapped refs
    and the removed footprints (kept referenced until the save: lessons doc, KiCad 10 SWIG)."""
    upd.export_netlist()
    comps, pin_net = upd.read_netlist()
    linked = {r for r in fps if not upd.UNLINKED_OK.match(r)}
    if linked != set(comps):
        raise SystemExit(f'board vs schematic: missing {sorted(set(comps) - linked)}, extra {sorted(linked - set(comps))}'
                         ': run 01 first')
    todo = [r for r in sorted(comps) if not upd.fp_matches(fps[r], comps[r], pin_net)]
    unexpected = [r for r in todo if r not in SWAPPED
                  or SWAP_FROM_TO.get(fps[r].GetFPIDAsString()) != comps[r]['footprint']]
    if unexpected:
        raise SystemExit(f'footprint/field/net differences outside the 0805 swap: {unexpected}: run 01 or check')
    nets = {n: board.FindNet(n) for n in set(pin_net.values())}
    if any(v is None for v in nets.values()):
        raise SystemExit('a netlist net is missing on the board: run 01 first')
    removed = []
    for ref in todo:
        comp, old = comps[ref], fps[ref]
        fp = upd.load_lib_fp(comp['footprint'])
        fp.SetParent(board)
        upd.apply_fields(fp, ref, comp, upd.want_path(comp, old))
        fp.SetOrientation(old.GetOrientation())
        fp.SetPosition(old.GetPosition())
        fp.SetLocked(old.IsLocked())
        for p in fp.Pads():
            net = pin_net.get((ref, p.GetNumber()))
            if net is None:
                raise SystemExit(f'{ref}: pad {p.GetNumber()} not in the netlist')
            p.SetNet(nets[net])
        removed.append(old)
        board.Remove(old)
        board.Add(fp)
        fps[ref] = fp
    return todo, removed


def main():
    locks = sorted(ROOT.glob('~*.lck'))
    if locks:
        raise SystemExit(f'KiCad lock files present ({[p.name for p in locks]}): close KiCad first')
    board = pcbnew.LoadBoard(str(PCB))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    movable = set(fps) - set(FIXED)
    target_refs = [t[0] for t in TARGETS]
    if len(set(target_refs)) != len(target_refs) or set(target_refs) != movable:
        raise SystemExit(f'TARGETS vs board: missing {sorted(movable - set(target_refs))}, '
                         f'extra {sorted(set(target_refs) - movable)}')
    if any(fps[r].IsFlipped() for r in movable):
        raise SystemExit('a movable part is on the bottom side: unexpected')
    fixed_before = {r: (fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees())
                    for r in FIXED}

    swapped, _removed = swap_footprints(board, fps)
    print(f'swapped to 0805: {swapped or "none (already applied)"}')
    before = {r: (fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees()) for r in fps}
    refs_before = plc.ref_state(fps)

    obstacles = [plc.crt_box(fps[r]) for r in FIXED] + list(plc.LABEL_STRIPS)
    local, padoff = {}, {}
    for ref, *_ in TARGETS:
        pos, ori = fps[ref].GetPosition(), fps[ref].GetOrientationDegrees()
        local[ref], padoff[ref] = {}, {}
        for r in (0, 90, 180, 270):
            fps[ref].SetOrientationDegrees(r)
            fps[ref].SetPosition(pcbnew.VECTOR2I(0, 0))
            local[ref][r] = plc.crt_box(fps[ref])
            padoff[ref][r] = {p.GetNumber(): (p.GetPosition().x / 1e6, p.GetPosition().y / 1e6)
                              for p in fps[ref].Pads()}
        fps[ref].SetOrientationDegrees(ori)
        fps[ref].SetPosition(pos)
    fixed_pads = {(r, p.GetNumber()): (p.GetPosition().x / 1e6, p.GetPosition().y / 1e6)
                  for r in FIXED for p in fps[r].Pads()}
    nets = {}
    for ref, f in sorted(fps.items()):
        for p in f.Pads():
            name = p.GetNetname()
            if name and not name.startswith('unconnected-'):
                nets.setdefault(name, []).append((ref, p.GetNumber()))
    nets = {k: sorted(set(v)) for k, v in nets.items()}
    n = target_refs.index(N_ANCHORS_AFTER) + 1

    def area(t):
        b = local[t[0]][0]
        return (b[2] - b[0]) * (b[3] - b[1])
    near, far = plc.candidates(), plc.candidates(plc.FAR_SHIFT_MM, plc.FAR_STEP_MM)
    anchors, failed = plan(TARGETS[:n], local, obstacles, near, far)
    if failed:
        raise SystemExit(f'NOT PLACED (no legal spot on the board): {failed}: nothing saved')
    static = obstacles + [plc.box_at(local[r][v[2]], v[0], v[1]) for r, v in anchors.items()]
    start = {t[0]: (t[1], t[2], t[3]) for t in TARGETS[n:]}
    start.update({r: v[:3] for r, v in anchors.items()})
    tgt_xy = {t[0]: (t[1], t[2]) for t in TARGETS[n:]}
    spread_pos = spread(start, target_refs[n:], local, padoff, fixed_pads, static, nets, tgt_xy)
    order = sorted([(r, x, y, rot, True) for r, (x, y, rot) in spread_pos.items()], key=lambda t: -area(t))
    rest, failed = plan(order, local, static, near, far)
    if failed:
        raise SystemExit(f'NOT PLACED (no legal spot on the board): {failed}: nothing saved')
    result = dict(anchors)
    result.update(rest)
    result, cost = improve(result, target_refs[n:], local, padoff, fixed_pads, obstacles, nets, tgt_xy)
    print(f'weighted wire length after annealing: {cost:.1f} mm')

    tgt = {t[0]: t for t in TARGETS}
    log = []
    for ref, (px, py, pr, g) in result.items():
        fps[ref].SetOrientationDegrees(pr)
        fps[ref].SetPosition(pcbnew.VECTOR2I(plc.mm(px), plc.mm(py)))
        _, x, y, rot, _m = tgt[ref]
        log.append((ref, px, py, pr, g, math.hypot(px - x, py - y), pr != rot))
    labels = plc.add_pin_labels(board)
    fab_only = plc.place_refs(board, target_refs + [r for r in FIXED if r[0] == 'J'])
    after = {r: (fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees()) for r in fps}
    if any(fixed_before[r] != after[r] for r in FIXED):
        raise SystemExit('a fixed footprint moved: not saved')

    moved = [r for r in movable if abs(before[r][0] - after[r][0]) > POS_TOL_NM
             or abs(before[r][1] - after[r][1]) > POS_TOL_NM or before[r][2] != after[r][2]]
    gaps = {}
    for ref, px, py, pr, g, d, turned in sorted(log):
        gaps[g] = gaps.get(g, 0) + 1
        note = []
        if d > 1e-6 or turned:
            note.append(f'moved {d:.2f} mm from target' + (', turned 90' if turned else ''))
        if g < GAP_MM:
            note.append(f'gap {g} mm')
        print(f'  {ref:5s} ({px:8.3f}, {py:8.3f}) rot {pr:5.0f}  {"; ".join(note)}')
    print(f'parts per courtyard gap (mm): {dict(sorted(gaps.items(), reverse=True))}')
    print(f'references on F.Fab only (no free silk spot): {fab_only or "none"}')
    if not swapped and not moved and not labels and plc.ref_state(fps) == refs_before:
        print('already applied: 0805 footprints on the board, every part at its legalized position; nothing saved')
        return
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_pcb'
    shutil.copy2(PCB, backup)
    print(f'backup {backup.relative_to(ROOT)}')
    pcbnew.SaveBoard(str(PCB), board)
    text = PCB.read_text(encoding='utf-8')
    text = upd.reseed_uuids(text, set(swapped))
    PCB.write_text(plc.seed_label_uuids(text), encoding='utf-8', newline='')
    pcbnew.SaveBoard(str(PCB), pcbnew.LoadBoard(str(PCB)))     # order by the seeded uuids
    print(f'swapped {len(swapped)}, placed {len(moved)} parts, {labels} pin labels added')


if __name__ == '__main__':
    main()
