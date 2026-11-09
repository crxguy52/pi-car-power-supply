"""Post-route edit 17 (2026-11-09, project lead's review): references from F.Fab to F.Silkscreen; track debris removed.

Run with KiCad's python from the project root (KiCad must not have the board open):

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" -I tools/post_route/17_silk_refs.py [--dry-run] [--root DIR]

--root DIR works on DIR/pi_power_board.kicad_pcb (a scratch copy with the project files); default: the master.

What and why (project lead 2026-11-09, after the lead's own GUI edits of the buck block):
- References: 06 / 11 / 16 put every reference that overlapped a pad, a via or other silk on F.Fab (assembly
  drawing tools/render_assembly.py). The lead wants them on the silkscreen. Every visible F.Fab reference moves to
  F.Silkscreen at REF_SIZE_MM / REF_THICK_MM (the size of the references already on silk). Its spot: the first
  free one, searching outward from the part's courtyard centre (angle 0 and 90 deg, STEP_MM grid, at most
  SEARCH_MM beyond the courtyard). Free = clear of every pad's copper (PAD_CLEAR_MM: the fab clips silk at mask
  openings), of vias (VIA_CLEAR_MM), of every other silk item and placed reference (SILK_CLEAR_MM), of other
  parts' bodies (courtyard shrunk by COURTYARD_SHRINK_MM, so a label can't be read as a neighbour's), and inside
  the outline by EDGE_CLEAR_MM. A reference with no free spot still goes to silk, at its courtyard centre: the
  lead asked for these to be left in violation and fixed by hand in the GUI. They are printed.
  Second pass (staff review 2026-11-09: U8's label landed above D3, next to D3's own, and C31's sat between C18
  and C31): a placed reference whose text box is not strictly nearer its own courtyard than every other part's
  (nearest_own) is searched again with that test added, the other references fixed; with no such spot it stays.
  Hidden references (MH1-MH4) stay hidden on F.Fab. References already on silk are not moved.
- Debris (lead review 2026-11-09): segments lying wholly on a wider-or-equal collinear segment of the same net
  and layer are deleted; micro-segments (length <= MICRO_MM: Freerouting / GUI kinks, zero-length dots) are deleted
  and the same-net tracks ending at their far end are snapped to the kept end (the end in a via / pad, if one is),
  so nothing is cut apart; of the two ends, one whose snap keeps every moved track's clearance (route review
  2026-11-09: a snap toward U5 pin 4 broke the 0.2 mm rule by 5 um). A micro-segment joining two different vias /
  pads, or with no clear option, is left. Zones refilled
  (route_lib.refill).

Guards: every reference is on F.Fab or F.Silkscreen (else stop); "already applied" when no visible F.Fab reference
and no debris is left. Footprints, pads, nets, zones and every other track are not touched. Backup first.
"""
import math
import pathlib
import sys

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import route_lib  # noqa: E402

STEM = 'pi_power_board'
REF_SIZE_MM = 0.8
REF_THICK_MM = 0.12
PAD_CLEAR_MM = 0.15
VIA_CLEAR_MM = 0.1
SILK_CLEAR_MM = 0.1
COURTYARD_SHRINK_MM = 0.25
EDGE_CLEAR_MM = 0.3
SEARCH_MM = 2.0
STEP_MM = 0.25
ANGLES = (0.0, 90.0)
COLLINEAR_TOL_NM = 1e3
MICRO_MM = 50e-3
FAB_LAYERS = ('F.Fab',)
SILK_LAYERS = ('F.Silkscreen',)


def nm(v):
    return pcbnew.FromMM(v)


def box(bb, grow=0.0):
    return (bb.GetLeft() / 1e6 - grow, bb.GetTop() / 1e6 - grow, bb.GetRight() / 1e6 + grow, bb.GetBottom() / 1e6 + grow)


def gap(a, b):
    """Distance between boxes a and b (0 when they touch or overlap)."""
    return math.hypot(max(b[0] - a[2], 0.0, a[0] - b[2]), max(b[1] - a[3], 0.0, a[1] - b[3]))


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def crt_box(fp):
    c = fp.GetCourtyard(pcbnew.F_CrtYd)
    return box(c.BBox()) if c.OutlineCount() else box(fp.GetBoundingBox(False))


