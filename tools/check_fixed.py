"""Fixed-item guard for pi_power_board.kicad_pcb (project lead's hard constraints, overnight run 2026-11-04).

The project lead fixed these items; no scripted or agent edit may change them:

- the board outline (every Edge.Cuts item drawn on the board);
- mounting holes MH1-MH4 (footprint, position, orientation, side, pads);
- the parts that leave the board: J1, J4, J5 (screw terminals) and J2 (USB): position, orientation, side and the
  absolute coordinates of every pad. J1/J4/J5 may change footprint (Metz RT034xx -> Phoenix MKDS 1/x-3,81, SPEC 7)
  as long as every pad number stays at the same absolute coordinates; J2 may rename its shield pads 19 -> SH
  (KiCad 10 library, SPEC 7);
- every board-level drawing and text (keep-outs, reference outlines, dimensions: GPIO HEADER, WAVESHARE IO, PoE,
  BACK HEADER KEEPOUT, RJ45/USB) and every rule area (the PoE footprint keep-out).

Items added later (new silk text, new zones) are allowed: the check only proves the baseline items are unchanged.

Usage (KiCad python, under timeout):
    python.exe -I tools/check_fixed.py [board]          verify the board (default: the master) against the baseline
    python.exe -I tools/check_fixed.py --make-baseline  write tools/fixed_baseline.json once; refuses if it exists
    python.exe -I tools/check_fixed.py --selftest       mutate each baseline item in memory and prove the check fails
    python.exe -I tools/check_fixed.py --accept-lead-change J1,J4,J5 | J2,J5 | EDGE_RIGHT_NOTCH
                                                        | EDGE_RIGHT_NOTCH_UNDER_USB
                                                        record a lead decision in the baseline (guarded; see below)

Recorded lead changes (`--accept-lead-change`, the only way the baseline changes after it was generated):
- 2026-11-05, J1,J4,J5: rotated 180 deg about the centre of each pad row (lead decision, SPEC 5 "Fixed
  positions", tools/post_route/05_sync_cd4541.py), so the wire entries face outward. Only those three entries
  change: orientation +180, and the pad -> pin map (pin k now sits at the lead's location of pin n+1-k); the
  set of pad locations is the lead's. The footprint origin is pad 1, so `pos` moves to the lead's last-pad
  location. The guard refuses unless every other baseline item still passes and these exact relations hold.
  The JSON keeps the record in `lead_changes`.
- 2026-11-05, J2,J5: moved in the lead's layout copy (`C:\git-personal\pi-car-power-supply - Copy`, snapshot
  tools/post_route/lead_layout_2026-11-05.json, applied by tools/post_route/08_lead_layout.py). A pure
  translation by the recorded vectors LEAD_SHIFTS_NM (J2 -0.635 mm in x; J5 -2.54 mm in x and +0.038 mm in y):
  same footprint, orientation and side; every pad moves by the same vector. Same guard: every other baseline
  item must still pass.
- 2026-11-05, EDGE_RIGHT_NOTCH: the project lead's right-edge notch (approved geometry; applied by
  tools/post_route/13_right_notch.py): the right edge line RIGHT_NOTCH_OLD is replaced by the path
  RIGHT_NOTCH_PATH, which cuts out the BACK HEADER KEEPOUT strip between the MH2 / MH4 corner tabs. Only that
  Edge.Cuts entry changes: the guard refuses unless the old line is gone, every new item is on the board exactly
  (TOL_NM; line / arc direction free), no other Edge.Cuts item was added, and every other baseline item passes.
- 2026-11-05, EDGE_RIGHT_NOTCH_UNDER_USB: the project lead keeps the board under the USB port J2 (applied by
  tools/post_route/14_notch_under_usb.py): the notch's top edge moves down from CUT_TOP_Y to CUT_TOP_Y_USB, just
  below J2's courtyard. The top five items of RIGHT_NOTCH_PATH (right edge line, mouth arc, top edge, inner
  fillet, inner vertical line) are replaced by RIGHT_NOTCH_USB_TOP; the bottom edge and its arcs stay. Same guard
  as EDGE_RIGHT_NOTCH (old items gone, new ones on the board exactly, nothing else changed).

Exit code 0 = PASS. Tolerance: TOL_NM on every coordinate, TOL_DEG on every angle.
"""
import json
import pathlib
import sys

import pcbnew

