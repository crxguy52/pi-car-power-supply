"""14: right-edge notch: board kept under the USB port J2 (project lead decision 2026-11-05; SPEC 5 "Board").

Why: the project lead: "Keep board under the USB port (J2). It's going to block underneath it anyway, so we may
as well have board under it. I'm not using the header it covers." Script 13 cut the BACK HEADER KEEPOUT strip
from just below the MH2 tab; the part of that strip under J2's body is board again, and the notch now starts just
below J2's courtyard (DECISIONS "Right-edge notch under the USB port").

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/14_notch_under_usb.py`;
`--dry-run` builds the result in the scratch folder and saves nothing to the master):

1. Edge.Cuts: the notch's top five items (check_fixed.RIGHT_NOTCH_USB_OLD: right edge line, mouth arc, top edge,
   inner fillet, inner vertical line) are replaced by check_fixed.RIGHT_NOTCH_USB_TOP: the same path with its top
   edge at check_fixed.CUT_TOP_Y_USB, the first round value at least COURTYARD_GAP_MM below J2's courtyard
   (checked here against the measured courtyard). Same corner radii, layer, width, lock state; seeded uuids; the
   whole path shares exact (nm) endpoints and the outline stays one closed contour. The bottom edge stays.
2. Every zone refilled, one priority level at a time (route_lib.refill), in a scratch copy of the project.
3. GND stitching vias in the restored strip, on the column and grid of script 11 (the ones 13 deleted): only where
   the via is >= COPPER_EDGE_MM from the edge, both GND fills hold it with STITCH_MARGIN_MM to spare (so no other
   net's copper is near) and every hole is STITCH_HOLE_MM away. Then refill again.
4. The scratch board replaces the master (backup first), then check_fixed --accept-lead-change
   EDGE_RIGHT_NOTCH_UNDER_USB and the normal check_fixed.

Untouched: J1 / J4 pin labels (13 placed them; their edge gap is re-checked), the lead's drawings, the PoE rule
area (now on board again), J2, every other item. Script 13 becomes historical (its guard sees a partly-changed
path).

Guards: KiCad lock files; check_fixed before; the old items present exactly and none of the new (apply), or the
reverse plus the stitching vias (already applied: re-checks and stops); anything else stops. Post-checks (also on
"already applied"): one closed outline with exact shared endpoints, necks >= NECK_MIN_MM measured on the saved
Edge.Cuts shapes, no copper closer than COPPER_EDGE_MM to the edge near the notch, J2 pad copper to edge, the
labels' edge gap.
"""
import importlib.util
import math
import pathlib
import shutil
import subprocess
import sys

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))
import route_lib as rl  # noqa: E402
import check_fixed as cf  # noqa: E402


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


n13 = _load('n13', '13_right_notch.py')        # geometry helpers only (read-only use)

NAMESPACE = 'pipwr/14_notch_under_usb'
LEAD_CHANGE = 'EDGE_RIGHT_NOTCH_UNDER_USB'
SCRATCH = pathlib.Path(r'C:\tmp\pipwr\a19_14')

COPPER_EDGE_MM = n13.COPPER_EDGE_MM
NECK_MIN_MM = n13.NECK_MIN_MM
COURTYARD_REF = 'J2'
COURTYARD_GAP_MM = 0.2        # project lead brief: top edge at least this far below J2's courtyard
TOP_Y_STEP_MM = 0.01          # rounding step of the top edge
J2_PAD_EDGE_MIN_MM = COPPER_EDGE_MM

VIA_NET = 'GND'
VIA_DIA_MM, VIA_DRILL_MM = n13.VIA_DIA_MM, n13.VIA_DRILL_MM
STITCH_COL_X = n13.CUT_COL_X  # script 11's column inside the strip
STITCH_PITCH_MM = 5.0         # script 11's grid
STITCH_MARGIN_MM = 0.3        # script 11
STITCH_HOLE_MM = 0.5          # script 11
STITCH_SAMPLES = 16
GND_ZONES = (('GND_TOP', pcbnew.F_Cu), ('GND_BOT', pcbnew.B_Cu))
RESTORED_Y = (cf.CUT_TOP_Y, cf.CUT_TOP_Y_USB)   # strip that is board again
GRID_TOL_MM = 0.01


# ---------------------------------------------------------------- state

def present(edges, item):
    return [s for s in edges if n13.key_match(s, item)]