# ---------------------------------------------------------------- references

def obstacles(board, movers):
    """(pads, vias, silk, bodies) boxes in mm. silk excludes the references being moved."""
    pads, silk, bodies = [], [], []
    for f in board.GetFootprints():
        for p in f.Pads():
            pads.append(box(p.GetBoundingBox(), PAD_CLEAR_MM))
        for g in f.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS:
                silk.append(box(g.GetBoundingBox(), SILK_CLEAR_MM))
        for t in (f.Reference(), f.Value()):
            if t.GetLayer() == pcbnew.F_SilkS and t.IsVisible() and f.GetReference() not in movers:
                silk.append(box(t.GetBoundingBox(), SILK_CLEAR_MM))
        c = crt_box(f)
        bodies.append((f.GetReference(), (c[0] + COURTYARD_SHRINK_MM, c[1] + COURTYARD_SHRINK_MM,
                                          c[2] - COURTYARD_SHRINK_MM, c[3] - COURTYARD_SHRINK_MM)))
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS:
            silk.append(box(d.GetBoundingBox(), SILK_CLEAR_MM))
    vias = [box(v.GetBoundingBox(), VIA_CLEAR_MM) for v in board.GetTracks() if v.Type() == pcbnew.PCB_VIA_T]
    return pads, vias, silk, bodies


def inside_outline(outline, tb):
    r = pcbnew.SHAPE_POLY_SET()
    r.NewOutline()
    x0, y0, x1, y1 = (tb[0] - EDGE_CLEAR_MM, tb[1] - EDGE_CLEAR_MM, tb[2] + EDGE_CLEAR_MM, tb[3] + EDGE_CLEAR_MM)
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        r.Append(nm(x), nm(y))
    r.BooleanSubtract(outline)
    return r.OutlineCount() == 0


