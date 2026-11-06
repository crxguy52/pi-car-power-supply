"""02: place every footprint that isn't fixed (placement phase, SPEC 5 "Board", SLVSCD5D 10.1; overnight run 2026-11-04).

What (KiCad python, from the project root: `python.exe -I tools/post_route/02_placement.py`):

- every part except the fixed ones (J1, J2, J4, J5, MH1-MH4: tools/check_fixed.py) gets a target position and
  rotation from TARGETS, in TARGETS order (priority); a legalizer then moves each part to the nearest spot (grid
  STEP_MM, radius MAX_SHIFT_MM) where its courtyard is inside the allowed board area, clear of the fixed parts, the
  silk label strips of J4/J5 and every part placed before it by >= GAP_MM (fallback MIN_GAP_MM). All parts top side;
- the lead's positions (LEAD) are the targets of the parts the lead had placed; a part only leaves them where the
  new circuit needs the space (printed with the distance);
- silkscreen: each reference goes to the part centre (0.8 mm text) if it clears every pad and every other reference,
  else to the nearest free spot around the part, else to F.Fab only (printed); J1/J4/J5 get pin-name labels
  (board-level F.SilkS text, seeded uuids) because J4 and J5 carry GND on opposite pins (SPEC 7).

Why the layout is what it is (left -> right on the board, top = GPIO header side):
- buck along the top next to J2: U8 rotated 180 deg so its power pins (GND, PH, VIN, BOOT) face L1 and its analog
  pins (VSENSE, COMP, EN, SS) face away from the switch node, as SLVSCD5D figure 55 (mirrored); C17 (100 nF) right
  at VIN/GND between U8 and L1, C15/C16 and C18 (BOOT) just below the power pins; PH crosses to L1 under C17
  (bottom-layer SW copper, as the datasheet); C22-C24 at L1 pin 2 / J2 VBUS; C25/C26 next to them;
  FB/COMP/EN/SS parts left of U8, away from L1;
- power path down the right side: TVS1/TVS2 (vertical, anode at the J1 GND pin, cathode at BATT/ACC_IN) and C11
  in front of J1; Q1 below them, rotated 180 deg so its source pin is next to J1 BATT and its tab (VOUT) faces
  the board centre (pour room on both layers, C12 next to it); R14/C13 under Q1 next to its gate pin;
- logic on the left, at the lead's positions where they are still free: timer U4 + C9 across pins 8/1, J5
  status (R6/R7/C3, Q4, R21), OR network (D1/D2/R1/R2/C2), LED D3/R3; SW1 at the bottom edge (top-actuated slide,
  nothing tall next to it).

Guards: stops on lock files, on a missing or extra footprint, if a part can't be placed, if a fixed item would move
(tools/check_fixed.py must PASS afterwards). Idempotent: the result depends only on TARGETS, so a re-run on the
placed board changes nothing and saves nothing. Backup to pi_power_board-backups/ before saving.
"""
import datetime
import math
import random
import pathlib
import shutil
import sys
import uuid

import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[2]
STEM = 'pi_power_board'
PCB = ROOT / f'{STEM}.kicad_pcb'
BACKUPS = ROOT / f'{STEM}-backups'
UUID_NS = uuid.uuid5(uuid.NAMESPACE_URL, 'pi-car-power-supply/tools/post_route/02_placement')

FIXED = ('J1', 'J2', 'J4', 'J5', 'MH1', 'MH2', 'MH3', 'MH4')
GAP_MM = 0.25                # courtyard-to-courtyard target (the board is ~85 % full at this gap)
MIN_GAP_MM = 0.1             # fallback where the target gap can't be had
LAST_GAP_MM = 0.02           # last resort: courtyards just clear (DRC courtyards_overlap still 0)
ORDER_JITTER = 0.6
STEP_MM = 0.25
MAX_SHIFT_MM = 20.0
FAR_SHIFT_MM = 70.0          # second search for a part with no spot near its target
FAR_STEP_MM = 0.5
ROT_PENALTY_MM = 1.5         # prefer the target rotation over a 90 deg turn this close
POS_TOL_NM = 1000
N_ANCHORS_AFTER = 'C26'      # TARGETS up to this ref are anchors (never reordered)
PARK_X_MM, PARK_Y0_MM, PARK_PITCH_MM = 115.0, 70.0, 5.0     # parked (unplaceable) parts, off the board
FIRST_ORDER = 0              # the order that won on 2026-11-04 (tried first, so a re-run is quick)
MAX_ORDERS = 1             # 40 seeded orders were tried on 2026-11-04: none complete, order 0 the best (4 parked)