def edge_state(board):
    edges = n13.edge_shapes(board)
    for it in cf.RIGHT_NOTCH_PATH[cf.USB_TOP_ITEMS:]:
        if len(present(edges, it)) != 1:
            raise SystemExit(f'kept notch item {it} not on the board exactly once: stop')
    old = [present(edges, it) for it in cf.RIGHT_NOTCH_USB_OLD]
    new = [present(edges, it) for it in cf.RIGHT_NOTCH_USB_TOP]
    if any(len(x) > 1 for x in old + new):
        raise SystemExit('an edge item is on the board twice: stop')
    n_old, n_new = sum(map(len, old)), sum(map(len, new))
    if n_old == len(old) and n_new == 0:
        return 'todo', [x[0] for x in old]
    if n_old == 0 and n_new == len(new):
        return 'applied', [x[0] for x in new]
    raise SystemExit(f'partly applied ({n_old}/{len(old)} old, {n_new}/{len(new)} new items): stop')


def courtyard_bottom(board):
    fp = board.FindFootprintByReference(COURTYARD_REF)
    return rl.mm(fp.GetCourtyard(pcbnew.F_CrtYd).BBox().GetBottom())


def check_top_y(board):
    """CUT_TOP_Y_USB must be the recorded value and clear J2's courtyard by COURTYARD_GAP_MM."""
    need = math.ceil(round((courtyard_bottom(board) + COURTYARD_GAP_MM) / TOP_Y_STEP_MM, 6)) * TOP_Y_STEP_MM
    if cf.CUT_TOP_Y_USB < need - 1e-9:
        raise SystemExit(f'top edge {cf.CUT_TOP_Y_USB} above the J2 courtyard limit {need:.3f}: stop')
    return need


# ---------------------------------------------------------------- edits

def replace_edges(board, old):
    for s in old:
        if s.GetWidth() != cf.EDGE_WIDTH_NM or not s.IsLocked():
            raise SystemExit('old edge item width / lock not as recorded: stop')
    template = old[0]
    keep_alive = list(old)                       # proxies must outlive the save (lessons doc)
    for s in old:
        board.Remove(s)
    for it in cf.RIGHT_NOTCH_USB_TOP:
        n13.add_edge(board, it, template)
    return keep_alive


def gnd_fills(board):
    return [next(z for z in board.Zones() if z.GetZoneName() == n).GetFilledPolysList(layer) for n, layer in GND_ZONES]


def holes(board):
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetDrillSize().x > 0:
                out.append((rl.mm(p.GetPosition().x), rl.mm(p.GetPosition().y), rl.mm(p.GetDrillSize().x) / 2))
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            out.append((rl.mm(t.GetPosition().x), rl.mm(t.GetPosition().y), rl.mm(t.GetDrillValue()) / 2))
    return out


def stitch_candidates(board):
    """Grid points of script 11's column inside the restored strip (grid phase from the column's surviving vias)."""
    col = n13.stitch_vias(board, STITCH_COL_X)
    if not col:
        raise SystemExit('no surviving via on the stitching column to take the grid from: stop')
    y0 = rl.mm(col[0].GetPosition().y)
    x = rl.mm(col[0].GetPosition().x)
    for v in col:
        k = (rl.mm(v.GetPosition().y) - y0) / STITCH_PITCH_MM
        if abs(k - round(k)) * STITCH_PITCH_MM > GRID_TOL_MM:
            raise SystemExit('stitching column vias are off the grid: stop')
    k0 = math.ceil((RESTORED_Y[0] - y0) / STITCH_PITCH_MM)
    k1 = math.floor((RESTORED_Y[1] - y0) / STITCH_PITCH_MM)
    return [(x, round(y0 + k * STITCH_PITCH_MM, 6)) for k in range(k0, k1 + 1)]


def via_fits(board, ps, lines, fills, hole_list, xy):
    if not n13.via_ok(ps, lines, xy):
        return 'edge'
    r = VIA_DIA_MM / 2 + STITCH_MARGIN_MM
    ring = [rl.P(xy[0] + r * math.cos(2 * math.pi * k / STITCH_SAMPLES),
                 xy[1] + r * math.sin(2 * math.pi * k / STITCH_SAMPLES)) for k in range(STITCH_SAMPLES)]
    if not all(f.Contains(p) for f in fills for p in ring + [rl.P(*xy)]):
        return 'fill'
    if any(math.hypot(xy[0] - hx, xy[1] - hy) < VIA_DRILL_MM / 2 + hr + STITCH_HOLE_MM for hx, hy, hr in hole_list):
        return 'hole'
    return None


def add_stitching(board):
    ps = n13.outline_poly(board)
    lines = [n13.shape_polyline(s) for s in n13.edge_shapes(board)]
    fills, hole_list = gnd_fills(board), holes(board)
    added, skipped = [], []
    for xy in stitch_candidates(board):
        why = via_fits(board, ps, lines, fills, hole_list, xy)
        if why:
            skipped.append((xy, why))
            continue
        rl.add_via(board, VIA_NET, xy, VIA_DIA_MM, VIA_DRILL_MM)
        hole_list.append((xy[0], xy[1], VIA_DRILL_MM / 2))
        added.append(xy)
    return added, skipped