def spots(cb):
    """Candidate text centres, nearest the courtyard first."""
    cx, cy = (cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2
    rx, ry = (cb[2] - cb[0]) / 2 + SEARCH_MM, (cb[3] - cb[1]) / 2 + SEARCH_MM
    nx, ny = int(rx / STEP_MM), int(ry / STEP_MM)
    out = [(cx + i * STEP_MM, cy + j * STEP_MM) for i in range(-nx, nx + 1) for j in range(-ny, ny + 1)]
    out.sort(key=lambda p: (math.hypot(p[0] - cx, p[1] - cy), p))
    return out


def nearest_own(tb, ref, fps):
    """The text box is strictly nearer its own part's courtyard than any other part's (staff review 17)."""
    own = gap(tb, crt_box(fps[ref]))
    return all(own < gap(tb, crt_box(f)) for r, f in fps.items() if r != ref)


def place_refs(board, refs, own_test=False):
    """Spot search (docstring). own_test: also require nearest_own; a ref with no such spot is left where it is
    and returned in `violating` (nothing moved)."""
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    pads, vias, silk, bodies = obstacles(board, set(refs))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    placed, violating = {}, []
    for ref in refs:
        fp = fps[ref]
        t = fp.Reference()
        before = (t.GetPosition(), t.GetTextAngleDegrees())
        t.SetLayer(pcbnew.F_SilkS)
        t.SetVisible(True)
        t.SetTextSize(pcbnew.VECTOR2I(nm(REF_SIZE_MM), nm(REF_SIZE_MM)))
        t.SetTextThickness(nm(REF_THICK_MM))
        t.SetKeepUpright(True)
        cb = crt_box(fp)
        others = [b for r, b in bodies if r != ref]
        found = None
        for x, y in spots(cb):
            for ang in ANGLES:
                t.SetTextAngleDegrees(ang)
                t.SetPosition(pcbnew.VECTOR2I(nm(x), nm(y)))
                tb = box(t.GetBoundingBox())
                if (any(overlap(tb, o) for o in pads) or any(overlap(tb, o) for o in vias)
                        or any(overlap(tb, o) for o in silk) or any(overlap(tb, o) for o in others)
                        or not inside_outline(outline, tb) or (own_test and not nearest_own(tb, ref, fps))):
                    continue
                found = (x, y, ang)
                break
            if found:
                break
        if found is None and own_test:
            t.SetPosition(before[0])
            t.SetTextAngleDegrees(before[1])
            x, y, ang = before[0].x / 1e6, before[0].y / 1e6, before[1]
            violating.append(ref)
        elif found is None:
            x, y = (cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2
            ang = 90.0 if (cb[3] - cb[1]) > (cb[2] - cb[0]) else 0.0
            t.SetTextAngleDegrees(ang)
            t.SetPosition(pcbnew.VECTOR2I(nm(x), nm(y)))
            violating.append(ref)
        else:
            x, y, ang = found
        silk.append(box(t.GetBoundingBox(), SILK_CLEAR_MM))
        placed[ref] = (round(x, 3), round(y, 3), ang)
    return placed, violating


# ---------------------------------------------------------------- debris

def on_segment(p, a, b):
    """p lies on segment a-b (within COLLINEAR_TOL_NM)."""
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(p.x - ax, p.y - ay) <= COLLINEAR_TOL_NM
    s = ((p.x - ax) * dx + (p.y - ay) * dy) / L2
    if s < -1e-9 or s > 1 + 1e-9:
        return False
    return math.hypot(ax + s * dx - p.x, ay + s * dy - p.y) <= COLLINEAR_TOL_NM


def near(p, q):
    return math.hypot(p.x - q.x, p.y - q.y) <= COLLINEAR_TOL_NM


def anchors(board, t, p):
    """Same-net vias / pads on t's layer that contain point p (uuids)."""
    out = set()
    for v in board.GetTracks():
        if v.Type() == pcbnew.PCB_VIA_T and v.GetNetCode() == t.GetNetCode() and v.HitTest(p):
            out.add(v.m_Uuid.AsString())
    for f in board.GetFootprints():
        for pd in f.Pads():
            if pd.GetNetCode() == t.GetNetCode() and pd.IsOnLayer(t.GetLayer()) and pd.HitTest(p):
                out.add(pd.m_Uuid.AsString())
    return out


def ends_at(tracks, t, p):
    """(track, 'start' | 'end') of same-net, same-layer tracks other than t with an end at p."""
    out = []
    for o in tracks:
        if o is t or o.GetNetCode() != t.GetNetCode() or o.GetLayer() != t.GetLayer():
            continue
        if near(o.GetStart(), p):
            out.append((o, 'start'))
        if near(o.GetEnd(), p):
            out.append((o, 'end'))
    return out


def find_fix(board, tracks):
    """Next debris fix: (segment, why, [(track, end, new point)]) or None. Contained first, then micro-segments."""
    for t in tracks:
        if t.GetLength() <= MICRO_MM * 1e6:
            continue
        for o in tracks:
            if (o is not t and o.GetNetCode() == t.GetNetCode() and o.GetLayer() == t.GetLayer()
                    and o.GetWidth() >= t.GetWidth() and o.GetLength() > MICRO_MM * 1e6
                    and on_segment(t.GetStart(), o.GetStart(), o.GetEnd())
                    and on_segment(t.GetEnd(), o.GetStart(), o.GetEnd())):
                return t, 'contained', []
    for t in tracks:
        if t.GetLength() > MICRO_MM * 1e6:
            continue
        a, b = t.GetStart(), t.GetEnd()
        aa, ab = anchors(board, t, a), anchors(board, t, b)
        if aa and ab and not (aa & ab):
            continue                 # two different anchors: deleting it would cut them apart
        options = [(b, a)] if ab and not aa else [(a, b)] if aa and not ab else [(a, b), (b, a)]
        for keep, other in options:
            moves = [(o, end, pcbnew.VECTOR2I(keep.x, keep.y)) for o, end in ends_at(tracks, t, other)]
            if clear_after(board, t, moves):
                return t, 'micro', moves
    return None


def clear_after(board, t, moves):
    """The moved tracks keep their clearance to other-net pads and tracks on their layer (checked, then undone)."""
    old = [(o, end, o.GetStart() if end == 'start' else o.GetEnd()) for o, end, _ in moves]
    for o, end, p in moves:
        (o.SetStart if end == 'start' else o.SetEnd)(p)
    ok = True
    others = [x for x in board.GetTracks() if x is not t] + [pd for f in board.GetFootprints() for pd in f.Pads()]
    for o, _, _ in moves:
        lay = o.GetLayer()
        shape = o.GetEffectiveShape(lay)
        for x in others:
            if x.GetNetCode() == o.GetNetCode() or not x.IsOnLayer(lay):
                continue
            need = max(o.GetOwnClearance(lay), x.GetOwnClearance(lay))
            if shape.Collide(x.GetEffectiveShape(lay), need - 1):
                ok = False
                break
        if not ok:
            break
    for o, end, p in old:
        (o.SetStart if end == 'start' else o.SetEnd)(p)
    return ok


def clean_debris(board):
    """Find contained and micro-segments and snap their neighbours to the kept end (in memory).
    Returns (report lines, segments to remove): the caller removes them just before saving, because pcbnew's
    Python lists of the board's items break once an item is removed."""
    lines, removed, doomed = [], set(), []
    while True:
        tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T
                  and t.m_Uuid.AsString() not in removed]
        fix = find_fix(board, tracks)
        if fix is None:
            for t in tracks:
                if t.GetLength() <= MICRO_MM * 1e6:
                    print('  left (no safe fix)', describe(board, t, 'micro'))
            return lines, doomed
        t, why, moves = fix
        lines.append(describe(board, t, why) + (f'; {len(moves)} neighbour end(s) snapped' if moves else ''))
        for o, end, p in moves:
            (o.SetStart if end == 'start' else o.SetEnd)(p)
        removed.add(t.m_Uuid.AsString())
        doomed.append(t)


def describe(board, t, why):
    a, b = t.GetStart(), t.GetEnd()
    return (f'{why:11s} {t.GetNetname():10s} {board.GetLayerName(t.GetLayer()):5s} '
            f'({a.x / 1e6:.3f},{a.y / 1e6:.3f})->({b.x / 1e6:.3f},{b.y / 1e6:.3f}) w{t.GetWidth() / 1e6:.2f}')


# ---------------------------------------------------------------- main

def main():
    argv = sys.argv[1:]
    dry = '--dry-run' in argv
    root = pathlib.Path(argv[argv.index('--root') + 1]).resolve() if '--root' in argv else ROOT
    pcb = root / f'{STEM}.kicad_pcb'
    board = pcbnew.LoadBoard(str(pcb))
    movers = []
    for f in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        lay = board.GetLayerName(f.Reference().GetLayer())
        if lay not in FAB_LAYERS + SILK_LAYERS:
            raise SystemExit(f'unexpected state: {f.GetReference()} reference on {lay}')
        if lay in FAB_LAYERS and f.Reference().IsVisible():
            movers.append(f.GetReference())
    junk, doomed = clean_debris(board)
    if not movers and not junk:
        print('already applied')
        return 0
    for line in junk:
        print('  delete', line)
    placed, violating = place_refs(board, movers)
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    ambiguous = [r for r in movers if r not in violating
                 and not nearest_own(box(fps[r].Reference().GetBoundingBox()), r, fps)]
    replaced, kept = place_refs(board, ambiguous, own_test=True)
    placed.update(replaced)
    for ref in ambiguous:
        print(f'  {ref:5s} nearer another part: ' + ('kept (no unambiguous free spot)' if ref in kept else 're-placed'))
    for ref, (x, y, a) in placed.items():
        print(f'  {ref:5s} silk at ({x:.3f}, {y:.3f}) {a:.0f} deg' + ('  NO FREE SPOT (left in violation)'
                                                                      if ref in violating else ''))
    print(f'{len(movers)} references to silk ({len(violating)} without a free spot: {", ".join(violating) or "-"}); '
          f'{len(junk)} debris segments')
    if dry:
        print('dry run: nothing written')
        return 0
    if root == ROOT:
        route_lib.backup(pcb)
    for t in doomed:
        board.Remove(t)
    pcbnew.SaveBoard(str(pcb), board)
    route_lib.refill(pcb)
    print('applied; zones refilled')
    return 0


if __name__ == '__main__':
    sys.exit(main())
