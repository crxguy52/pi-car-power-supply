"""Shared helpers for the routing scripts 04-06 (KiCad python). Not an edit script itself.

- geometry in mm (Y down, KiCad frame); rect unions -> zone outlines;
- item creation (tracks, vias, zones) and an item key for "already applied" checks (the scripts' ledger: every
  item a script creates is listed in the script itself, so a re-run compares keys instead of guessing);
- uuid reseeding of the items a script created (uuid5 from the item content), so two runs from the same input give
  the same file;
- backup, lock-file guard, tools/check_fixed.py, refill.
"""
import datetime
import math
import pathlib
import re
import shutil
import subprocess
import sys
import uuid

import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[2]
STEM = 'pi_power_board'
PCB = ROOT / f'{STEM}.kicad_pcb'
PRO = ROOT / f'{STEM}.kicad_pro'
DRU = ROOT / f'{STEM}.kicad_dru'
BACKUPS = ROOT / f'{STEM}-backups'
BUILD = ROOT / 'build'
CHECK_FIXED = ROOT / 'tools' / 'check_fixed.py'
CHECK_TIMEOUT_S = 300

F, B = pcbnew.F_Cu, pcbnew.B_Cu
NM_PER_MM = 1e6


def nm(v):
    return int(round(v * NM_PER_MM))


def mm(v):
    return v / NM_PER_MM


def P(x, y):
    return pcbnew.VECTOR2I(nm(x), nm(y))


# ---------------------------------------------------------------- guards, backup, save

def guard_locks():
    locks = sorted(ROOT.glob('~*.lck'))
    if locks:
        raise SystemExit(f'KiCad lock files present ({[p.name for p in locks]}): close KiCad first')


def backup(path=PCB):
    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    dst = BACKUPS / f'{path.stem}_{stamp}{path.suffix}'
    shutil.copy2(path, dst)
    print(f'backup {dst.relative_to(ROOT)}')
    return dst


def check_fixed(board_path=PCB):
    r = subprocess.run([sys.executable, '-I', str(CHECK_FIXED), str(board_path)], capture_output=True, text=True,
                       timeout=CHECK_TIMEOUT_S)
    last = (r.stdout.strip().splitlines() or ['?'])[-1]
    print(f'check_fixed: {last}')
    if r.returncode != 0:
        raise SystemExit(f'check_fixed FAILED:\n{r.stdout[-2000:]}{r.stderr[-1000:]}')


def uuids_in(text):
    return set(re.findall(r'\(uuid "([0-9a-f-]+)"\)', text))


ITEM_START = re.compile(r'^\t\((segment|via|arc|zone)\b', re.M)


def _block_end(text, i):
    depth = 0
    j = i
    in_str = False
    while j < len(text):
        c = text[j]
        if in_str:
            if c == '\\':
                j += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    raise ValueError('unbalanced block')


def reseed_uuids(text, keep, namespace):
    """Give every segment/via/arc/zone whose uuid is not in `keep` a uuid5 from its content (zones: from their
    name). Duplicate contents get an index."""
    ns = uuid.uuid5(uuid.NAMESPACE_URL, namespace)
    out, pos, seen = [], 0, {}
    for m in ITEM_START.finditer(text):
        i = m.start() + 1
        j = _block_end(text, i)
        block = text[i:j]
        um = re.search(r'\(uuid "([0-9a-f-]+)"\)', block)
        if um and um.group(1) not in keep:
            if m.group(1) == 'zone':
                nmatch = re.search(r'\(name "([^"]*)"\)', block)
                basis = 'zone/' + (nmatch.group(1) if nmatch else block[:200])
            else:
                basis = re.sub(r'\(uuid "[0-9a-f-]+"\)', '', block)
            k = seen.get(basis, 0)
            seen[basis] = k + 1
            new = str(uuid.uuid5(ns, f'{basis}#{k}'))
            block = block[:um.start(1)] + new + block[um.end(1):]
        out.append(text[pos:i])
        out.append(block)
        pos = j
    out.append(text[pos:])
    return ''.join(out)


def save(board, before_text, namespace, path=PCB):
    """Save, reseed the uuids of the new items, then load and save once more (KiCad orders items by uuid)."""
    pcbnew.SaveBoard(str(path), board)
    keep = uuids_in(before_text)
    text = path.read_text(encoding='utf-8')
    path.write_text(reseed_uuids(text, keep, namespace), encoding='utf-8', newline='')
    b2 = pcbnew.LoadBoard(str(path))
    pcbnew.SaveBoard(str(path), b2)