# allowed courtyard area: (x0, y0, x1, y1) mm; the main body inside Edge.Cuts with EDGE margin, left of the BACK
# HEADER KEEPOUT line, and the two left tabs below/above the mounting holes
EDGE_MARGIN_MM = 0.3
BODY = (127.0 + EDGE_MARGIN_MM, 66.04 + EDGE_MARGIN_MM, 185.17 - EDGE_MARGIN_MM, 106.43 - EDGE_MARGIN_MM)
LEFT_TABS = (127.0 + EDGE_MARGIN_MM, 64.9, 133.85 - EDGE_MARGIN_MM, 107.7)
# silk label strips kept free of parts: (x0, y0, x1, y1) mm
LABEL_STRIPS = [(173.6, 99.0, 175.0, 106.1)]     # J4 pin 2 (GND), left of J4

# J1/J4/J5 pin-name labels: (text, x, y, angle deg) mm; J1 and the J4 pin 1 label sit in the BACK HEADER strip
# (silk only, no parts)
PIN_LABELS = [('GND', 184.4, 87.63, 90.0), ('ACC', 184.4, 91.44, 90.0), ('BATT', 184.4, 95.25, 90.0),
              ('12V', 184.4, 102.235, 90.0), ('GND', 174.3, 102.235, 90.0),
              ('GND', 138.938, 66.65, 0.0), ('ACC_N', 142.748, 66.65, 0.0)]     # J5: between its body and the edge
LABEL_SIZE_MM = 0.8
LABEL_THICK_MM = 0.12
REF_SIZE_MM = 0.8
REF_THICK_MM = 0.12
PAD_CLEAR_MM = 0.15

# the lead's positions (board before this phase), mm / deg
LEAD = {
    'C2': (136.0170, 93.7260, 90), 'C3': (130.6570, 70.1040, 90), 'C4': (148.3125, 85.0900, 0),
    'C5': (142.2665, 85.3440, 0), 'D1': (150.6220, 93.5990, 0), 'D2': (143.1290, 93.7260, 180),
    'D3': (130.1750, 102.9970, 90), 'R1': (131.3330, 93.9500, 0), 'R2': (131.3330, 97.2400, 0),
    'R3': (134.1120, 102.9970, 90), 'R4': (165.2270, 85.3560, 0), 'R5': (165.2270, 88.6460, 0),
    'R6': (132.1810, 74.4220, 180), 'R7': (133.9590, 70.1040, 90), 'R8': (165.4810, 92.3290, 0),
    'R9': (143.6760, 81.1530, 0), 'U3': (159.6000, 86.3600, 0), 'U4': (133.8580, 83.0580, 0),
    'U8': (166.1160, 71.7550, 0),
}

