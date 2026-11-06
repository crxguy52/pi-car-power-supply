"""06: placement of the CD4541B design (placement phase, SPEC 5 "Board" / "Buck layout" / "Timer layout"; 2026-11-05).

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/06_placement.py`;
`--dry-run [--out scratch.kicad_pcb]` prints the result and never saves the master):

- every part except the fixed ones (J1, J2, J4, J5, MH1-MH4: tools/check_fixed.py) goes to a planned position
  (TARGETS). ANCHORS (power corner and buck: hand-checked courtyard gaps) are placed exactly; every other part
  is legalized in TARGETS order: the nearest grid position to its target where its courtyard keeps GAPS_MM[0]
  from every placed courtyard, else GAPS_MM[1], else GAPS_MM[2], searched within SEARCH_RADII_MM[0] first, then
  the next radius (a part stays near its target at a smaller gap rather than drifting away), inside the allowed
  area (ALLOWED) and outside the planned power-copper channels (CHANNELS). The script stops (saves nothing) if a part finds no spot;
- all parts on the top side; positions on GRID_MM;
- silkscreen: each reference on F.SilkS in the first free spot (beside the part, else centre; clear of pads, other
  silk and REF_OTHER_CRT_MM from every other courtyard, so no label reads as its neighbour's), else on F.Fab only
  (listed); size REF_SIZE_MM. Board-level F.SilkS pin names at J1/J4/J5 for the rotated pin order (05):
  BATT/ACC/GND top to bottom at J1 and ACC_N/GND left to right at J5, in front of the wire entry; 12V/GND left
  and right of J4 (its wire face is 0.6 mm from the board edge). The 02 labels (old pin order: wrong after the rotation) are removed first;
- prints the courtyard-gap statistics (per part: the smallest gap to any other courtyard).

Plan (y down; SLVSCD5D 10.1, SPEC 5):
- power corner (inside the J1 BATT -> Q1 -> VOUT -> J4 loop): Q1 (TO-252, pins up, tab down) in the J4 corner,
  so the VOUT tab feeds J4 pin 1 over a short strip (CHANNELS 'VOUT strip'); BATT runs from J1 pin 3 left along
  the top of the corner and down into Q1 S ('BATT run'); C30 straddles G-S just above the pins, R14 above it,
  both with pin 1 on the BATT down-segment; TVS1 beside them with its cathode in the BATT run, anode to GND next
  to the J1 GND pin; Q1 tab gets the corner copper (SPEC 5: >= 1 in2 VOUT where it fits);
- buck along the top (TI layout guide, mirrored onto the J2 side): U8 power pins (GND, PH, VIN, BOOT) to the
  right; C17 (100 nF) then C15 (10 uF) at VIN/GND, VIN rail below them, GND rail above; PH through vias under
  C17 to C18 (BOOT) and L1 pin 1 (small PH area, TI: SW pour on the bottom); L1 below the output caps; C22-C24
  in a row along the top at the GND rail, pin 1 (+5V1) down to the +5V1 rail that feeds the J2 VBUS pins and
  L1 pin 2 (C24 nearest J2); FB / COMP / SS parts below-left of U8 (analog pins), away from PH and L1;
- VOUT to the buck: one up-run from the Q1 tab, left of the BATT down-segment, between C18 and L1 into the VIN
  rail at C15 ('VOUT up-run');
- timer (SPEC 5 "Timer layout"): U5 left of centre; R27 / C29 / R28 in a column at the oscillator pins 1-3, their
  common U5_TJ pins in a line (short TJ / RS node, far from PH and L1); C8 at pin 14 with D7 and R31 next to it,
  R30 between them and the VOUT up-run; R26 at MR (pin 6);
- gate drive and HOLD_G: Q5, R15, R29, D6 between U5 and the VOUT up-run (Q5 near the Q1 gate network; Q1_G
  reaches R15 through a short bottom jumper under the BATT down-segment: routing phase);
- ACC input: TVS2, D5, R8, R25 at the lower right of the logic area, the closest spot outside the power loop
  to J1 (ACC_IN leaves J1 pin 2 on the bottom layer: routing phase); D4 by SW1;
- status: Q6 and R21 next to J5 (R21 at the ACC_N pin);
- SW1 at the left board edge (the free edge: J2/J1/J4 on the right, GPIO header on top, Waveshare IO at the
  bottom), slide parallel to the edge, top actuated; D3 (VOUT LED) and R3 next to it, visible from above.
- routing channels: power copper on top (BATT, VOUT >= 3 mm), bottom = GND pour (routing phase).

Why: the 64-part placement (02/03) is obsolete (05 removed 36 parts and added 13). The board now has room for
GAPS_MM[0] courtyard gaps almost everywhere (hand assembly: project lead, nothing below 0805, keep parts apart).

U8's bottom pad 9 (4.0 x 6.0 mm) keeps the 0.5 mm copper-to-edge rule from the GPIO-header notch edge (y 66.04).

Guards: stops on KiCad lock files, on a footprint set other than TARGETS + FIXED, on a bottom-side part, on an
anchor overlap below GAPS_MM[-1], if a part can't be placed, if a fixed item would move (check_fixed must PASS
afterwards). Idempotent: deterministic search; a re-run on the applied board prints "already applied" and
saves nothing. Backup to pi_power_board-backups/ before saving.
"""
import datetime
import math
import pathlib
import re
import shutil
import sys
import uuid