def save(board, before_text, path):
    pcbnew.SaveBoard(str(path), board)
    keep = rl.uuids_in(before_text)
    text = path.read_text(encoding='utf-8')
    text = n13.reseed_shapes(rl.reseed_uuids(text, keep, NAMESPACE), keep, NAMESPACE)
    path.write_text(text, encoding='utf-8', newline='')
    b2 = pcbnew.LoadBoard(str(path))
    pcbnew.SaveBoard(str(path), b2)


# ---------------------------------------------------------------- post-checks

def endpoints_exact(board):
    """Every endpoint of the notch path is shared by exactly two Edge.Cuts shapes, to the nm (the lead's own
    outline elsewhere has a 1 nm near-miss: not this script's to fix)."""
    count = {}
    for s in n13.edge_shapes(board):
        for p in (s.GetStart(), s.GetEnd()):
            count[(p.x, p.y)] = count.get((p.x, p.y), 0) + 1
    ends = {(rl.nm(it[k][0]), rl.nm(it[k][1])) for it in cf.RIGHT_NOTCH_USB_PATH for k in (1, 2)}
    bad = [(rl.mm(x), rl.mm(y)) for (x, y) in ends if count.get((x, y), 0) != 2]
    if bad:
        raise SystemExit(f'post-check: Edge.Cuts endpoints not shared exactly: {bad}: stop')


def necks(board, new):
    """(top, bottom) neck: the cut edge items (not the x = RIGHT_X lines) against the lead's edges above / below."""
    by_item = dict(zip(cf.RIGHT_NOTCH_USB_TOP, new))
    edges = n13.edge_shapes(board)
    kept = [present(edges, it)[0] for it in cf.RIGHT_NOTCH_PATH[cf.USB_TOP_ITEMS:]]
    notch_ids = {s.m_Uuid.AsString() for s in new + kept}
    lead = [n13.shape_polyline(s) for s in edges if s.m_Uuid.AsString() not in notch_ids]
    is_outer = lambda it: it[0] == 'line' and abs(it[1][0] - cf.RIGHT_X) < 1e-9 and abs(it[2][0] - cf.RIGHT_X) < 1e-9
    top_cut = [n13.shape_polyline(by_item[it]) for it in cf.RIGHT_NOTCH_USB_TOP if not is_outer(it)]
    bot_cut = [n13.shape_polyline(s) for s, it in zip(kept, cf.RIGHT_NOTCH_PATH[cf.USB_TOP_ITEMS:]) if not is_outer(it)]
    top_lead = [ln for ln in lead if max(p[1] for p in ln) < cf.CUT_TOP_Y_USB]
    bot_lead = [ln for ln in lead if min(p[1] for p in ln) > cf.CUT_BOT_Y]
    return (min(n13.line_line(u, v) for u in top_lead for v in top_cut),
            min(n13.line_line(u, v) for u in bot_lead for v in bot_cut))


def copper_near_edge(board, ps, lines):
    bad = []
    near = lambda item: rl.mm(item.GetBoundingBox().GetRight()) >= n13.CHECK_X_MIN
    j2_gap = math.inf
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if not p.IsOnCopperLayer() or not (near(p) or fp.GetReference() == COURTYARD_REF):
                continue
            for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                if not p.IsOnLayer(layer):
                    continue
                poly = p.GetEffectivePolygon(layer)
                pts = [(rl.mm(poly.CVertex(i).x), rl.mm(poly.CVertex(i).y)) for i in range(poly.TotalVertices())]
                gap = min(n13.edge_dist(lines, q) for q in pts)
                if fp.GetReference() == COURTYARD_REF:
                    j2_gap = min(j2_gap, gap)
                if not n13.inside(ps, (rl.mm(p.GetPosition().x), rl.mm(p.GetPosition().y))) or \
                        gap < COPPER_EDGE_MM - 1e-6:
                    bad.append(f'{fp.GetReference()}.{p.GetNumber()}')
    for t in board.GetTracks():
        if not near(t):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            xy = (rl.mm(t.GetPosition().x), rl.mm(t.GetPosition().y))
            if not n13.via_ok(ps, lines, xy):
                bad.append(f'via {xy}')
        else:
            a = (rl.mm(t.GetStart().x), rl.mm(t.GetStart().y))
            b = (rl.mm(t.GetEnd().x), rl.mm(t.GetEnd().y))
            gap = min(n13.line_line([a, b], ln) for ln in lines) - rl.mm(t.GetWidth()) / 2
            if not (n13.inside(ps, a) and n13.inside(ps, b)) or gap < COPPER_EDGE_MM - 1e-6:
                bad.append(f'track {a}-{b}')
    if bad:
        raise SystemExit(f'post-check: copper too close to the edge or outside the board: {bad}: stop')
    if j2_gap < J2_PAD_EDGE_MIN_MM:
        raise SystemExit(f'post-check: J2 pad copper {j2_gap:.3f} mm from the edge: stop')
    return j2_gap