# placement order = priority; (ref, x, y, rot, may_rotate)
TARGETS = [
    # buck (SLVSCD5D 10.1)
    ('U8', 152.29, 71.4, 180, False), ('C17', 158.0, 71.4, 90, False), ('L1', 166.75, 72.1, 0, False),
    ('C18', 155.1, 77.3, 270, False), ('C15', 152.2, 77.3, 90, False), ('C16', 149.3, 77.3, 90, False),
    ('C22', 171.5, 80.67, 270, False), ('C23', 168.6, 80.67, 270, False), ('C24', 165.7, 80.67, 270, False),
    ('C25', 160.4, 82.9, 270, False),
    # power path
    ('TVS1', 172.4, 89.85, 90, False), ('TVS2', 167.3, 89.85, 90, False), ('C11', 163.0, 90.67, 90, False),
    ('Q1', 167.0, 98.64, 180, False), ('R14', 170.5, 104.4, 0, True), ('C13', 165.0, 104.4, 0, True),
    ('C12', 155.5, 101.4, 180, False), ('C26', 153.2, 87.6, 270, True),
    # the lead's logic parts that keep their places
    ('U4', *LEAD['U4'], False), ('R6', *LEAD['R6'], False), ('R7', *LEAD['R7'], False),
    ('C3', *LEAD['C3'], False), ('R1', *LEAD['R1'], False), ('R2', *LEAD['R2'], False),
    ('C2', *LEAD['C2'], False), ('D3', *LEAD['D3'], False), ('R3', *LEAD['R3'], False),
    ('D2', *LEAD['D2'], False), ('D1', *LEAD['D1'], True), ('R9', *LEAD['R9'], True),
    # timer: C9 across U4 pins 8/1, R22 at pins 2/6, C4 at pin 5
    ('C9', 133.86, 78.81, 180, False), ('R22', 128.5, 83.06, 90, True), ('C4', 138.6, 83.0, 90, True),
    ('C5', *LEAD['C5'], True), ('C6', 142.3, 88.6, 0, True), ('D6', 129.2, 77.6, 0, True),
    # J5 status
    ('Q4', 139.4, 77.7, 0, True), ('R21', 145.0, 77.05, 0, True),
    # buck analog (VSENSE/COMP/EN/SS), below-left of U8, away from L1
    ('R16', 146.59, 71.0, 90, False), ('R17', 148.1, 86.3, 90, True), ('C19', 152.5, 81.27, 0, True),
    ('R18', 145.45, 85.1, 90, True), ('C20', 145.45, 90.4, 90, True), ('C21', 148.1, 91.6, 90, True),
    ('R19', 150.8, 93.5, 0, True), ('R20', 150.8, 96.0, 0, True),
    # Q1 gate network, Q2
    ('DZ2', 156.0, 94.3, 0, True), ('C14', 159.0, 92.0, 90, True), ('R15', 156.0, 91.5, 0, True),
    ('Q2', 140.5, 97.5, 0, True), ('D5', 159.2, 90.2, 0, True),
    # logic supply
    ('DZ1', 132.0, 89.0, 0, True), ('R13', 138.0, 89.5, 0, True), ('C7', 128.5, 89.5, 90, True),
    # comparator
    ('U3', 141.0, 91.0, 0, True), ('C8', 137.5, 91.5, 0, True), ('R4', 144.5, 95.5, 90, True),
    ('R5', 147.5, 98.0, 90, True), ('R11', 137.5, 100.0, 0, True), ('R8', 142.5, 100.5, 0, True),
    ('R12', 145.0, 100.5, 90, True),
    # SW1 (bottom edge) and the ACC sense diode from it
    ('SW1', 139.0, 103.5, 0, False), ('D4', 143.5, 104.5, 0, True),
]


def mm(v):
    return pcbnew.FromMM(v)


def crt_box(fp):
    """Courtyard bbox (x0, y0, x1, y1) in mm at the footprint's current position and rotation."""
    c = fp.GetCourtyard(pcbnew.F_CrtYd)
    b = c.BBox() if c.OutlineCount() else fp.GetBoundingBox(False)
    return (b.GetLeft() / 1e6, b.GetTop() / 1e6, b.GetRight() / 1e6, b.GetBottom() / 1e6)


def inside(box, area):
    return box[0] >= area[0] and box[1] >= area[1] and box[2] <= area[2] and box[3] <= area[3]


def allowed(box):
    return inside(box, BODY) or inside(box, LEFT_TABS)


def gap(a, b):
    """Clearance between two boxes (negative = overlap)."""
    dx = max(b[0] - a[2], a[0] - b[2])
    dy = max(b[1] - a[3], a[1] - b[3])
    if dx < 0 and dy < 0:
        return max(dx, dy)
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def candidates(radius=MAX_SHIFT_MM, step=STEP_MM):
    """Grid offsets sorted by distance (computed once)."""
    n = int(radius / step)
    out = [(i * step, j * step) for i in range(-n, n + 1) for j in range(-n, n + 1)
           if math.hypot(i, j) * step <= radius]
    out.sort(key=lambda d: (math.hypot(*d), d))
    return out