def refill(board_path=PCB):
    """Reload (project rules in force) and fill one priority level at a time, highest first."""
    board = pcbnew.LoadBoard(str(board_path))
    board.BuildConnectivity()
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    filler = pcbnew.ZONE_FILLER(board)
    for prio in sorted({z.GetAssignedPriority() for z in zones}, reverse=True):
        level = pcbnew.ZONES()
        for z in zones:
            if z.GetAssignedPriority() == prio:
                level.append(z)
        if not filler.Fill(level):
            raise SystemExit('zone fill failed')
    pcbnew.SaveBoard(str(board_path), board)
    return board


# ---------------------------------------------------------------- items

def net(board, name):
    n = board.FindNet(name)
    if n is None or n.GetNetCode() <= 0:
        raise SystemExit(f'net {name} not on the board')
    return n


def rects_poly(rects):
    ps = pcbnew.SHAPE_POLY_SET()
    for x0, y0, x1, y1 in rects:
        if not (x1 > x0 and y1 > y0):
            raise SystemExit(f'bad rect {(x0, y0, x1, y1)}')
        r = pcbnew.SHAPE_POLY_SET()
        r.NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            r.Append(nm(x), nm(y))
        ps.BooleanAdd(r)
    ps.Simplify()
    return ps


def add_zone(board, name, netname, layer, rects, priority, clearance, min_width, connection, locked=True,
             thermal_gap=0.3, spoke=0.5):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net(board, netname))
    z.SetZoneName(name)
    # copy the vertices: ZONE.SetOutline takes ownership of a pointer Python also frees (crash on save)
    ps = rects_poly(rects)
    o = z.Outline()
    o.RemoveAllContours()
    for k in range(ps.OutlineCount()):
        if ps.HoleCount(k):
            raise SystemExit(f'zone {name}: rect union has holes')
        o.NewOutline()
        line = ps.Outline(k)
        for i in range(line.PointCount()):
            pt = line.CPoint(i)
            o.Append(pt.x, pt.y)
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(nm(clearance))
    z.SetMinThickness(nm(min_width))
    z.SetPadConnection(connection)
    z.SetThermalReliefGap(nm(thermal_gap))
    z.SetThermalReliefSpokeWidth(nm(spoke))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetLocked(locked)
    board.Add(z)
    return z


def add_track(board, netname, layer, a, b, width, locked=True):
    t = pcbnew.PCB_TRACK(board)
    t.SetLayer(layer)
    t.SetStart(P(*a))
    t.SetEnd(P(*b))
    t.SetWidth(nm(width))
    t.SetNet(net(board, netname))
    t.SetLocked(locked)
    board.Add(t)
    return t


def add_path(board, netname, layer, pts, width, locked=True):
    return [add_track(board, netname, layer, pts[i], pts[i + 1], width, locked) for i in range(len(pts) - 1)]


def add_via(board, netname, xy, dia, drill, locked=True):
    v = pcbnew.PCB_VIA(board)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetPosition(P(*xy))
    v.SetLayerPair(F, B)
    v.SetWidth(nm(dia))
    v.SetDrill(nm(drill))
    v.SetNet(net(board, netname))
    v.SetLocked(locked)
    board.Add(v)
    return v


def track_key(t):
    if t.Type() == pcbnew.PCB_VIA_T:
        p = t.GetPosition()
        return ('via', t.GetNetname(), p.x, p.y, t.GetWidth(F), t.GetDrillValue())
    s, e = t.GetStart(), t.GetEnd()
    a, b = sorted(((s.x, s.y), (e.x, e.y)))
    return ('trk', t.GetNetname(), t.GetLayer(), a, b, t.GetWidth())


def planned_track_key(netname, layer, a, b, width):
    p, q = sorted(((nm(a[0]), nm(a[1])), (nm(b[0]), nm(b[1]))))
    return ('trk', netname, layer, p, q, nm(width))


def planned_via_key(netname, xy, dia, drill):
    return ('via', netname, nm(xy[0]), nm(xy[1]), nm(dia), nm(drill))


# ---------------------------------------------------------------- obstacle geometry (mm) for via searches

def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def rect_dist(p, r):
    x0, y0, x1, y1 = r
    dx = max(x0 - p[0], 0.0, p[0] - x1)
    dy = max(y0 - p[1], 0.0, p[1] - y1)
    return math.hypot(dx, dy)


def seg_seg_dist(a, b, c, d):
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2, d3, d4 = cross(c, d, a), cross(c, d, b), cross(a, b, c), cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(seg_dist(a, c, d), seg_dist(b, c, d), seg_dist(c, a, b), seg_dist(d, a, b))


def seg_rect_dist(a, b, r):
    x0, y0, x1, y1 = r
    if x0 <= a[0] <= x1 and y0 <= a[1] <= y1:
        return 0.0
    edges = (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))
    return min(seg_seg_dist(a, b, c, d) for c, d in edges)