import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[2]
STEM = 'pi_power_board'
PCB = ROOT / f'{STEM}.kicad_pcb'
BACKUPS = ROOT / f'{STEM}-backups'
UUID_NS = uuid.uuid5(uuid.NAMESPACE_URL, 'pi-car-power-supply/tools/post_route/06_placement')

FIXED = ('J1', 'J2', 'J4', 'J5', 'MH1', 'MH2', 'MH3', 'MH4')
GAPS_MM = (1.0, 0.75, 0.5)      # courtyard-to-courtyard: target, fallback, minimum (project lead)
GRID_MM = 0.05
STEP_MM = 0.25
SEARCH_RADII_MM = (2.0, 5.0, 12.0)   # staged search: every gap step within the first radius, then the next
POS_TOL_NM = 1000
EPS_MM = 1e-6

# allowed courtyard area (x0, y0, x1, y1) mm: inside Edge.Cuts with EDGE_MARGIN_MM, below the GPIO HEADER strip,
# above the WAVESHARE IO strip, left of the BACK HEADER KEEPOUT line (the lead's Dwgs.User drawings), plus the left
# tabs between the mounting holes (same areas as 02_placement.py)
EDGE_MARGIN_MM = 0.3
BODY = (127.0 + EDGE_MARGIN_MM, 66.04 + EDGE_MARGIN_MM, 185.17 - EDGE_MARGIN_MM, 106.43 - EDGE_MARGIN_MM)
LEFT_TABS = (127.0 + EDGE_MARGIN_MM, 64.9, 133.85 - EDGE_MARGIN_MM, 107.7)
ALLOWED = (BODY, LEFT_TABS)

# planned power copper on top: no legalized courtyard inside (anchors are checked by hand)
CHANNELS = {
    'VOUT up-run': (157.6, 74.9, 159.7, 99.6),
    'VOUT to tab': (157.6, 98.0, 163.6, 106.13),
    'BATT run': (161.0, 84.9, 175.0, 88.3),
    'VOUT strip': (167.9, 100.9, 176.5, 103.6),
}