def box_at(local, x, y):
    return (local[0] + x, local[1] + y, local[2] + x, local[3] + y)


def separated(a, o, g):
    """True if boxes a and o are at least g apart along x or along y."""
    return a[0] >= o[2] + g or o[0] >= a[2] + g or a[1] >= o[3] + g or o[1] >= a[3] + g


def legalize(local, x, y, rot, may_rotate, placed, offsets):
    """Nearest legal (x, y, rot, gap) for a part with courtyard boxes `local` (per rotation, at the origin)."""
    rots = [rot] + ([(rot + 90) % 360] if may_rotate else [])
    for g in (GAP_MM, MIN_GAP_MM, LAST_GAP_MM):
        best = None
        for r in rots:
            pen = 0.0 if r == rot else ROT_PENALTY_MM
            lb = local[r]
            for dx, dy in offsets:
                d = math.hypot(dx, dy) + pen
                if best is not None and d >= best[0]:
                    break
                bx = (lb[0] + x + dx, lb[1] + y + dy, lb[2] + x + dx, lb[3] + y + dy)
                if not allowed(bx):
                    continue
                if all(separated(bx, o, g - 1e-9) for o in placed):
                    best = (d, x + dx, y + dy, r)
                    break
        if best is not None:
            return best[1], best[2], best[3], g
    return None


def plan(targets, local, obstacles, offsets, far):
    """Legalize targets in order. Returns ({ref: (x, y, rot, gap)}, [failed refs])."""
    placed = list(obstacles)
    out, failed = {}, []
    for ref, x, y, rot, may_rotate in targets:
        res = legalize(local[ref], x, y, rot, may_rotate, placed, offsets)
        if res is None:                 # nothing near the target: anywhere on the board, coarser grid
            res = legalize(local[ref], x, y, rot, True, placed, far)
        if res is None:
            failed.append(ref)
            continue
        out[ref] = res
        lb = local[ref][res[2]]
        placed.append((lb[0] + res[0], lb[1] + res[1], lb[2] + res[0], lb[3] + res[1]))
    return out, failed


def orders(local):
    """Placement orders to try. The anchors (buck, power path, the lead's kept parts) always go first, in TARGETS
    order. The rest go largest courtyard first (big parts are the hard ones to fit), then in seeded,
    reproducible shuffles of that order with the area jittered by up to ORDER_JITTER."""
    n = [t[0] for t in TARGETS].index(N_ANCHORS_AFTER) + 1
    head, tail = TARGETS[:n], TARGETS[n:]

    def area(t):
        b = local[t[0]][0]
        return (b[2] - b[0]) * (b[3] - b[1])
    for seed in [FIRST_ORDER] + [k for k in range(MAX_ORDERS) if k != FIRST_ORDER]:
        rnd = random.Random(seed)
        jit = {t[0]: (1.0 + ORDER_JITTER * rnd.random() if seed else 1.0) for t in tail}
        yield seed, head + sorted(tail, key=lambda t: -area(t) * jit[t[0]])


def text_box(t):
    b = t.GetBoundingBox()
    return (b.GetLeft() / 1e6, b.GetTop() / 1e6, b.GetRight() / 1e6, b.GetBottom() / 1e6)


def pad_boxes(board):
    out = []
    for f in board.GetFootprints():
        for p in f.Pads():
            b = p.GetBoundingBox()
            out.append((b.GetLeft() / 1e6 - PAD_CLEAR_MM, b.GetTop() / 1e6 - PAD_CLEAR_MM,
                        b.GetRight() / 1e6 + PAD_CLEAR_MM, b.GetBottom() / 1e6 + PAD_CLEAR_MM))
    return out