class Obstacle:
    """A copper shape on a set of layers: ('rect', x0, y0, x1, y1), ('circle', cx, cy, r) or ('seg', a, b, half)."""

    def __init__(self, netname, layers, shape, hole=None):
        self.net, self.layers, self.shape, self.hole = netname, layers, shape, hole

    def dist_pt(self, p):
        k = self.shape[0]
        if k == 'rect':
            return rect_dist(p, self.shape[1:])
        if k == 'circle':
            return math.hypot(p[0] - self.shape[1], p[1] - self.shape[2]) - self.shape[3]
        return seg_dist(p, self.shape[1], self.shape[2]) - self.shape[3]

    def dist_seg(self, a, b):
        k = self.shape[0]
        if k == 'rect':
            return seg_rect_dist(a, b, self.shape[1:])
        if k == 'circle':
            return seg_dist((self.shape[1], self.shape[2]), a, b) - self.shape[3]
        return seg_seg_dist(a, b, self.shape[1], self.shape[2]) - self.shape[3]


def pad_obstacle(pad):
    layers = set()
    if pad.IsOnLayer(F):
        layers.add(F)
    if pad.IsOnLayer(B):
        layers.add(B)
    pos = pad.GetPosition()
    hole = None
    if pad.GetDrillSize().x > 0:
        hole = (mm(pos.x), mm(pos.y), mm(pad.GetDrillSize().x) / 2)
    if pad.GetShape(F if F in layers else B) == pcbnew.PAD_SHAPE_CIRCLE:
        shape = ('circle', mm(pos.x), mm(pos.y), mm(pad.GetSize(F if F in layers else B).x) / 2)
    else:
        bb = pad.GetBoundingBox()
        shape = ('rect', mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom()))
    return Obstacle(pad.GetNetname(), layers, shape, hole)


def track_obstacles(board):
    out = []
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            out.append(Obstacle(t.GetNetname(), {F, B}, ('circle', mm(p.x), mm(p.y), mm(t.GetWidth(F)) / 2),
                                (mm(p.x), mm(p.y), mm(t.GetDrillValue()) / 2)))
        else:
            s, e = t.GetStart(), t.GetEnd()
            out.append(Obstacle(t.GetNetname(), {t.GetLayer()},
                                ('seg', (mm(s.x), mm(s.y)), (mm(e.x), mm(e.y)), mm(t.GetWidth()) / 2)))
    return out


def board_obstacles(board, zone_rects):
    """Pads, tracks, vias, and the given zone rect lists {(net, layer): [rects]}."""
    obs = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                pos = pad.GetPosition()
                obs.append(Obstacle('', {F, B}, ('circle', mm(pos.x), mm(pos.y), mm(pad.GetDrillSize().x) / 2),
                                    (mm(pos.x), mm(pos.y), mm(pad.GetDrillSize().x) / 2)))
                continue
            if not (pad.IsOnLayer(F) or pad.IsOnLayer(B)):
                continue
            obs.append(pad_obstacle(pad))
    obs += track_obstacles(board)
    for (netname, layer), rects in zone_rects.items():
        for r in rects:
            obs.append(Obstacle(netname, {layer}, ('rect',) + tuple(r)))
    return obs


def edge_segments(board, step=0.25):
    """Board outline as short segments (mm), arcs sampled."""
    segs = []
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts or d.GetClass() != 'PCB_SHAPE':
            continue
        if d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            segs.append(((mm(d.GetStart().x), mm(d.GetStart().y)), (mm(d.GetEnd().x), mm(d.GetEnd().y))))
        elif d.GetShape() == pcbnew.SHAPE_T_ARC:
            c = d.GetCenter()
            cx, cy, r = mm(c.x), mm(c.y), mm(d.GetRadius())
            a0 = math.atan2(mm(d.GetStart().y) - cy, mm(d.GetStart().x) - cx)
            a1 = math.atan2(mm(d.GetEnd().y) - cy, mm(d.GetEnd().x) - cx)
            sweep = math.radians(d.GetArcAngle().AsDegrees())
            n = max(4, int(abs(sweep) * r / step))
            pts = [(cx + r * math.cos(a0 + sweep * k / n), cy + r * math.sin(a0 + sweep * k / n)) for k in range(n + 1)]
            segs += list(zip(pts[:-1], pts[1:]))
            _ = a1
        else:
            raise SystemExit(f'unexpected Edge.Cuts shape {d.GetShapeStr()}')
    return segs


def inside_board(board, p):
    poly = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(poly)
    return poly.Contains(P(*p))