ROOT = pathlib.Path(__file__).resolve().parent.parent
PCB = ROOT / 'pi_power_board.kicad_pcb'
BASELINE = pathlib.Path(__file__).resolve().parent / 'fixed_baseline.json'
TOL_NM = 1000                       # 1 um
TOL_DEG = 1e-3
FIXED_REFS = ('MH1', 'MH2', 'MH3', 'MH4', 'J1', 'J2', 'J4', 'J5')
FPID_MAY_CHANGE = {'J1', 'J4', 'J5'}            # Metz -> Phoenix (SPEC 7), pads must stay put
PAD_RENAMES = {'J2': {'19': 'SH'}}               # KiCad 10 USB3_A footprint shield pad name (SPEC 7)
MUTATE_NM = 50_000                               # selftest displacement, far above TOL_NM
LEAD_CHANGES = {                                 # accepted lead decisions: refs -> (date, record text)
    'J1,J4,J5': ('2026-11-05', 'J1, J4, J5 rotated 180 deg about the centre of each pad row (lead decision, '
                 'SPEC 5 "Fixed positions"; tools/post_route/05_sync_cd4541.py): wire entries face outward; '
                 'pad-location set unchanged, pin order reversed, origin (pad 1) at the old last-pad location'),
    'J2,J5': ('2026-11-05', 'J2 and J5 moved by the project lead in the layout copy (tools/post_route/'
              'lead_layout_2026-11-05.json, applied by tools/post_route/08_lead_layout.py): pure translations, '
              'J2 -0.635 mm x, J5 -2.54 mm x / +0.038 mm y; orientation, side and footprint unchanged'),
    'EDGE_RIGHT_NOTCH': ('2026-11-05', 'right edge notch (project lead, approved geometry; tools/post_route/'
                         '13_right_notch.py): the right edge line x 192.024 is replaced by a cut-out of the BACK '
                         'HEADER KEEPOUT strip, x 185.166-192.024, y 70.450-102.000, inner corners r 1.524, outer '
                         'r 0.762; top cut edge 10 um below the approved 70.440 so the MH2 neck is >= 5 mm'),
    'EDGE_RIGHT_NOTCH_UNDER_USB': ('2026-11-05', 'right edge notch top edge moved down to y 85.000, just below the '
                                   'J2 (USB) courtyard (project lead: "Keep board under the USB port (J2) ... I\'m '
                                   'not using the header it covers"; tools/post_route/14_notch_under_usb.py): notch '
                                   'now x 185.166-192.024, y 85.000-102.000, same corner radii; the five top items '
                                   'of the EDGE_RIGHT_NOTCH path replaced, bottom edge unchanged'),
}
LEAD_CHANGE_KIND = {'J1,J4,J5': 'half_turn', 'J2,J5': 'translate', 'EDGE_RIGHT_NOTCH': 'edge',
                    'EDGE_RIGHT_NOTCH_UNDER_USB': 'edge'}
LEAD_SHIFTS_NM = {'J2': (-635_000, 0), 'J5': (-2_540_000, 38_000)}   # exact values of the lead's copy
HALF_TURN_DEG = 180.0