def silk_boxes(board):
    """(owner ref or None, bbox mm) of every F.SilkS graphic: footprint silk and board-level silk text."""
    out = []
    for f in board.GetFootprints():
        for g in f.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS and g.GetClass() != 'PCB_FIELD':
                b = g.GetBoundingBox()
                out.append((f.GetReference(), (b.GetLeft() / 1e6, b.GetTop() / 1e6, b.GetRight() / 1e6,
                                               b.GetBottom() / 1e6)))
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS:
            b = d.GetBoundingBox()
            out.append((None, (b.GetLeft() / 1e6, b.GetTop() / 1e6, b.GetRight() / 1e6, b.GetBottom() / 1e6)))
    return out


def ref_state(fps):
    """Reference text layer, position, angle and size per footprint (to detect a no-op re-run)."""
    return {r: (f.Reference().GetLayer(), f.Reference().GetPosition().x, f.Reference().GetPosition().y,
                f.Reference().GetTextAngleDegrees(), f.Reference().GetTextSize().x) for r, f in fps.items()}


def place_refs(board, refs):
    """Reference text: centre, then around the part; F.Fab only if nothing is free. Returns refs moved to Fab."""
    pads = pad_boxes(board)
    silk = silk_boxes(board)
    taken = [b for _r, b in silk if _r is None]      # board-level silk (pin labels)
    fab_only = []
    for ref in refs:
        fp = board.FindFootprintByReference(ref)
        t = fp.Reference()
        t.SetLayer(pcbnew.F_SilkS)
        t.SetVisible(True)
        t.SetTextSize(pcbnew.VECTOR2I(mm(REF_SIZE_MM), mm(REF_SIZE_MM)))
        t.SetTextThickness(mm(REF_THICK_MM))
        t.SetKeepUpright(True)
        c = fp.GetPosition()
        cb = crt_box(fp)
        w, h = cb[2] - cb[0], cb[3] - cb[1]
        rot = fp.GetOrientationDegrees()
        across = (rot + 90.0) % 180.0          # across the long axis of a two-pad part
        spots = [(0.0, 0.0, across), (0.0, 0.0, rot % 180.0)]
        for k in (0.5, 0.5 + REF_SIZE_MM):
            spots += [(0.0, -(h / 2 + k), 0.0), (0.0, h / 2 + k, 0.0), (-(w / 2 + k), 0.0, 90.0),
                      (w / 2 + k, 0.0, 90.0)]
        ok = False
        for dx, dy, ang in spots:
            t.SetTextAngleDegrees(ang)
            t.SetPosition(pcbnew.VECTOR2I(c.x + mm(dx), c.y + mm(dy)))
            tb = text_box(t)
            if not allowed(tb):
                continue
            if any(gap(tb, p) < 0 for p in pads) or any(gap(tb, o) < 0.1 for o in taken) or any(
                    gap(tb, b) < 0.05 for r, b in silk if r is not None):
                continue
            taken.append(tb)
            ok = True
            break
        if not ok:
            t.SetLayer(pcbnew.F_Fab)
            t.SetTextAngleDegrees(0.0)
            t.SetPosition(c)
            fab_only.append(ref)
    return fab_only


def add_pin_labels(board):
    """Board-level F.SilkS pin names at J1/J4/J5 (skipped if an identical label is already there)."""
    have = {(d.GetText(), d.GetPosition().x, d.GetPosition().y) for d in board.GetDrawings()
            if d.GetClass() == 'PCB_TEXT' and d.GetLayer() == pcbnew.F_SilkS}
    added = 0
    for i, (text, x, y, ang) in enumerate(PIN_LABELS):
        if (text, mm(x), mm(y)) in have:
            continue
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        t.SetTextAngleDegrees(ang)
        t.SetTextSize(pcbnew.VECTOR2I(mm(LABEL_SIZE_MM), mm(LABEL_SIZE_MM)))
        t.SetTextThickness(mm(LABEL_THICK_MM))
        board.Add(t)
        added += 1
    return added