# (ref, x, y, rot deg, may_rotate)
ANCHORS = [
    # power corner
    ('Q1', 166.3, 101.3, 270), ('C30', 166.3, 92.9, 0), ('R14', 166.3, 89.9, 0), ('TVS1', 171.3, 89.55, 270),
    # buck
    ('U8', 150.5, 69.7, 180), ('C17', 157.0, 69.06, 90), ('C15', 159.8, 69.15, 90),
    ('C22', 163.4, 69.2, 90), ('C23', 167.45, 69.2, 90), ('C24', 171.5, 69.2, 90),
    ('L1', 166.3, 78.01, 0), ('C18', 156.1, 74.0, 0),
]
TARGETS = [
    # buck analog, below-left of U8 (VSENSE / COMP / SS on its left pads)
    ('C19', 147.5, 75.1, 270, False), ('R18', 150.6, 75.5, 270, False), ('C20', 150.6, 80.2, 270, False),
    ('R17', 143.3, 79.5, 90, False), ('R16', 143.3, 84.3, 90, False),
    # SW1 at the left edge, LED next to it, J5 status
    ('SW1', 129.55, 72.0, 0, False), ('R21', 134.3, 71.4, 90, False), ('Q6', 133.6, 78.2, 0, True),
    ('D3', 129.6, 80.2, 90, False), ('R3', 129.6, 85.6, 90, False), ('D4', 134.3, 84.0, 0, True),
    # timer
    ('U5', 138.5, 94.5, 0, False), ('R27', 131.5, 89.6, 180, False), ('C29', 131.5, 92.6, 180, False),
    ('R28', 131.5, 95.6, 180, False), ('R26', 131.5, 98.6, 0, False),
    ('C8', 144.1, 91.0, 270, False), ('D7', 147.6, 91.0, 270, False), ('R31', 144.1, 95.6, 270, False),
    ('R30', 148.0, 85.6, 0, False),
    # gate drive / HOLD_G
    ('R15', 154.3, 85.2, 180, False), ('Q5', 154.3, 89.05, 180, False), ('D6', 154.3, 93.6, 180, False),
    # ACC input (TVS2 first: the largest): TVS2 cathode at the bottom next to D5's anode
    ('TVS2', 155.0, 101.3, 90, False), ('D5', 151.0, 101.5, 270, False), ('R8', 147.3, 99.3, 180, True),
    ('R25', 147.3, 102.5, 0, True),
    # HOLD_G: D6 and R29 between U5 OUT (pin 8) and Q5's gate
    ('R29', 148.6, 96.3, 0, True),
]

# board-level pin names (text, x, y, angle deg) mm, after 05's pin order: J1 and J5 in front of the wire entry;
# J4 beside its pins (its wire face is 0.6 mm from the Waveshare-notch edge: no room in front)
PIN_LABELS = [('BATT', 184.4, 87.63, 90.0), ('ACC', 184.4, 91.44, 90.0), ('GND', 184.4, 95.25, 90.0),
              ('12V', 174.3, 102.235, 90.0), ('GND', 184.4, 102.235, 90.0),
              ('ACC_N', 138.938, 66.6, 0.0), ('GND', 142.748, 66.6, 0.0)]
OLD_LABEL_TEXTS = {'GND', 'ACC', 'BATT', '12V', 'ACC_N'}     # 02's labels (old pin order)
LABEL_SIZE_MM = 0.8
LABEL_THICK_MM = 0.12
REF_SIZE_MM = 0.8
REF_THICK_MM = 0.12
REF_PAD_CLEAR_MM = 0.15
REF_OFFSETS_MM = (0.5, 1.3, 2.1)      # text centre beyond the courtyard edge
REF_TEXT_GAP_MM = 0.1
REF_OTHER_CRT_MM = 0.4    # a reference keeps this from every other courtyard (no ambiguous labels)


def mm(v):
    return pcbnew.FromMM(v)


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


def inside(box, area):
    return box[0] >= area[0] - EPS_MM and box[1] >= area[1] - EPS_MM and box[2] <= area[2] + EPS_MM \
        and box[3] <= area[3] + EPS_MM


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def legal(box, placed, g):
    return any(inside(box, a) for a in ALLOWED) and not any(overlaps(box, c) for c in CHANNELS.values()) \
        and all(gap(box, o) >= g - EPS_MM for o in placed)


def offsets():
    n = int(SEARCH_RADII_MM[-1] / STEP_MM)
    out = [(i * STEP_MM, j * STEP_MM) for i in range(-n, n + 1) for j in range(-n, n + 1)
           if math.hypot(i, j) * STEP_MM <= SEARCH_RADII_MM[-1]]
    out.sort(key=lambda d: (round(math.hypot(*d), 6), d))
    return out


def snap(v):
    return round(round(v / GRID_MM) * GRID_MM, 4)


def local_boxes(fp):
    """Courtyard box at the origin for each rotation."""
    pos, ori = fp.GetPosition(), fp.GetOrientationDegrees()
    out = {}
    for r in (0, 90, 180, 270):
        fp.SetOrientationDegrees(r)
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        out[r] = crt_box(fp)
    fp.SetOrientationDegrees(ori)
    fp.SetPosition(pos)
    return out