# EDGE_RIGHT_NOTCH (mm, KiCad frame): the line it replaces, and the new path ('line', a, b) / ('arc', a, b, centre)
EDGE_LAYER = 'Edge.Cuts'
EDGE_WIDTH_NM = 50_800                           # the lead's Edge.Cuts line width
RIGHT_X, NOTCH_X = 192.024, 185.166              # board right edge; strip inner edge (the lead's keep-out line)
TOP_TAB_Y, BOT_TAB_Y = 61.468, 111.252           # ends of the old right edge line (corner arcs)
CUT_TOP_Y, CUT_BOT_Y = 70.450, 102.000           # cut edges (top: approved 70.440, moved for the 5 mm neck)
OUTER_R, INNER_R = 0.762, 1.524                  # convex corner radius (as the notch tabs); inner fillet radius
RIGHT_NOTCH_OLD = ('line', (RIGHT_X, BOT_TAB_Y), (RIGHT_X, TOP_TAB_Y))
RIGHT_NOTCH_PATH = (
    ('line', (RIGHT_X, TOP_TAB_Y), (RIGHT_X, CUT_TOP_Y - OUTER_R)),
    ('arc', (RIGHT_X, CUT_TOP_Y - OUTER_R), (RIGHT_X - OUTER_R, CUT_TOP_Y), (RIGHT_X - OUTER_R, CUT_TOP_Y - OUTER_R)),
    ('line', (RIGHT_X - OUTER_R, CUT_TOP_Y), (NOTCH_X + INNER_R, CUT_TOP_Y)),
    ('arc', (NOTCH_X + INNER_R, CUT_TOP_Y), (NOTCH_X, CUT_TOP_Y + INNER_R), (NOTCH_X + INNER_R, CUT_TOP_Y + INNER_R)),
    ('line', (NOTCH_X, CUT_TOP_Y + INNER_R), (NOTCH_X, CUT_BOT_Y - INNER_R)),
    ('arc', (NOTCH_X, CUT_BOT_Y - INNER_R), (NOTCH_X + INNER_R, CUT_BOT_Y), (NOTCH_X + INNER_R, CUT_BOT_Y - INNER_R)),
    ('line', (NOTCH_X + INNER_R, CUT_BOT_Y), (RIGHT_X - OUTER_R, CUT_BOT_Y)),
    ('arc', (RIGHT_X - OUTER_R, CUT_BOT_Y), (RIGHT_X, CUT_BOT_Y + OUTER_R), (RIGHT_X - OUTER_R, CUT_BOT_Y + OUTER_R)),
    ('line', (RIGHT_X, CUT_BOT_Y + OUTER_R), (RIGHT_X, BOT_TAB_Y)),
)
# EDGE_RIGHT_NOTCH_UNDER_USB: the top of the notch moves below J2's courtyard; RIGHT_NOTCH_PATH[USB_TOP_ITEMS:] stays
CUT_TOP_Y_USB = 85.000
USB_TOP_ITEMS = 5
RIGHT_NOTCH_USB_OLD = RIGHT_NOTCH_PATH[:USB_TOP_ITEMS]
RIGHT_NOTCH_USB_TOP = (
    ('line', (RIGHT_X, TOP_TAB_Y), (RIGHT_X, CUT_TOP_Y_USB - OUTER_R)),
    ('arc', (RIGHT_X, CUT_TOP_Y_USB - OUTER_R), (RIGHT_X - OUTER_R, CUT_TOP_Y_USB),
     (RIGHT_X - OUTER_R, CUT_TOP_Y_USB - OUTER_R)),
    ('line', (RIGHT_X - OUTER_R, CUT_TOP_Y_USB), (NOTCH_X + INNER_R, CUT_TOP_Y_USB)),
    ('arc', (NOTCH_X + INNER_R, CUT_TOP_Y_USB), (NOTCH_X, CUT_TOP_Y_USB + INNER_R),
     (NOTCH_X + INNER_R, CUT_TOP_Y_USB + INNER_R)),
    ('line', (NOTCH_X, CUT_TOP_Y_USB + INNER_R), (NOTCH_X, CUT_BOT_Y - INNER_R)),
)
RIGHT_NOTCH_USB_PATH = RIGHT_NOTCH_USB_TOP + RIGHT_NOTCH_PATH[USB_TOP_ITEMS:]
EDGE_CHANGES = {                                 # edge lead change -> (recorded items removed, recorded items added)
    'EDGE_RIGHT_NOTCH': ((RIGHT_NOTCH_OLD,), RIGHT_NOTCH_PATH),
    'EDGE_RIGHT_NOTCH_UNDER_USB': (RIGHT_NOTCH_USB_OLD, RIGHT_NOTCH_USB_TOP),
}


def _nm(v):
    return int(round(v * 1e6))


def arc_mid_mm(a, b, c):
    """Mid point of the arc a -> b about centre c (the shorter way: every arc here is a quarter circle)."""
    ux, uy = a[0] - c[0] + b[0] - c[0], a[1] - c[1] + b[1] - c[1]
    r = ((a[0] - c[0]) ** 2 + (a[1] - c[1]) ** 2) ** 0.5
    n = (ux * ux + uy * uy) ** 0.5
    return c[0] + r * ux / n, c[1] + r * uy / n


