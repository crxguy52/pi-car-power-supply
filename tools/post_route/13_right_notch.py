"""13: right-edge notch: cut out the BACK HEADER KEEPOUT strip (project lead decision 2026-11-05; SPEC 5 "Board").

Why: this HAT sits on standoffs above a Waveshare 2-CH CAN FD HAT turned 180 deg; that board's vertical pin header
sits under the strip the lead marked "BACK HEADER KEEPOUT" (User.Drawings, x NOTCH_X to the right edge). The lead
approved cutting it out like the existing top and bottom notches, leaving necks of at least NECK_MIN_MM joining
the MH2 / MH4 corner tabs to the board (DECISIONS "Right-edge notch").

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/13_right_notch.py`;
`--dry-run` saves nothing):

1. Edge.Cuts: the right edge line (uuid OLD_EDGE_UUID) is replaced by check_fixed.RIGHT_NOTCH_PATH (the recorded
   geometry lives in tools/check_fixed.py, the guard that accepts it): line, convex corner (OUTER_R), cut edge,
   inner fillet (INNER_R, >= the fab's interior milling radius MILL_MIN_R_MM), the inner edge on the lead's
   keep-out line, and the mirror image at the bottom. Same layer, width and lock state as the lead's segments;
   seeded uuids. The approved top cut edge gave a top neck just under NECK_MIN_MM; it moved outward (into the
   cut) by the smallest round step that clears it (check_fixed.CUT_TOP_Y). The bottom neck already clears it.
2. GND stitching vias (11): every one inside the cut or closer than COPPER_EDGE_MM to the new edge is deleted
   (the CUT_COL_X column); the INNER_COL_X column next to the new inner edge moves to INNER_COL_NEW_X where it
   is too close; a via that is still too close after the move is deleted.
3. J1 / J4 pin labels (board silk text at LABEL_X_OLD) move to LABEL_X_NEW: still next to their pins, and at
   least LABEL_EDGE_GAP_MM from the new edge (fab routing tolerance; the DRC silk-to-edge clearance is 0).
4. Every zone refilled, one priority level at a time (route_lib.refill).
5. tools/check_fixed.py --accept-lead-change EDGE_RIGHT_NOTCH (the recorded, guarded baseline update), then the
   normal check_fixed.

Untouched: the lead's User.Drawings keep-out line and "BACK HEADER KEEPOUT" text, the PoE rule area, J2 (its body
overhangs the cut by intent; no J2 pad is within COPPER_EDGE_MM of the new edge: checked), every other item.

Guards: KiCad lock files; check_fixed before; the old edge line present with the recorded geometry and none of
the new items (apply), or the old line gone and every new item present (already applied: re-checks and stops);
anything else stops. Post-checks (also on "already applied"): necks >= NECK_MIN_MM measured on the saved
Edge.Cuts shapes, no pad / via / track copper closer than COPPER_EDGE_MM to the edge or outside the board, the
labels' edge gap. Backup of the board before saving.
"""
import math
import pathlib
import re
import subprocess
import sys
import uuid

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))
import route_lib as rl  # noqa: E402
import check_fixed as cf  # noqa: E402

NAMESPACE = 'pipwr/13_right_notch'
LEAD_CHANGE = 'EDGE_RIGHT_NOTCH'
OLD_EDGE_UUID = '1d8aaebc-a0af-4f24-b4de-d6686c34c2e0'

COPPER_EDGE_MM = 0.4          # board rule (12)
NECK_MIN_MM = 5.0             # project lead
MILL_MIN_R_MM = 0.505         # OSH Park interior milling radius
TOP_NOTCH_FILLET_C = (183.642, 64.516)   # existing notch fillets the necks are measured from (lead's outline)
BOT_NOTCH_FILLET_C = (183.642, 107.950)
MID_Y = 86.0                  # splits top / bottom neck items

VIA_NET = 'GND'
VIA_DIA_MM = 0.6
VIA_DRILL_MM = 0.3
CUT_COL_X = 189.475           # 11 stitching column inside the strip
INNER_COL_X = 184.475         # 11 stitching column next to the new inner edge
INNER_COL_NEW_X = 184.2
COL_TOL_MM = 0.01

LABEL_TEXTS = ('BATT', 'ACC', 'GND')
LABEL_LAYER = 'F.Silkscreen'
LABEL_X_OLD = 184.4
LABEL_X_NEW = 184.33
LABEL_EDGE_GAP_MM = 0.15      # assumption: margin for the fab's routing tolerance
LABEL_Y_RANGE = (cf.CUT_TOP_Y, cf.CUT_BOT_Y + cf.INNER_R)   # the labels next to the new inner edge

CHECK_X_MIN = cf.NOTCH_X - 3.0   # post-check copper right of this (DRC checks the whole board)
ARC_SAMPLES = 256
EPS_NM = 1