def at(lb, x, y):
    return (lb[0] + x, lb[1] + y, lb[2] + x, lb[3] + y)


def legalize(lbs, x, y, rot, may_rotate, placed, offs):
    rots = [rot] + ([(rot + 90) % 360] if may_rotate else [])
    for radius in SEARCH_RADII_MM:
        for g in GAPS_MM:
            for dx, dy in offs:
                if math.hypot(dx, dy) > radius + EPS_MM:
                    break
                for r in rots:
                    px, py = snap(x + dx), snap(y + dy)
                    if legal(at(lbs[r], px, py), placed, g):
                        return px, py, r, g
    return None


def text_box(t):
    b = t.GetBoundingBox()
    return (b.GetLeft() / 1e6, b.GetTop() / 1e6, b.GetRight() / 1e6, b.GetBottom() / 1e6)


def place_refs(board, refs):
    """Reference on F.SilkS: centre (across the long axis), else beside the courtyard; F.Fab only if no spot."""
    pads = []
    for f in board.GetFootprints():
        for p in f.Pads():
            b = p.GetBoundingBox()
            pads.append((b.GetLeft() / 1e6 - REF_PAD_CLEAR_MM, b.GetTop() / 1e6 - REF_PAD_CLEAR_MM,
                         b.GetRight() / 1e6 + REF_PAD_CLEAR_MM, b.GetBottom() / 1e6 + REF_PAD_CLEAR_MM))
    silk = []
    for f in board.GetFootprints():
        for g in f.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS and g.GetClass() != 'PCB_FIELD':
                silk.append(text_box(g) if g.GetClass() == 'PCB_TEXT' else
                            (g.GetBoundingBox().GetLeft() / 1e6, g.GetBoundingBox().GetTop() / 1e6,
                             g.GetBoundingBox().GetRight() / 1e6, g.GetBoundingBox().GetBottom() / 1e6))
    taken = [text_box(d) for d in board.GetDrawings() if d.GetLayer() == pcbnew.F_SilkS]
    crts = {f.GetReference(): crt_box(f) for f in board.GetFootprints()}
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
        cx, cy = (cb[0] + cb[2]) / 2 - c.x / 1e6, (cb[1] + cb[3]) / 2 - c.y / 1e6
        w, h = cb[2] - cb[0], cb[3] - cb[1]
        horiz = w >= h
        spots = []                              # beside the part first (readable after assembly), centre last
        for k in REF_OFFSETS_MM:
            spots += [(cx, cy - (h / 2 + k), 0.0), (cx, cy + h / 2 + k, 0.0), (cx - (w / 2 + k), cy, 90.0),
                      (cx + w / 2 + k, cy, 90.0)]
        for k in REF_OFFSETS_MM:                # beside, shifted along the side
            for f in (-0.5, 0.5):
                spots += [(cx + f * w, cy - (h / 2 + k), 0.0), (cx + f * w, cy + h / 2 + k, 0.0),
                          (cx - (w / 2 + k), cy + f * h, 90.0), (cx + w / 2 + k, cy + f * h, 90.0)]
        spots.append((cx, cy, 0.0 if horiz else 90.0))
        ok = False
        for dx, dy, ang in spots:
            t.SetTextAngleDegrees(ang)
            t.SetPosition(pcbnew.VECTOR2I(c.x + mm(dx), c.y + mm(dy)))
            tb = text_box(t)
            if not any(inside(tb, a) for a in ALLOWED):
                continue
            if any(overlaps(tb, p) for p in pads) or any(gap(tb, o) < REF_TEXT_GAP_MM for o in taken + silk):
                continue
            if any(gap(tb, o) < REF_OTHER_CRT_MM for q, o in crts.items() if q != ref):
                continue                        # unambiguous: clear of every other part's courtyard
            taken.append(tb)
            ok = True
            break
        if not ok:
            t.SetLayer(pcbnew.F_Fab)
            t.SetTextAngleDegrees(0.0)
            t.SetPosition(pcbnew.VECTOR2I(c.x + mm(cx), c.y + mm(cy)))
            fab_only.append(ref)
    return fab_only