def edge_item_key(item):
    """shape_key of one recorded path item."""
    k = {'class': 'PCB_SHAPE', 'layer': EDGE_LAYER, 'shape': 'Line' if item[0] == 'line' else 'Arc',
         'width': EDGE_WIDTH_NM, 'start': [_nm(item[1][0]), _nm(item[1][1])]}
    if item[0] == 'arc':
        m = arc_mid_mm(*item[1:])
        k['mid'] = [_nm(m[0]), _nm(m[1])]
    k['end'] = [_nm(item[2][0]), _nm(item[2][1])]
    return k


def _undirected(k):
    """Shape key with start / end in a fixed order (KiCad may store a line or arc either way)."""
    if 'start' not in k or 'end' not in k:
        return k
    a, b = sorted([k['start'], k['end']])
    return dict(k, start=a, end=b)


def _pt(v):
    return [int(v.x), int(v.y)]


def shape_key(d):
    """Geometry of one board-level shape as JSON-able data."""
    k = {'class': d.GetClass(), 'layer': d.GetLayerName(), 'shape': d.GetShapeStr(), 'width': int(d.GetWidth())}
    st = d.GetShape()
    if st == pcbnew.SHAPE_T_ARC:
        k.update(start=_pt(d.GetStart()), mid=_pt(d.GetArcMid()), end=_pt(d.GetEnd()))
    elif st == pcbnew.SHAPE_T_CIRCLE:
        k.update(center=_pt(d.GetCenter()), end=_pt(d.GetEnd()))
    elif st == pcbnew.SHAPE_T_POLY:
        poly = d.GetPolyShape()
        k.update(points=[_pt(poly.CVertex(i)) for i in range(poly.TotalVertices())])
    else:
        k.update(start=_pt(d.GetStart()), end=_pt(d.GetEnd()))
    return k


def text_key(d):
    return {'class': d.GetClass(), 'layer': d.GetLayerName(), 'text': d.GetText(), 'pos': _pt(d.GetPosition()),
            'angle': d.GetTextAngleDegrees(), 'size': _pt(d.GetTextSize())}


def dim_key(d):
    return {'class': d.GetClass(), 'layer': d.GetLayerName(), 'text': d.GetText(), 'start': _pt(d.GetStart()),
            'end': _pt(d.GetEnd())}


def drawing_key(d):
    c = d.GetClass()
    if c.startswith('PCB_DIM'):
        return dim_key(d)
    if c in ('PCB_TEXT', 'PCB_TEXTBOX'):
        return text_key(d)
    return shape_key(d)


def zone_key(z):
    o = z.Outline()
    return {'name': z.GetZoneName(), 'layers': [z.GetBoard().GetLayerName(l) for l in z.GetLayerSet().Seq()],
            'points': [_pt(o.CVertex(i)) for i in range(o.TotalVertices())],
            'no_footprints': z.GetDoNotAllowFootprints(), 'no_tracks': z.GetDoNotAllowTracks(),
            'no_vias': z.GetDoNotAllowVias(), 'no_pads': z.GetDoNotAllowPads(),
            'no_zones': z.GetDoNotAllowZoneFills()}


def footprint_key(f):
    return {'fpid': f.GetFPIDAsString(), 'pos': _pt(f.GetPosition()), 'angle': f.GetOrientationDegrees(),
            'flipped': f.IsFlipped(),
            'pads': sorted([p.GetNumber(), *_pt(p.GetPosition())] for p in f.Pads())}


def snapshot(board):
    """Everything the lead fixed, from a loaded board."""
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    missing = [r for r in FIXED_REFS if r not in fps]
    if missing:
        raise SystemExit(f'fixed footprints missing from the board: {missing}')
    drawings = [drawing_key(d) for d in board.GetDrawings()]
    return {'edge_cuts': [k for k in drawings if k['layer'] == 'Edge.Cuts'],
            'drawings': [k for k in drawings if k['layer'] != 'Edge.Cuts'],
            'rule_areas': [zone_key(z) for z in board.Zones() if z.GetIsRuleArea()],
            'footprints': {r: footprint_key(fps[r]) for r in FIXED_REFS}}


def _close(a, b):
    """Recursive equality with TOL_NM on ints and TOL_DEG on floats."""
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(a, str) or a is None:
        return a == b
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(b, (int, float)) and abs(a - b) <= TOL_DEG
    return isinstance(b, int) and abs(a - b) <= TOL_NM


def _unmatched(base_items, cur_items):
    """Baseline items with no equal item on the board (each board item matches at most one baseline item)."""
    pool = list(cur_items)
    out = []
    for k in base_items:
        for i, c in enumerate(pool):
            if _close(k, c):
                del pool[i]
                break
        else:
            out.append(k)
    return out