# ---------------------------------------------------------------- geometry

def shape_polyline(s):
    """Edge.Cuts shape as a list of (x, y) mm points (arcs sampled; chord error far below 1 um)."""
    st = s.GetShape()
    a = (rl.mm(s.GetStart().x), rl.mm(s.GetStart().y))
    b = (rl.mm(s.GetEnd().x), rl.mm(s.GetEnd().y))
    if st == pcbnew.SHAPE_T_SEGMENT:
        return [a, b]
    if st != pcbnew.SHAPE_T_ARC:
        raise SystemExit(f'unexpected Edge.Cuts shape {s.GetShapeStr()}: stop')
    c = (rl.mm(s.GetCenter().x), rl.mm(s.GetCenter().y))
    m = (rl.mm(s.GetArcMid().x), rl.mm(s.GetArcMid().y))
    r = rl.mm(s.GetRadius())
    ang = lambda p: math.atan2(p[1] - c[1], p[0] - c[0])
    a0, am, a1 = ang(a), ang(m), ang(b)
    sweep = (a1 - a0) % (2 * math.pi)
    if (am - a0) % (2 * math.pi) > sweep:          # the mid point lies the other way round
        sweep -= 2 * math.pi
    return [(c[0] + r * math.cos(a0 + sweep * i / ARC_SAMPLES), c[1] + r * math.sin(a0 + sweep * i / ARC_SAMPLES))
            for i in range(ARC_SAMPLES + 1)]


def pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def pt_line(p, line):
    return min(pt_seg(p, line[i], line[i + 1]) for i in range(len(line) - 1))


def line_line(u, v):
    """Minimum distance between two polylines that don't cross."""
    return min(min(pt_line(p, v) for p in u), min(pt_line(p, u) for p in v))


def edge_shapes(board):
    return [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]


def outline_poly(board):
    ps = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(ps, False) or ps.OutlineCount() != 1 or ps.HoleCount(0) != 0:
        raise SystemExit('board outline is not one closed contour: stop')
    return ps


def edge_dist(lines, p):
    return min(pt_line(p, ln) for ln in lines)


def inside(ps, p):
    return ps.Contains(rl.P(*p))


# ---------------------------------------------------------------- state

def key_match(s, item):
    return cf._close(cf._undirected(cf.shape_key(s)), cf._undirected(cf.edge_item_key(item)))


def edge_state(board):
    edges = edge_shapes(board)
    old = [s for s in edges if s.m_Uuid.AsString() == OLD_EDGE_UUID]
    if old and not key_match(old[0], cf.RIGHT_NOTCH_OLD):
        raise SystemExit('the old right edge line has other geometry: stop')
    new = [[s for s in edges if key_match(s, it)] for it in cf.RIGHT_NOTCH_PATH]
    if any(len(n) > 1 for n in new):
        raise SystemExit('a new edge item is on the board twice: stop')
    have = sum(len(n) for n in new)
    if old and have == 0:
        return 'todo', old[0], None
    if not old and have == len(cf.RIGHT_NOTCH_PATH):
        return 'applied', None, [n[0] for n in new]
    raise SystemExit(f'partly applied (old line {bool(old)}, {have}/{len(cf.RIGHT_NOTCH_PATH)} new items): stop')


def design_necks():
    """Necks from the recorded geometry (fillet centres minus both radii); the measured ones are post_checks."""
    top_c = (cf.NOTCH_X + cf.INNER_R, cf.CUT_TOP_Y + cf.INNER_R)
    bot_c = (cf.NOTCH_X + cf.INNER_R, cf.CUT_BOT_Y - cf.INNER_R)
    return (math.dist(TOP_NOTCH_FILLET_C, top_c) - 2 * cf.INNER_R,
            math.dist(BOT_NOTCH_FILLET_C, bot_c) - 2 * cf.INNER_R)


def add_edge(board, item, template):
    s = pcbnew.PCB_SHAPE(board)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetStroke(template.GetStroke())
    s.SetWidth(cf.EDGE_WIDTH_NM)
    if item[0] == 'line':
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(rl.P(*item[1]))
        s.SetEnd(rl.P(*item[2]))
    else:
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(rl.P(*item[1]), rl.P(*cf.arc_mid_mm(*item[1:])), rl.P(*item[2]))
    s.SetLocked(True)
    board.Add(s)
    if not key_match(s, item):
        raise SystemExit(f'new edge item {item} does not match its record: stop')
    return s


def stitch_vias(board, x):
    return [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == VIA_NET
            and abs(rl.mm(t.GetPosition().x) - x) <= COL_TOL_MM]


def via_ok(ps, lines, xy):
    return inside(ps, xy) and edge_dist(lines, xy) - VIA_DIA_MM / 2 >= COPPER_EDGE_MM


