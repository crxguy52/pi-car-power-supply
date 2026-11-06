"""KiCad 10 symbol-library helpers for the schematic edit scripts (tools/post_sch/) and checks.

- load a symbol from the KiCad standard library, flattened (an `extends` child gets its parent's units), renamed
  to its `Lib:Name` lib_id: the form a schematic's lib_symbols cache holds;
- pin geometry: connection point and outward direction of every pin of a placed symbol (sheet coordinates, mm,
  Y down), and the body bounding box (graphics only, no pins).

Library coordinates have Y up; the sheet has Y down. A symbol at (X, Y) rotated by `rot` degrees (CCW on screen)
maps a library point (px, py) to (X + px*cos - py*sin, Y - (px*sin + py*cos)). Mirrored symbols are not handled:
the edit scripts place none.
"""
import copy
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sexpr  # noqa: E402
import toolchain  # noqa: E402

SYMBOL_DIR = toolchain.Toolchain().kicad_cli.parent.parent / 'share' / 'kicad' / 'symbols'
ROUND_MM = 4                                   # KiCad writes 4 decimals
_LIB_CACHE = {}


def _lib(name):
    if name not in _LIB_CACHE:
        path = SYMBOL_DIR / f'{name}.kicad_sym'
        _LIB_CACHE[name] = sexpr.parse(path.read_text(encoding='utf-8'))
    return _LIB_CACHE[name]


def _raw(lib, name):
    for node in sexpr.find_all(_lib(lib), 'symbol'):
        if node[1] == name:
            return node
    raise SystemExit(f'{SYMBOL_DIR / lib}.kicad_sym: no symbol {name}')


def flat_symbol(lib_id):
    """The library symbol `Lib:Name` as a lib_symbols cache entry (flattened, renamed), as a parsed node."""
    lib, name = lib_id.split(':')
    child = _raw(lib, name)
    ext = sexpr.find(child, 'extends')
    if ext is None:
        node = copy.deepcopy(child)
    else:
        parent = _raw(lib, ext[1])
        if sexpr.find(parent, 'extends') is not None:
            raise SystemExit(f'{lib_id}: two-level extends not handled')
        node = copy.deepcopy(parent)
        own = {p[1]: copy.deepcopy(p) for p in sexpr.find_all(child, 'property')}
        props = [own.pop(p[1], p) for p in sexpr.find_all(node, 'property')] + list(own.values())  # KiCad: parent
        node = [x for x in node if not (isinstance(x, list) and x and x[0] == 'property')]           # fields kept
        first_sub = next(i for i, x in enumerate(node) if isinstance(x, list) and x and x[0] in ('symbol',
                                                                                                 'embedded_fonts'))
        node[first_sub:first_sub] = props
        for sub in sexpr.find_all(node, 'symbol'):
            sub[1] = re.sub(r'^' + re.escape(ext[1]) + r'_', name + '_', sub[1])
    node[1] = lib_id
    return node


def unit_of(sub_name):
    """Unit number of a library sub-symbol name `Name_U_S` (0 = common to all units)."""
    return int(sub_name.rsplit('_', 2)[1])


def lib_pins(node, unit):
    """{number: (px, py, angle_deg, length, name, type)} for one unit (plus the common unit 0), library coords."""
    out = {}
    for sub in sexpr.find_all(node, 'symbol'):
        if unit_of(sub[1]) not in (0, unit):
            continue
        for p in sexpr.find_all(sub, 'pin'):
            at = sexpr.find(p, 'at')
            out[sexpr.find(p, 'number')[1]] = (float(at[1]), float(at[2]), float(at[3]),
                                               float(sexpr.find(p, 'length')[1]), sexpr.find(p, 'name')[1], p[1])
    return out


def _graphic_points(item):
    kind = item[0]
    if kind == 'rectangle':
        return [tuple(map(float, sexpr.find(item, k)[1:3])) for k in ('start', 'end')]
    if kind in ('polyline', 'bezier'):
        return [(float(xy[1]), float(xy[2])) for xy in sexpr.find_all(sexpr.find(item, 'pts'), 'xy')]
    if kind == 'circle':
        cx, cy = map(float, sexpr.find(item, 'center')[1:3])
        r = float(sexpr.find(item, 'radius')[1])
        return [(cx - r, cy - r), (cx + r, cy + r)]
    if kind == 'arc':
        return [tuple(map(float, sexpr.find(item, k)[1:3])) for k in ('start', 'mid', 'end')]
    return []


def lib_body_box(node, unit):
    """(xmin, ymin, xmax, ymax) of the body graphics of a unit (library coords, Y up), or None."""
    pts = []
    for sub in sexpr.find_all(node, 'symbol'):
        if unit_of(sub[1]) not in (0, unit):
            continue
        for item in sub:
            if isinstance(item, list) and item:
                pts += _graphic_points(item)
    if not pts:
        return None
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def to_sheet(x0, y0, rot, px, py):
    """Library point -> sheet point (mm, Y down) for a symbol at (x0, y0) rotated rot degrees."""
    c, s = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
    return round(x0 + px * c - py * s, ROUND_MM), round(y0 - (px * s + py * c), ROUND_MM)


def outward(rot, pin_angle):
    """Unit vector (sheet coords) pointing away from the body at a pin end."""
    a = math.radians(pin_angle + 180 + rot)
    return round(math.cos(a)), -round(math.sin(a))


def sheet_box(x0, y0, rot, box):
    (ax, ay), (bx, by) = to_sheet(x0, y0, rot, box[0], box[1]), to_sheet(x0, y0, rot, box[2], box[3])
    return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)