def _angle_eq(a, b):
    d = (a - b) % 360.0
    return min(d, 360.0 - d) <= TOL_DEG


def compare(base, cur):
    """List of failures (empty = PASS)."""
    errs = []
    for group in ('edge_cuts', 'drawings', 'rule_areas'):
        for k in _unmatched(base[group], cur[group]):
            errs.append(f'{group}: changed or missing: {json.dumps(k)[:160]}')
    for ref in FIXED_REFS:
        b, c = base['footprints'][ref], cur['footprints'][ref]
        if b['fpid'] != c['fpid'] and ref not in FPID_MAY_CHANGE:
            errs.append(f'{ref}: footprint {c["fpid"]} != {b["fpid"]}')
        if not _close(b['pos'], c['pos']):
            errs.append(f'{ref}: position {c["pos"]} != {b["pos"]}')
        if not _angle_eq(b['angle'], c['angle']):
            errs.append(f'{ref}: orientation {c["angle"]} != {b["angle"]}')
        if b['flipped'] != c['flipped']:
            errs.append(f'{ref}: side changed')
        renames = PAD_RENAMES.get(ref, {})
        got = c['pads']
        ok = False
        for names in ({}, renames):             # the baseline pad names, or the allowed renames
            want = sorted([names.get(p[0], p[0]), p[1], p[2]] for p in b['pads'])
            ok |= [p[0] for p in want] == [p[0] for p in got] and _close([p[1:] for p in want],
                                                                          [p[1:] for p in got])
        if not ok:
            errs.append(f'{ref}: pads differ (number or absolute position beyond {TOL_NM} nm)')
    return errs


def load_baseline():
    if not BASELINE.exists():
        raise SystemExit(f'{BASELINE} missing: run --make-baseline once on the lead\'s board')
    return json.loads(BASELINE.read_text(encoding='utf-8'))


def make_baseline():
    if BASELINE.exists():
        raise SystemExit(f'{BASELINE} exists: the baseline is generated once and never overwritten')
    snap = snapshot(pcbnew.LoadBoard(str(PCB)))
    BASELINE.write_text(json.dumps(snap, indent=1) + '\n', encoding='utf-8')
    print(f'baseline written: {BASELINE} ({len(snap["edge_cuts"])} Edge.Cuts, {len(snap["drawings"])} drawings, '
          f'{len(snap["rule_areas"])} rule areas, {len(snap["footprints"])} footprints)')


def _rotated_ok(b, c):
    """True if footprint entry c is entry b turned 180 deg about its pad-row centre (same pad-location set,
    pin k at the old location of pin n+1-k, orientation +180, same side)."""
    if b['flipped'] != c['flipped'] or not _angle_eq(b['angle'] + HALF_TURN_DEG, c['angle']):
        return False
    old = {p[0]: p[1:] for p in b['pads']}
    new = {p[0]: p[1:] for p in c['pads']}
    n = len(old)
    if set(old) != set(new) or set(old) != {str(k) for k in range(1, n + 1)}:
        return False
    if not all(_close(old[str(n + 1 - k)], new[str(k)]) for k in range(1, n + 1)):
        return False
    return _close(c['pos'], new['1'])               # the footprint origin is pad 1


def _translated_ok(ref, b, c):
    """True if footprint entry c is entry b moved by LEAD_SHIFTS_NM[ref] (same orientation, side, pad names; every
    pad and the origin moved by that vector)."""
    dx, dy = LEAD_SHIFTS_NM[ref]
    if b['flipped'] != c['flipped'] or not _angle_eq(b['angle'], c['angle']):
        return False
    if not _close([b['pos'][0] + dx, b['pos'][1] + dy], c['pos']):
        return False
    for names in ({}, PAD_RENAMES.get(ref, {})):     # the baseline pad names, or the allowed renames
        want = sorted([names.get(p[0], p[0]), p[1] + dx, p[2] + dy] for p in b['pads'])
        if [p[0] for p in want] == [p[0] for p in c['pads']] and _close([p[1:] for p in want],
                                                                        [p[1:] for p in c['pads']]):
            return True
    return False