def seed_label_uuids(text):
    """Board-level F.SilkS pin labels get uuid5 uuids (reproducible)."""
    import re
    out = text
    for i, (label, x, y, _ang) in enumerate(PIN_LABELS):
        pat = re.compile(r'(\(gr_text "' + re.escape(label) + r'"\s*\(at ' + re.escape(f'{x:g}') + ' '
                         + re.escape(f'{y:g}') + r'[^\n]*\n(?:[^\n]*\n)*?\s*\(uuid ")[0-9a-f-]+(")')
        out = pat.sub(lambda m: m.group(1) + str(uuid.uuid5(UUID_NS, f'label/{i}')) + m.group(2), out, count=1)
    return out


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
    before = {r: (fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees()) for r in fps}
    refs_before = ref_state(fps)

    obstacles = [crt_box(fps[r]) for r in FIXED] + list(LABEL_STRIPS)
    local = {}
    for ref, *_ in TARGETS:
        local[ref] = {}
        for r in (0, 90, 180, 270):
            fps[ref].SetOrientationDegrees(r)
            fps[ref].SetPosition(pcbnew.VECTOR2I(0, 0))
            local[ref][r] = crt_box(fps[ref])
    offsets = candidates()
    far = candidates(FAR_SHIFT_MM, FAR_STEP_MM)
    best = None
    for seed, order in orders(local):
        result, failed = plan(order, local, obstacles, offsets, far)
        if best is None or len(failed) < len(best[2]):
            best = (seed, result, failed)
        if not failed:
            break
    seed, result, failed = best
    if failed:
        # the board is full (SPEC question in docs/TODO.md): park what doesn't fit in a row left of the board,
        # on the top side, so the lead decides (smaller passives, bottom side or a released keep-out)
        for i, ref in enumerate(failed):
            result[ref] = (PARK_X_MM, PARK_Y0_MM + PARK_PITCH_MM * i, 0, 0.0)
        print(f'NOT PLACED (no legal spot on the board, parked at x = {PARK_X_MM} mm): {failed}')
    print(f'placement order {seed}')
    log = []
    tgt = {t[0]: t for t in TARGETS}
    for ref, (px, py, pr, g) in result.items():
        fps[ref].SetOrientationDegrees(pr)
        fps[ref].SetPosition(pcbnew.VECTOR2I(mm(px), mm(py)))
        _, x, y, rot, _m = tgt[ref]
        log.append((ref, px, py, pr, g, math.hypot(px - x, py - y), pr != rot))
    labels = add_pin_labels(board)
    fab_only = place_refs(board, [r for r in target_refs if r not in failed] + [r for r in FIXED if r[0] == "J"])
    after = {r: (fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees()) for r in fps}
    if any(before[r] != after[r] for r in FIXED):
        raise SystemExit('a fixed footprint moved: not saved')

    moved = [r for r in movable if abs(before[r][0] - after[r][0]) > POS_TOL_NM
             or abs(before[r][1] - after[r][1]) > POS_TOL_NM or before[r][2] != after[r][2]]
    for ref, px, py, pr, g, d, turned in log:
        note = []
        if d > 1e-6 or turned:
            note.append(f'moved {d:.2f} mm from target' + (', turned 90' if turned else ''))
        if g < GAP_MM:
            note.append(f'gap {g} mm')
        if ref in LEAD:
            lx, ly, lr = LEAD[ref]
            ld = math.hypot(px - lx, py - ly)
            note.append('at the lead position' if ld < 1e-3 and pr == lr else f'{ld:.2f} mm from the lead position')
        print(f'  {ref:5s} ({px:8.3f}, {py:8.3f}) rot {pr:5.0f}  {"; ".join(note)}')
    print(f'references on F.Fab only (no free silk spot): {fab_only or "none"}')
    if not moved and not labels and ref_state(fps) == refs_before:
        print('already applied: every part is at its legalized position; nothing saved')
        return
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_pcb'
    shutil.copy2(PCB, backup)
    print(f'backup {backup.relative_to(ROOT)}')
    pcbnew.SaveBoard(str(PCB), board)
    text = PCB.read_text(encoding='utf-8')
    PCB.write_text(seed_label_uuids(text), encoding='utf-8', newline='')
    pcbnew.SaveBoard(str(PCB), pcbnew.LoadBoard(str(PCB)))     # order by the seeded uuids
    print(f'placed {len(moved)} parts, {labels} pin labels added')


if __name__ == '__main__':
    main()