def restored_vias(board):
    return [(rl.mm(v.GetPosition().x), rl.mm(v.GetPosition().y)) for v in n13.stitch_vias(board, STITCH_COL_X)
            if RESTORED_Y[0] <= rl.mm(v.GetPosition().y) <= RESTORED_Y[1]]


def post_checks(board):
    state, new = edge_state(board)
    if state != 'applied':
        raise SystemExit('post-check: the new edge is not on the board: stop')
    endpoints_exact(board)
    ps = n13.outline_poly(board)
    lines = [n13.shape_polyline(s) for s in n13.edge_shapes(board)]
    nk = necks(board, new)
    if min(nk) < NECK_MIN_MM:
        raise SystemExit(f'post-check: necks {nk} under {NECK_MIN_MM} mm: stop')
    j2_gap = copper_near_edge(board, ps, lines)
    labs = n13.labels(board, n13.LABEL_X_NEW)
    gaps = [n13.bbox_edge_gap(lines, d.GetBoundingBox()) for d in labs]
    if not labs or min(gaps) < n13.LABEL_EDGE_GAP_MM:
        raise SystemExit(f'post-check: label edge gaps {gaps}: stop')
    vias = restored_vias(board)
    if not vias:
        raise SystemExit('post-check: no stitching via in the restored strip: stop')
    fills, hole_list = gnd_fills(board), holes(board)
    for xy in vias:
        others = [h for h in hole_list if math.hypot(h[0] - xy[0], h[1] - xy[1]) > 1e-6]
        why = via_fits(board, ps, lines, fills, others, xy)
        if why and why != 'fill':
            raise SystemExit(f'post-check: via {xy} fails ({why}): stop')
    return nk, j2_gap, min(gaps), vias


def report(board, tag):
    nk, j2_gap, lab_gap, vias = post_checks(board)
    print(f'{tag}: top edge y {cf.CUT_TOP_Y_USB:.3f} (J2 courtyard bottom {courtyard_bottom(board):.4f}); necks top '
          f'{nk[0]:.4f} / bottom {nk[1]:.4f} mm; J2 pad copper to edge {j2_gap:.3f} mm; label edge gap '
          f'{lab_gap:.3f} mm; stitching vias in the restored strip {vias}')


# ---------------------------------------------------------------- main

def run_check_fixed_accept():
    r = subprocess.run([sys.executable, '-I', str(rl.CHECK_FIXED), '--accept-lead-change', LEAD_CHANGE],
                       capture_output=True, text=True, timeout=rl.CHECK_TIMEOUT_S)
    print('  ' + (r.stdout.strip().splitlines() or ['?'])[-1])
    if r.returncode != 0:
        raise SystemExit(f'check_fixed --accept-lead-change failed:\n{r.stdout[-2000:]}{r.stderr[-1000:]}')


def scratch_copy():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    for src in (rl.PCB, rl.PRO, rl.DRU):
        shutil.copy2(src, SCRATCH / src.name)
    return SCRATCH / rl.PCB.name


def main():
    pcb = rl.PCB
    rl.guard_locks()
    board = pcbnew.LoadBoard(str(pcb))
    state, items = edge_state(board)
    rl.check_fixed(pcb)
    if state == 'applied':
        report(board, 'already applied')
        print('nothing saved')
        return
    need = check_top_y(board)
    print(f'  J2 courtyard bottom {courtyard_bottom(board):.4f} mm; top edge limit {need:.3f}; '
          f'top edge {cf.CUT_TOP_Y_USB:.3f}')
    work = scratch_copy()
    before_text = pcb.read_text(encoding='utf-8')
    b = pcbnew.LoadBoard(str(work))
    _, old = edge_state(b)
    keep_alive = replace_edges(b, old)
    n13.outline_poly(b)
    save(b, before_text, work)
    del keep_alive
    rl.refill(work)
    b = pcbnew.LoadBoard(str(work))
    added, skipped = add_stitching(b)
    print(f'  stitching vias added {added}; skipped {skipped}')
    if not added:
        raise SystemExit('no stitching via fits the restored strip: stop (nothing saved)')
    save(b, before_text, work)
    rl.refill(work)
    report(pcbnew.LoadBoard(str(work)), '  scratch')
    if '--dry-run' in sys.argv:
        print(f'dry run: result in {work}; nothing saved to the master')
        return
    rl.backup(pcb)
    shutil.copyfile(work, pcb)
    shutil.rmtree(SCRATCH)
    run_check_fixed_accept()
    rl.check_fixed(pcb)
    report(pcbnew.LoadBoard(str(pcb)), '  applied')


if __name__ == '__main__':
    main()