def _pop_match(items, key):
    """Remove and return the one item of `items` equal to `key` with start / end in either order, else None."""
    hits = [i for i, k in enumerate(items) if _close(_undirected(key), _undirected(k))]
    if len(hits) != 1:
        return None
    return items.pop(hits[0])


def _accept_edge_change(name, base, cur):
    """Edge lead change (EDGE_CHANGES): the recorded old items are gone, the recorded new items are on the board
    exactly, nothing else changed. Writes the baseline with the old items replaced by the board's new items."""
    old_items, add_items = EDGE_CHANGES[name]
    base_edges = list(base['edge_cuts'])
    removed = []
    for item in old_items:
        old = _pop_match(base_edges, edge_item_key(item))
        if old is None:
            raise SystemExit(f'{name}: old edge item {item} is not in the baseline exactly once: refusing')
        removed.append(old)
    cur_edges = list(cur['edge_cuts'])
    for old in removed:
        if _pop_match(list(cur_edges), old) is not None:
            raise SystemExit(f'{name}: old edge item {old} is still on the board: refusing')
    new_items = []
    for item in add_items:
        got = _pop_match(cur_edges, edge_item_key(item))
        if got is None:
            raise SystemExit(f'{name}: recorded item {item} not on the board exactly once: refusing')
        new_items.append(got)
    if len(cur_edges) != len(base_edges):
        raise SystemExit(f'{name}: {len(cur_edges) - len(base_edges)} Edge.Cuts items besides the recorded change: '
                         'refusing')
    errs = compare(dict(base, edge_cuts=base_edges), dict(cur, edge_cuts=cur_edges))
    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit('other baseline items differ: refusing the lead change')
    date, text = LEAD_CHANGES[name]
    new = json.loads(json.dumps(base))
    new['edge_cuts'] = base_edges + new_items
    new.setdefault('lead_changes', []).append({'date': date, 'refs': name, 'record': text,
                                               'before': {'edge_cuts_removed': removed},
                                               'after': {'edge_cuts_added': new_items}})
    if compare(new, cur):
        raise SystemExit('internal: the new baseline does not pass on the board: nothing written')
    BASELINE.write_text(json.dumps(new, indent=1) + '\n', encoding='utf-8')
    print(f'baseline updated for the lead change {name} ({date}): {BASELINE}')
    return 0


def accept_lead_change(refs_arg):
    """Write the baseline for one recorded lead change: only the named footprint entries change."""
    if refs_arg not in LEAD_CHANGES:
        raise SystemExit(f'--accept-lead-change {refs_arg}: not a recorded lead change ({sorted(LEAD_CHANGES)})')
    refs = refs_arg.split(',')
    date, text = LEAD_CHANGES[refs_arg]
    base = load_baseline()
    if any(h.get('refs') == refs_arg for h in base.get('lead_changes', [])):
        print(f'already applied: {refs_arg} recorded in the baseline ({date}); nothing written')
        return 0 if not compare(base, snapshot(pcbnew.LoadBoard(str(PCB)))) else 1
    cur = snapshot(pcbnew.LoadBoard(str(PCB)))
    if LEAD_CHANGE_KIND[refs_arg] == 'edge':
        return _accept_edge_change(refs_arg, base, cur)
    # every other baseline item must still pass: compare with the changed refs taken from the baseline
    masked = dict(cur, footprints=dict(cur['footprints'], **{r: base['footprints'][r] for r in refs}))
    errs = compare(base, masked)
    if errs:
        for e in errs:
            print('FAIL', e)
        raise SystemExit('other baseline items differ: refusing the lead change')
    if LEAD_CHANGE_KIND[refs_arg] == 'half_turn':
        bad = [r for r in refs if not _rotated_ok(base['footprints'][r], cur['footprints'][r])]
    else:
        bad = [r for r in refs if not _translated_ok(r, base['footprints'][r], cur['footprints'][r])]
    if bad:
        raise SystemExit(f'{bad}: not the recorded {LEAD_CHANGE_KIND[refs_arg]} lead change: refusing')
    new = json.loads(json.dumps(base))
    for r in refs:
        new['footprints'][r] = dict(base['footprints'][r], pos=cur['footprints'][r]['pos'],
                                    angle=cur['footprints'][r]['angle'], pads=cur['footprints'][r]['pads'])
    new.setdefault('lead_changes', []).append({'date': date, 'refs': refs_arg, 'record': text,
                                               'before': {r: {k: base['footprints'][r][k]
                                                              for k in ('pos', 'angle', 'pads')} for r in refs}})
    if compare(new, cur):
        raise SystemExit('internal: the new baseline does not pass on the board: nothing written')
    BASELINE.write_text(json.dumps(new, indent=1) + '\n', encoding='utf-8')
    print(f'baseline updated for the lead change {refs_arg} ({date}): {BASELINE}')
    return 0