def ref_state(fps):
    return {r: (f.Reference().GetLayerName(), f.Reference().GetPosition().x, f.Reference().GetPosition().y,
                f.Reference().GetTextAngleDegrees(), f.Reference().GetTextSize().x) for r, f in fps.items()}


def label_state(board):
    return sorted((d.GetText(), d.GetPosition().x, d.GetPosition().y, round(d.GetTextAngleDegrees(), 3))
                  for d in board.GetDrawings() if d.GetClass() == 'PCB_TEXT' and d.GetLayer() == pcbnew.F_SilkS)


def want_labels():
    return sorted((t, mm(x), mm(y), round(a, 3)) for t, x, y, a in PIN_LABELS)


def set_labels(board):
    """Replace the board-level F.SilkS pin labels with PIN_LABELS. Returns True if anything changed."""
    if label_state(board) == want_labels():
        return False
    old = [d for d in board.GetDrawings() if d.GetClass() == 'PCB_TEXT' and d.GetLayer() == pcbnew.F_SilkS]
    unknown = [d.GetText() for d in old if d.GetText() not in OLD_LABEL_TEXTS]
    if unknown:
        raise SystemExit(f'unexpected board-level silk texts {unknown}: not touched, stop')
    keep = []
    for d in old:
        keep.append(d)
        board.Remove(d)
    for text, x, y, ang in PIN_LABELS:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        t.SetTextAngleDegrees(ang)
        t.SetTextSize(pcbnew.VECTOR2I(mm(LABEL_SIZE_MM), mm(LABEL_SIZE_MM)))
        t.SetTextThickness(mm(LABEL_THICK_MM))
        board.Add(t)
    return True


def seed_label_uuids(text):
    """The board-level pin labels get uuid5 uuids (reproducible files)."""
    out = text
    for i, (label, x, y, _a) in enumerate(PIN_LABELS):
        pat = re.compile(r'(\(gr_text "' + re.escape(label) + r'"\s*\(at ' + re.escape(f'{x:g}') + ' '
                         + re.escape(f'{y:g}') + r'[^\n]*\n(?:[^\n]*\n)*?\s*\(uuid ")[0-9a-f-]+(")')
        out = pat.sub(lambda m: m.group(1) + str(uuid.uuid5(UUID_NS, f'label/{i}')) + m.group(2), out, count=1)
    return out


def gap_stats(board):
    boxes = {f.GetReference(): crt_box(f) for f in board.GetFootprints()}
    mins = {}
    for r, b in boxes.items():
        if r.startswith('MH'):
            continue
        mins[r] = min(gap(b, o) for q, o in boxes.items() if q != r)
    return mins