def labels(board, x):
    return [d for d in board.GetDrawings() if d.GetClass() == 'PCB_TEXT' and d.GetText() in LABEL_TEXTS
            and d.GetLayerName() == LABEL_LAYER and abs(rl.mm(d.GetPosition().x) - x) <= COL_TOL_MM
            and LABEL_Y_RANGE[0] <= rl.mm(d.GetPosition().y) <= LABEL_Y_RANGE[1]]


def bbox_edge_gap(lines, bb):
    """Smallest distance from the bounding box's corners and edge mid points to the outline."""
    x0, y0, x1, y1 = (rl.mm(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
    box = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return min(min(pt_line(p, box) for ln in lines for p in ln), min(edge_dist(lines, p) for p in box))


# ---------------------------------------------------------------- apply

def apply(board, old):
    for r in (cf.OUTER_R, cf.INNER_R):
        if r < MILL_MIN_R_MM:
            raise SystemExit(f'corner radius {r} under the milling minimum: stop')
    necks = design_necks()
    if min(necks) < NECK_MIN_MM:
        raise SystemExit(f'recorded geometry gives necks {necks}: stop')
    if old.GetWidth() != cf.EDGE_WIDTH_NM or not old.IsLocked():
        raise SystemExit('old edge line width / lock not as recorded: stop')
    keep_alive = [old]                               # proxies must outlive the save (lessons doc)
    board.Remove(old)
    for it in cf.RIGHT_NOTCH_PATH:
        add_edge(board, it, old)
    ps = outline_poly(board)
    lines = [shape_polyline(s) for s in edge_shapes(board)]

    deleted, moved = [], []
    for v in stitch_vias(board, CUT_COL_X):
        xy = (rl.mm(v.GetPosition().x), rl.mm(v.GetPosition().y))
        if not via_ok(ps, lines, xy):
            deleted.append(xy)
            keep_alive.append(v)
            board.Remove(v)
    for v in stitch_vias(board, INNER_COL_X):
        xy = (rl.mm(v.GetPosition().x), rl.mm(v.GetPosition().y))
        if via_ok(ps, lines, xy):
            continue
        new = (INNER_COL_NEW_X, xy[1])
        if via_ok(ps, lines, new):
            v.SetPosition(rl.P(*new))
            moved.append(xy)
        else:
            deleted.append(xy)
            keep_alive.append(v)
            board.Remove(v)
    labs = labels(board, LABEL_X_OLD)
    if not labs:
        raise SystemExit('pin labels not at the expected x: stop')
    for d in labs:
        d.SetPosition(rl.P(LABEL_X_NEW, rl.mm(d.GetPosition().y)))
    return deleted, moved, [d.GetText() for d in labs], keep_alive


GR_START = re.compile(r'^\t\((gr_line|gr_arc)\b', re.M)


def reseed_shapes(text, keep, namespace):
    """uuid5 from the content for every new gr_line / gr_arc (route_lib.reseed_uuids covers copper and zones)."""
    ns = uuid.uuid5(uuid.NAMESPACE_URL, namespace)
    out, pos = [], 0
    for m in GR_START.finditer(text):
        i = m.start() + 1
        j = rl._block_end(text, i)
        block = text[i:j]
        um = re.search(r'\(uuid "([0-9a-f-]+)"\)', block)
        if um and um.group(1) not in keep:
            basis = re.sub(r'\(uuid "[0-9a-f-]+"\)', '', block)
            block = block[:um.start(1)] + str(uuid.uuid5(ns, basis)) + block[um.end(1):]
        out += [text[pos:i], block]
        pos = j
    out.append(text[pos:])
    return ''.join(out)


def save(board, before_text, path):
    pcbnew.SaveBoard(str(path), board)
    keep = rl.uuids_in(before_text)
    text = path.read_text(encoding='utf-8')
    text = reseed_shapes(rl.reseed_uuids(text, keep, NAMESPACE), keep, NAMESPACE)
    path.write_text(text, encoding='utf-8', newline='')
    b2 = pcbnew.LoadBoard(str(path))
    pcbnew.SaveBoard(str(path), b2)


# ---------------------------------------------------------------- post-checks

def post_checks(board):
    state, _, new = edge_state(board)
    if state != 'applied':
        raise SystemExit('post-check: the new edge is not on the board: stop')
    ps = outline_poly(board)
    lines = [shape_polyline(s) for s in edge_shapes(board)]
    new_ids = {s.m_Uuid.AsString() for s in new}
    old_lines = [shape_polyline(s) for s in edge_shapes(board) if s.m_Uuid.AsString() not in new_ids]
    # neck items: the new cut edge (not the outer x = RIGHT_X lines) against the lead's notch edges
    cut = [shape_polyline(s) for s, it in zip(new, cf.RIGHT_NOTCH_PATH) if not (
        it[0] == 'line' and abs(it[1][0] - cf.RIGHT_X) < 1e-9 and abs(it[2][0] - cf.RIGHT_X) < 1e-9)]
    necks = []
    for top in (True, False):
        side = (lambda ln: max(p[1] for p in ln) < MID_Y) if top else (lambda ln: min(p[1] for p in ln) > MID_Y)
        a = [ln for ln in old_lines if side(ln)]
        b = [ln for ln in cut if side(ln)]
        necks.append(min(line_line(u, v) for u in a for v in b))
    if min(necks) < NECK_MIN_MM:
        raise SystemExit(f'post-check: necks {necks} under {NECK_MIN_MM} mm: stop')
    bad = []
    near = lambda item: rl.mm(item.GetBoundingBox().GetRight()) >= CHECK_X_MIN
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if not p.IsOnCopperLayer() or not near(p):
                continue
            poly = p.GetEffectivePolygon(pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
            pts = [(rl.mm(poly.CVertex(i).x), rl.mm(poly.CVertex(i).y)) for i in range(poly.TotalVertices())]
            pts.append((rl.mm(p.GetPosition().x), rl.mm(p.GetPosition().y)))
            if not inside(ps, pts[-1]) or min(edge_dist(lines, q) for q in pts[:-1]) < COPPER_EDGE_MM - 1e-6:
                bad.append(f'{fp.GetReference()}.{p.GetNumber()}')
    for t in board.GetTracks():
        if not near(t):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            xy = (rl.mm(t.GetPosition().x), rl.mm(t.GetPosition().y))
            if not via_ok(ps, lines, xy):
                bad.append(f'via {xy}')
        else:
            a = (rl.mm(t.GetStart().x), rl.mm(t.GetStart().y))
            b = (rl.mm(t.GetEnd().x), rl.mm(t.GetEnd().y))
            gap = min(line_line([a, b], ln) for ln in lines) - rl.mm(t.GetWidth()) / 2
            if not (inside(ps, a) and inside(ps, b)) or gap < COPPER_EDGE_MM - 1e-6:
                bad.append(f'track {a}-{b}')
    if bad:
        raise SystemExit(f'post-check: copper too close to the edge or outside the board: {bad}: stop')
    labs = labels(board, LABEL_X_NEW)
    gaps = [bbox_edge_gap(lines, d.GetBoundingBox()) for d in labs]
    if not labs or min(gaps) < LABEL_EDGE_GAP_MM:
        raise SystemExit(f'post-check: label edge gaps {gaps}: stop')
    left = [v for v in stitch_vias(board, CUT_COL_X) if cf.CUT_TOP_Y <= rl.mm(v.GetPosition().y) <= cf.CUT_BOT_Y]
    if labels(board, LABEL_X_OLD) or left:
        raise SystemExit('post-check: labels or vias left at the old place: stop')
    return necks, min(gaps)


# ---------------------------------------------------------------- main

def run_check_fixed_accept():
    r = subprocess.run([sys.executable, '-I', str(rl.CHECK_FIXED), '--accept-lead-change', LEAD_CHANGE],
                       capture_output=True, text=True, timeout=rl.CHECK_TIMEOUT_S)
    print('  ' + (r.stdout.strip().splitlines() or ['?'])[-1])
    if r.returncode != 0:
        raise SystemExit(f'check_fixed --accept-lead-change failed:\n{r.stdout[-2000:]}{r.stderr[-1000:]}')


def main():
    pcb = rl.PCB
    rl.guard_locks()
    before_text = pcb.read_text(encoding='utf-8')
    board = pcbnew.LoadBoard(str(pcb))
    state, old, _ = edge_state(board)
    if state == 'applied':
        rl.check_fixed(pcb)
        necks, gap = post_checks(board)
        print(f'already applied: necks top {necks[0]:.4f} / bottom {necks[1]:.4f} mm, label edge gap {gap:.3f} mm; '
              'nothing saved')
        return
    rl.check_fixed(pcb)
    deleted, moved, labs, keep_alive = apply(board, old)
    print(f'  vias deleted {deleted}; moved to x {INNER_COL_NEW_X}: {moved}; labels moved: {labs}')
    if '--dry-run' in sys.argv:
        print(f'dry run: design necks {design_necks()}; nothing saved')
        return
    rl.backup(pcb)
    save(board, before_text, pcb)
    del keep_alive
    rl.refill(pcb)
    run_check_fixed_accept()
    rl.check_fixed(pcb)
    necks, gap = post_checks(pcbnew.LoadBoard(str(pcb)))
    print(f'  applied: necks top {necks[0]:.4f} / bottom {necks[1]:.4f} mm (design {design_necks()}), '
          f'label edge gap {gap:.3f} mm; zones refilled')


if __name__ == '__main__':
    main()