def verify(path):
    errs = compare(load_baseline(), snapshot(pcbnew.LoadBoard(str(path))))
    for e in errs:
        print('FAIL', e)
    print(f'check_fixed: {"PASS" if not errs else f"FAIL ({len(errs)})"} {path.name}')
    return 0 if not errs else 1


def _move(item):
    item.Move(pcbnew.VECTOR2I(MUTATE_NM, 0))


def _mutations(board):
    """(name, mutate) pairs: each one changes exactly one baseline item."""
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    edge = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    base = load_baseline()['drawings']        # mutate only baseline items (later additions are allowed)
    other = [d for d in board.GetDrawings() if d.GetLayer() != pcbnew.Edge_Cuts
             and any(_close(k, drawing_key(d)) for k in base)]
    texts = [d for d in other if d.GetClass() == 'PCB_TEXT']
    base_areas = load_baseline()['rule_areas']    # the lead's rule areas only (a later keep-out is allowed)
    areas = [z for z in board.Zones() if z.GetIsRuleArea() and any(_close(k, zone_key(z)) for k in base_areas)]
    out = [('edge segment moved', lambda: _move(edge[0])),
           ('edge item moved off Edge.Cuts', lambda: edge[-1].SetLayer(pcbnew.Cmts_User)),
           ('drawing moved', lambda: _move(other[0])),
           ('drawing moved to another layer', lambda: other[-1].SetLayer(pcbnew.Cmts_User)),
           ('text edited', lambda: texts[0].SetText(texts[0].GetText() + 'X')),
           ('rule area moved', lambda: areas[0].Move(pcbnew.VECTOR2I(MUTATE_NM, 0))),
           ('rule area flag', lambda: areas[0].SetDoNotAllowFootprints(not areas[0].GetDoNotAllowFootprints()))]
    for ref in FIXED_REFS:
        f = fps[ref]
        out.append((f'{ref} moved', lambda f=f: _move(f)))
        out.append((f'{ref} rotated', lambda f=f: f.SetOrientationDegrees(f.GetOrientationDegrees() + 90.0)))
        out.append((f'{ref} flipped', lambda f=f: f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)))
        pad = sorted(f.Pads(), key=lambda p: p.GetNumber())[0]
        out.append((f'{ref} pad moved', lambda p=pad: p.SetPosition(p.GetPosition() + pcbnew.VECTOR2I(0, MUTATE_NM))))
        out.append((f'{ref} pad renumbered', lambda p=pad: p.SetNumber(p.GetNumber() + 'Z')))
    out.append(('MH1 footprint swapped', lambda: fps['MH1'].SetFPID(pcbnew.LIB_ID('MountingHole', 'Other'))))
    return out


def selftest(path):
    base = load_baseline()
    board = pcbnew.LoadBoard(str(path))
    errs = compare(base, snapshot(board))
    if errs:
        print(f'selftest: the unmutated board already fails ({len(errs)}): fix that first')
        return 1
    names = [n for n, _ in _mutations(board)]
    bad = []
    for i, name in enumerate(names):
        b = pcbnew.LoadBoard(str(path))         # fresh copy per mutation, never saved
        _mutations(b)[i][1]()
        if not compare(base, snapshot(b)):
            bad.append(name)
    print(f'selftest: {len(names) - len(bad)}/{len(names)} mutations caught' + (f'; MISSED: {bad}' if bad else ''))
    return 0 if not bad else 1


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('--') and a not in LEAD_CHANGES]
    path = pathlib.Path(args[0]).resolve() if args else PCB
    if '--make-baseline' in argv:
        make_baseline()
        return 0
    if '--selftest' in argv:
        return selftest(path)
    if '--accept-lead-change' in argv:
        i = argv.index('--accept-lead-change')
        if i + 1 >= len(argv):
            raise SystemExit('--accept-lead-change needs the refs, e.g. J1,J4,J5')
        return accept_lead_change(argv[i + 1])
    return verify(path)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