def main():
    locks = sorted(ROOT.glob('~*.lck'))
    if locks:
        raise SystemExit(f'KiCad lock files present ({[p.name for p in locks]}): close KiCad first')
    board = pcbnew.LoadBoard(str(PCB))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    planned = [a[0] for a in ANCHORS] + [t[0] for t in TARGETS]
    movable = set(fps) - set(FIXED)
    if len(set(planned)) != len(planned) or set(planned) != movable:
        raise SystemExit(f'plan vs board: missing {sorted(movable - set(planned))}, '
                         f'extra {sorted(set(planned) - movable)}')
    if any(fps[r].IsFlipped() for r in fps):
        raise SystemExit('a part is on the bottom side: unexpected')
    fixed_before = {r: (fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees())
                    for r in FIXED}
    before = {r: (fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees()) for r in fps}
    refs_before = ref_state(fps)

    lbs = {r: local_boxes(fps[r]) for r in planned}
    placed = [crt_box(fps[r]) for r in FIXED if not r.startswith('MH')] + \
             [crt_box(fps[r]) for r in FIXED if r.startswith('MH')]
    result = {}
    for ref, x, y, rot in ANCHORS:
        box = at(lbs[ref][rot], x, y)
        worst = min(gap(box, o) for o in placed)
        if worst < GAPS_MM[-1] - EPS_MM or not any(inside(box, a) for a in ALLOWED):
            raise SystemExit(f'anchor {ref}: gap {worst:.2f} mm or outside the allowed area: fix ANCHORS')
        placed.append(box)
        result[ref] = (x, y, rot, None)
    offs = offsets()
    failed = []
    for ref, x, y, rot, may_rotate in TARGETS:
        res = legalize(lbs[ref], x, y, rot, may_rotate, placed, offs)
        if res is None:
            failed.append(ref)
            continue
        result[ref] = res
        placed.append(at(lbs[ref][res[2]], res[0], res[1]))
    if failed and '--dry-run' not in sys.argv:
        raise SystemExit(f'NOT PLACED (no legal spot within {SEARCH_RADII_MM[-1]} mm): {failed}: nothing saved')
    if failed:
        print(f'dry run: NOT PLACED {failed}')

    tgt = {a[0]: (a[1], a[2], a[3]) for a in ANCHORS}
    tgt.update({t[0]: (t[1], t[2], t[3]) for t in TARGETS})
    for ref, (px, py, pr, g) in result.items():
        fps[ref].SetOrientationDegrees(pr)
        fps[ref].SetPosition(pcbnew.VECTOR2I(mm(px), mm(py)))
        tx, ty, tr = tgt[ref]
        d = math.hypot(px - tx, py - ty)
        if d > EPS_MM or pr != tr or (g is not None and g < GAPS_MM[0]):
            print(f'  {ref:5s} legalized {d:.2f} mm from its target' + (', turned 90' if pr != tr else '')
                  + (f' (gap step {g} mm)' if g is not None else ''))
    labels_changed = set_labels(board)
    fab_only = place_refs(board, planned + ['J1', 'J2', 'J4', 'J5'])
    after = {r: (fps[r].GetPosition().x, fps[r].GetPosition().y, fps[r].GetOrientationDegrees()) for r in fps}
    if any(fixed_before[r] != after[r] for r in FIXED):
        raise SystemExit('a fixed footprint moved: not saved')

    mins = gap_stats(board)
    vals = sorted(mins.values())
    print(f'courtyard gap per part (smallest to any other courtyard): min {vals[0]:.2f} mm, median '
          f'{vals[len(vals) // 2]:.2f} mm; >= 1.0: {sum(v >= 1.0 - EPS_MM for v in vals)}, 0.75-1.0: '
          f'{sum(0.75 - EPS_MM <= v < 1.0 - EPS_MM for v in vals)}, 0.5-0.75: '
          f'{sum(0.5 - EPS_MM <= v < 0.75 - EPS_MM for v in vals)}, < 0.5: {sum(v < 0.5 - EPS_MM for v in vals)} '
          f'(of {len(vals)})')
    print('  below 1.0 mm: ' + ', '.join(f'{r} {v:.2f}' for r, v in sorted(mins.items(), key=lambda kv: kv[1])
                                         if v < 1.0 - EPS_MM))
    print(f'references on F.Fab only (no free silk spot): {fab_only or "none"}')

    moved = [r for r in fps if abs(before[r][0] - after[r][0]) > POS_TOL_NM
             or abs(before[r][1] - after[r][1]) > POS_TOL_NM or before[r][2] != after[r][2]]
    if '--dry-run' in sys.argv:
        for r in sorted(result):
            print(f'  {r:5s} {result[r][0]:8.2f} {result[r][1]:8.2f} {result[r][2]:4d}')
        if '--out' in sys.argv:
            out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])
            pcbnew.SaveBoard(str(out), board)
            print(f'dry run: scratch copy {out}')
        print(f'dry run: {len(moved)} parts would move; master not saved')
        return
    if not moved and not labels_changed and ref_state(fps) == refs_before:
        print('already applied: every part at its planned / legalized position, labels and references in place; '
              'nothing saved')
        return
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_pcb'
    shutil.copy2(PCB, backup)
    print(f'backup {backup.relative_to(ROOT)}')
    pcbnew.SaveBoard(str(PCB), board)
    PCB.write_text(seed_label_uuids(PCB.read_text(encoding='utf-8')), encoding='utf-8', newline='')
    pcbnew.SaveBoard(str(PCB), pcbnew.LoadBoard(str(PCB)))
    print(f'placed: {len(moved)} parts moved; pin labels {"replaced" if labels_changed else "unchanged"}')


if __name__ == '__main__':
    main()
