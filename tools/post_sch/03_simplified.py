"""Post-schematic edit 03 (2026-11-05, overnight): redraw pi_power_board.kicad_sch for the simplified SPEC 7.

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/03_simplified.py [--dry-run]

What and why (SPEC header note "simplified redesign", SPEC 2-4 intent, SPEC 6 Parts, SPEC 7 contract; DECISIONS
2026-11-04 "simplified redesign"): the project lead rejected the 64-part 555 / N-FET design as over-complicated. One
LM2903B dual comparator (U1, on BATT) now does the delay (U1A) and the ACC status (U1B); 32 parts plus J1, J2, J4,
J5 and SW1.
- the 33 parts SPEC 7 lists as removed go, with every wire, junction, label, no-connect, power symbol and text
  note of the old sheet: the topology changed in every block, so the sheet is redrawn from scratch;
- the 34 surviving parts keep their symbol uuid and pin uuids (the board links its footprints by symbol uuid;
  J1, J2, J4 and J5 are fixed on the board); their value, footprint and fields follow SPEC 7 / SPEC 6;
- new: U1 (`Comparator:LM2903`, units A, B and the power unit C), R23, R24 (KiCad 10 library symbols, flattened
  into lib_symbols; lib_symbols holds only the symbols this sheet uses);
- fields: Value and Footprint from SPEC 7; Datasheet `${KIPRJMOD}/<Parts table path>` where the Parts table has a
  PDF, else the maker's product page (J2), else empty (passives, MPN still TBD); MPN and Manufacturer from SPEC 6;
- connectivity: every pin gets a short stub and a net label, a GND symbol or a no-connect flag; adjacent same-net
  pins of one function (REF divider, timer node, Q1 gate, FB divider, COMP network, USB D+/D-) are joined by
  short wires;
- PWR_FLAGs only on nets that no power-output pin drives: BATT and GND (J1), VOUT (Q1 drain), +5V1 (L1);
- paper A3 -> A4 (32 parts fit legibly); functional blocks with short headers and one note each, values only
  on the parts.

Before writing, the script checks its own result: every connection point on the 50 mil grid; the drawn
connectivity (wires, labels, GND symbols) gives exactly the SPEC 7 pin -> net map; no wire end on another wire's
middle; no text, body or wire overlaps another; everything inside the A4 frame and outside the title block.
tools/check_netlist.py then checks the KiCad netlist export against SPEC 7 independently (`pdm run verify-sch`).

Guards: refuses if KiCad's lock file exists. Accepts only two states: (1) pre-edit: the 33 removed parts and the
34 surviving parts present with their expected library symbols, no new part, power symbols only GND / PWR_FLAG,
paper A3; (2) applied: exactly the SPEC 7 parts, and the sheet equals what this script writes (prints "already
applied", changes nothing). Anything else stops. The header (version, sheet uuid) and sheet_instances keep their
bytes; CRLF line endings kept; new uuids are uuid5 from this edit's namespace (reproducible). Backup to
pi_power_board-backups/ before writing.
"""
import collections
import datetime
import pathlib
import shutil
import sys
import uuid

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import check_netlist  # noqa: E402
import sch_lib  # noqa: E402
import sexpr  # noqa: E402

ROOT = TOOLS.parent
STEM = 'pi_power_board'
SHEET = ROOT / f'{STEM}.kicad_sch'
LOCK = ROOT / f'~{STEM}.kicad_sch.lck'
BACKUPS = ROOT / f'{STEM}-backups'
PROJECT = STEM
UUID_NS = uuid.UUID('5c3e8f20-7a14-4b9d-8e26-03a1f7c4d903')
PAPER_OLD, PAPER_NEW = '"A3"', '"A4"'

G = 1.27                       # schematic grid pitch, mm: every layout number below is in grid units
STUB = 2                       # default pin stub, grid units
FONT = 1.27                    # mm, fields and labels
HEADER_FONT = 2.0              # mm, block headers
CHAR_W = 1.2                   # mm per character at FONT (measured on a kicad-cli PDF): overlap check
TEXT_H = 1.9                   # mm, text box height at FONT (same measurement)
LABEL_LIFT = 0.25              # mm, label text bottom above its wire
FIELD_GAP = 1.0                # mm, field text from the body
OVERLAP_TOL = 0.05             # mm, boxes touching closer than this are not an overlap
BOLD_THICKNESS = 0.2           # bold header stroke, fraction of the font size
# A4 sheet, KiCad default page layout (mm): inner frame and title block, kept clear
FRAME = (12.0, 12.0, 285.0, 198.0)
TITLE_BLOCK = (176.0, 164.0, 285.0, 198.0)

GND = 'GND'
SURVIVING = ('J1 J2 J4 J5 SW1 Q1 U8 L1 TVS1 TVS2 D3 D5 D6 R3 R4 R5 R8 R9 R14 R15 R16 R17 R18 R21 C5 C8 C15 C17 '
             'C18 C19 C20 C22 C23 C24').split()
NEW = ('U1', 'R23', 'R24')
# SPEC 7 "Removed (33)": ref -> library symbol on the pre-edit sheet (guard)
REMOVED = {
    'U3': 'Comparator:LM397', 'U4': 'Timer:TLC555xD', 'Q2': 'Transistor_FET:2N7002', 'Q4': 'Transistor_FET:2N7002',
    'D1': 'Diode:1N4148W', 'D2': 'Diode:1N4148W', 'D4': 'Diode:1N4148W', 'DZ1': 'Device:D_Zener',
    'DZ2': 'Device:D_Zener', 'C12': 'Device:C_Polarized', 'C25': 'Device:C_Polarized', 'C26': 'Device:C_Polarized',
    **{r: 'Device:R_US' for r in 'R1 R2 R6 R7 R11 R12 R13 R19 R20 R22'.split()},
    **{c: 'Device:C' for c in 'C2 C3 C4 C6 C7 C9 C11 C13 C14 C16 C21'.split()},
}
POWER_LIBS = ('power:GND', 'power:PWR_FLAG')

# lib_id per symbol kind (KiCad 10 standard libraries; SPEC 7 symbol notes)
LIB = {
    'R': 'Device:R_US', 'C': 'Device:C', 'L': 'Device:L', 'D': 'Diode:1N4148W', 'TVS': 'Device:D_Zener',
    'LED': 'Device:LED', 'BAS': 'Diode:BAS21', 'PMOS': 'Transistor_FET:Q_PMOS_GDS', 'CMP': 'Comparator:LM2903',
    'BUCK': 'Regulator_Switching:TPS54336ADDA', 'USB': 'Connector:USB3_A_Stacked',
    'T2': 'Connector:Screw_Terminal_01x02', 'T3': 'Connector:Screw_Terminal_01x03',
    'SW': 'Switch:SW_Nidec_CAS-120A1', 'GND': 'power:GND', 'FLAG': 'power:PWR_FLAG',
}
MULTI_UNIT = ('CMP', 'USB')    # KiCad shows these references with a unit letter (U1A, J2B)

# Manufacturer per Parts-table MPN (SPEC 6 Package / Datasheet columns name the maker)
MANUFACTURER = {
    '1727023': 'Phoenix Contact', '1727010': 'Phoenix Contact', '0484060001': 'Molex',
    'CAS-120TA': 'Nidec Components', 'SQD50P04-13L_GE3': 'Vishay Siliconix', 'LM2903BIDR': 'Texas Instruments',
    'TPS54336ADDA': 'Texas Instruments', 'SRP1038A-100M': 'Bourns', 'SMBJ16A': 'Bourns',
    '1N4148W-E3-08': 'Vishay', 'BAS116LT1G': 'onsemi', 'LTST-C150KRKT': 'Lite-On',
}
# Datasheet where the Parts table has no PDF: the maker's product page
DATASHEET_EXTRA = {'J2': 'https://www.molex.com/en-us/products/part-detail/484060001'}


class P:
    """One placed symbol unit. x, y in grid units; rot in degrees (CCW); fields: 'right' | 'left' | 'above' |
    'below' | 'updown' | ((dx, dy), (dx, dy)) Reference / Value centre offsets in grid units.
    pins: {pin: {'stub': n, 'angle': label angle}} overrides; a pin on a LINK gets no stub unless given here."""

    def __init__(self, ref, kind, x, y, rot=0, unit=1, fields='right', pins=None):
        self.ref, self.kind, self.x, self.y, self.rot, self.unit = ref, kind, x, y, rot, unit
        self.fields, self.pins = fields, pins or {}

    @property
    def key(self):
        return self.ref if self.unit == 1 else f'{self.ref}/{self.unit}'


# ------------------------------------------------------------------------------------------------- layout
# A4, grid units. Top row: input / ACC sense, reference + delay timer, comparator, P-FET switch. Second row: buck,
# USB, status / LED / Pi outputs (right column, above the title block).
PARTS = [
    # Input / ACC sense
    P('J1', 'T3', 14, 30, 180, fields=((2, -6.5), (6, -5))),
    P('TVS1', 'TVS', 30, 38, 270), P('TVS2', 'TVS', 42, 38, 270),
    P('D5', 'D', 30, 52, 180, fields='above'),
    P('SW1', 'SW', 30, 62, fields='below'),
    P('R8', 'R', 50, 56),
    # Reference
    P('R4', 'R', 70, 24), P('R5', 'R', 70, 35), P('R23', 'R', 80, 30, 90, fields='updown'),
    # Delay timer
    P('R24', 'R', 69, 60, 90, fields='updown'), P('D6', 'BAS', 80, 60, 180, fields='below'),
    P('C5', 'C', 88, 65), P('R9', 'R', 106, 65),
    # Comparator
    P('U1', 'CMP', 140, 28, unit=1, fields=((0, -7), (0, -5.5))),
    P('U1', 'CMP', 140, 46, unit=2, fields=((0, -7), (0, -5.5))),
    P('U1', 'CMP', 162, 34, unit=3, fields=((-6, 0), (-10, 2))),
    P('C8', 'C', 168, 31),
    # P-FET switch
    P('Q1', 'PMOS', 196, 34, 270, fields='below'),
    P('R14', 'R', 196, 23, fields='left'), P('R15', 'R', 202, 26, 90, fields='updown'),
    # Status / LED / Pi 12 V output
    P('J4', 'T2', 212, 58, fields='below'),
    P('J5', 'T2', 184, 66, 180, fields='below'),
    P('R21', 'R', 196, 82, 90, fields='updown'),
    P('D3', 'LED', 220, 74, 90, fields='left'), P('R3', 'R', 220, 85, fields='left'),
    # Buck 5.1 V
    P('U8', 'BUCK', 60, 106, fields=((0, -10), (0, -8.5))),
    P('C15', 'C', 14, 100), P('C17', 'C', 29, 100),
    P('C19', 'C', 14, 122), P('R18', 'R', 32, 120), P('C20', 'C', 32, 130),
    P('C18', 'C', 84, 100), P('L1', 'L', 90, 114, 90, fields='updown'),
    P('R16', 'R', 104, 104), P('R17', 'R', 104, 113),
    P('C22', 'C', 56, 132), P('C23', 'C', 74, 132), P('C24', 'C', 92, 132),
    # USB
    P('J2', 'USB', 136, 104, unit=1, fields=((0, -16), (0, -14.5))),
    P('J2', 'USB', 170, 104, unit=2, fields=((0, -16), (0, -14.5))),
]

# Same-net pins joined by wires: (net, [points], label point or None, label angle). A point is 'KEY.PIN' (the pin
# end; units as 'U1/2.PIN') or (x, y) in grid units.
LINKS = [
    ('REF', ['R4.2', (70, 30), 'R5.1'], None, 0),
    ('REF', [(70, 30), 'R23.1'], (72, 30), 0),
    ('D6_A', ['R24.2', 'D6.1'], (73, 60), 0),
    ('C5_T', ['D6.3', (88, 60), 'C5.1'], (84, 60), 0),
    ('C5_T', [(88, 60), (106, 60), 'R9.1'], None, 0),
    ('BATT', ['U1/3.8', (160, 25), (168, 25), 'C8.1'], (161, 25), 0),
    ('Q1_G', ['Q1.1', 'R14.2'], (196, 28), 180),
    ('Q1_G', ['R14.2', 'R15.1'], None, 0),
    ('D3_K', ['D3.1', 'R3.1'], (220, 80), 180),
    ('U8_CRC', ['R18.2', 'C20.1'], (32, 125), 0),
    ('U8_FB', ['R16.2', 'R17.1'], (104, 109), 0),
    ('GND', ['U8.4', 'U8.9'], None, 0),
    ('USB1_D', ['J2.2', 'J2.3'], None, 0),
    ('USB2_D', ['J2/2.11', 'J2/2.12'], None, 0),
    ('GND', ['J2.SH', 'J2.7', 'J2.4'], None, 0),
    ('GND', ['J2/2.SH', 'J2/2.16', 'J2/2.13'], None, 0),
]
# Pins on a link that still get their own stub and label (the link has no label of its own)
LINK_STUB = {'U8.4', 'J2.2', 'J2/2.11', 'J2.4', 'J2/2.13'}

# PWR_FLAG positions (grid units): flag pin at (x, y), wire down to the label / GND symbol
FLAGS = [('BATT', 34, 28), (GND, 54, 28), ('VOUT', 210, 34), ('+5V1', 112, 128)]

# Block headers and notes: (text, x, y, size_mm, bold)
TEXTS = [
    ('INPUT / ACC SENSE', 10, 13, HEADER_FONT, True),
    ('Harness fuse; SW1 closed = key on', 10, 15.5, FONT, False),
    ('REFERENCE', 64, 13, HEADER_FONT, True),
    ('REF follows BATT; R23 adds hysteresis', 64, 15.5, FONT, False),
    ('DELAY TIMER', 64, 50, HEADER_FONT, True),
    ('Key off: delay ~ R9 C5 ln(V0 / REF) (SPEC 3)', 64, 52.5, FONT, False),
    ('COMPARATOR U1', 124, 13, HEADER_FONT, True),
    ('Open collector: low when IN- > REF', 124, 15.5, FONT, False),
    ('P-FET SWITCH', 180, 13, HEADER_FONT, True),
    ('DRV low turns Q1 on: VOUT on', 180, 15.5, FONT, False),
    ('STATUS / LED / PI 12 V', 180, 50, HEADER_FONT, True),
    ('J5 low = ACC on (Pi pull-up)', 180, 52.5, FONT, False),
    ('BUCK 5.1 V', 10, 82, HEADER_FONT, True),
    ('EN floats: enabled by its pull-up', 10, 84.5, FONT, False),
    ('USB', 124, 82, HEADER_FONT, True),
    ('D+ shorted to D- per port (BC1.2)', 124, 84.5, FONT, False),
]


# ------------------------------------------------------------------------------------------------- helpers

def mm(v):
    return round(v * G, 4)


def num(v):
    return sexpr.fmt_num(round(v, 4))


def uid(*parts):
    return str(uuid.uuid5(UUID_NS, '/'.join(str(p) for p in parts)))


def q(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def on_grid(v):
    return abs(v / G - round(v / G)) < 1e-6


def top_level_blocks(src, depth_want=2):
    """(start, end) of every '(' ... ')' at nesting depth depth_want (2 = children of the root list)."""
    blocks, depth, start, i, n = [], 0, None, 0, len(src)
    while i < n:
        c = src[i]
        if c == '"':
            i += 1
            while src[i] != '"':
                i += 2 if src[i] == '\\' else 1
        elif c == '(':
            depth += 1
            if depth == depth_want:
                start = i
        elif c == ')':
            if depth == depth_want:
                blocks.append((start, i + 1))
            depth -= 1
        i += 1
    return blocks


def prop(node, key):
    return next((p[2] for p in sexpr.find_all(node, 'property') if p[1] == key), None)


# ------------------------------------------------------------------------------------------------- geometry

class Geo:
    """Placed-symbol geometry: pin ends, outward directions, body box (graphics + pin lines), sheet mm."""

    def __init__(self, part, libnode):
        self.part, self.lib = part, libnode
        x0, y0 = mm(part.x), mm(part.y)
        self.pins = {}
        pts = []
        for num_, (px, py, ang, length, name, ptype) in sch_lib.lib_pins(libnode, part.unit).items():
            end = sch_lib.to_sheet(x0, y0, part.rot, px, py)
            d = sch_lib.outward(part.rot, ang)
            root = (end[0] - d[0] * length, end[1] - d[1] * length)
            self.pins[num_] = (end, d, name, ptype)
            pts += [end, root]
        lib_box = sch_lib.lib_body_box(libnode, part.unit)
        if lib_box is None:                                   # power unit (U1C): pins only
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            box = (min(xs), min(ys), max(xs), max(ys))
        else:
            box = sch_lib.sheet_box(x0, y0, part.rot, lib_box)
        self.body = box
        xs = [p[0] for p in pts] + [box[0], box[2]]
        ys = [p[1] for p in pts] + [box[1], box[3]]
        self.outline = (min(xs), min(ys), max(xs), max(ys))


def text_box(cx, cy, text, angle=0):
    w, h = len(text) * CHAR_W, TEXT_H
    if angle in (90, 270):
        w, h = h, w
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def label_box(x, y, text, angle):
    w = len(text) * CHAR_W
    if angle == 0:
        return (x, y - TEXT_H - LABEL_LIFT, x + w, y - LABEL_LIFT)
    if angle == 180:
        return (x - w, y - TEXT_H - LABEL_LIFT, x, y - LABEL_LIFT)
    raise SystemExit(f'label {text}: angle {angle} not used on this sheet')


def field_centres(geo, ref_text, val_text):
    part = geo.part
    bx1, by1, bx2, by2 = geo.body
    mx, my = (bx1 + bx2) / 2, (by1 + by2) / 2
    wr, wv = len(ref_text) * CHAR_W, len(val_text) * CHAR_W
    f = part.fields
    if isinstance(f, tuple):
        (rx, ry), (vx, vy) = f
        return (mm(part.x + rx), mm(part.y + ry)), (mm(part.x + vx), mm(part.y + vy))
    if f == 'right':
        return (bx2 + FIELD_GAP + wr / 2, my - G), (bx2 + FIELD_GAP + wv / 2, my + G)
    if f == 'left':
        return (bx1 - FIELD_GAP - wr / 2, my - G), (bx1 - FIELD_GAP - wv / 2, my + G)
    if f == 'above':
        return (mx, by1 - 3.5 * G), (mx, by1 - 1.5 * G)
    if f == 'below':
        return (mx, by2 + 1.5 * G), (mx, by2 + 3.5 * G)
    if f == 'updown':
        return (mx, by1 - 1.5 * G), (mx, by2 + 1.5 * G)
    raise SystemExit(f'{part.ref}: fields {f!r}')


# ------------------------------------------------------------------------------------------------- build

class Sheet:
    def __init__(self, spec, parts_table, old_syms):
        self.spec, self.parts_table, self.old = spec, parts_table, old_syms
        self.libs = {lib_id: sch_lib.flat_symbol(lib_id) for lib_id in sorted(set(LIB.values()))}
        self.geo = {p.key: Geo(p, self.libs[LIB[p.kind]]) for p in PARTS}
        self.wires, self.labels, self.power, self.ncs = [], [], [], []
        self.pwr_n = collections.Counter()

    def pin_end(self, token):
        key, pin = token.rsplit('.', 1)
        return self.geo[key].pins[pin][0]

    def point(self, p):
        return self.pin_end(p) if isinstance(p, str) else (mm(p[0]), mm(p[1]))

    def net_of(self, key, pin):
        return self.spec[key.split('/')[0]]['pins'][pin]

    def add_power(self, kind, x, y, net):
        prefix = '#FLG' if kind == 'FLAG' else '#PWR'
        self.pwr_n[prefix] += 1
        self.power.append((kind, x, y, f'{prefix}{self.pwr_n[prefix]:02d}', net))

    def build(self):
        linked = set()
        for net, pts, lab, ang in LINKS:
            xy = [self.point(p) for p in pts]
            for p in pts:
                if isinstance(p, str):
                    linked.add(p)
                    key, pin = p.rsplit('.', 1)
                    if self.net_of(key, pin) != net:
                        raise SystemExit(f'LINKS {net}: {p} is {self.net_of(key, pin)} in SPEC 7')
            if lab is not None:                       # split the polyline at the label point
                lp = (mm(lab[0]), mm(lab[1]))
                xy = split_at(xy, lp)
                self.labels.append((net, lp[0], lp[1], ang))
            for a, b in zip(xy, xy[1:]):
                self.wires.append((a, b))
        for p in PARTS:
            geo = self.geo[p.key]
            for pin, (end, d, name, ptype) in geo.pins.items():
                net = self.net_of(p.key, pin)
                tok = f'{p.key}.{pin}'
                ov = p.pins.get(pin, {})
                if net is None:
                    if ptype != 'no_connect':
                        self.ncs.append(end)
                    continue
                if tok in linked and tok not in LINK_STUB and 'stub' not in ov:
                    continue
                n = ov.get('stub', STUB)
                tip = (round(end[0] + d[0] * mm(n), 4), round(end[1] + d[1] * mm(n), 4))
                self.wires.append((end, tip))
                if net == GND:
                    self.add_power('GND', tip[0], tip[1], GND)
                else:
                    ang = ov.get('angle', 180 if d == (-1, 0) else 0)
                    self.labels.append((net, tip[0], tip[1], ang))
        for net, x, y in FLAGS:
            top, tip = (mm(x), mm(y)), (mm(x), mm(y + STUB))
            self.add_power('FLAG', top[0], top[1], net)
            self.wires.append((top, tip))
            if net == GND:
                self.add_power('GND', tip[0], tip[1], GND)
            else:
                self.labels.append((net, tip[0], tip[1], 0))
        self.wires = split_t_junctions(self.wires)
        self.junctions = self.find_junctions()

    def find_junctions(self):
        count = collections.Counter()
        for a, b in self.wires:
            count[a] += 1
            count[b] += 1
        pin_pts = {g.pins[n][0] for g in self.geo.values() for n in g.pins}
        return sorted(pt for pt, c in count.items() if c + (pt in pin_pts) >= 3)

    # -------------------------------------------------------------------------------------------- checks
    def check_grid(self):
        pts = [pt for w in self.wires for pt in w] + [(x, y) for _, x, y, _ in self.labels] + self.ncs
        pts += [(x, y) for _, x, y, _, _ in self.power]
        pts += [g.pins[n][0] for g in self.geo.values() for n in g.pins]
        bad = sorted({pt for pt in pts if not (on_grid(pt[0]) and on_grid(pt[1]))})
        if bad:
            raise SystemExit(f'off-grid connection points: {bad[:8]}')

    def check_connectivity(self):
        """Union-find over the drawn items; compare every pin's net with SPEC 7."""
        parent = {}

        def find(a):
            parent.setdefault(a, a)
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            parent[find(a)] = find(b)

        for a, b in self.wires:
            union(('pt', a), ('pt', b))
        for net, x, y, _ in self.labels:
            union(('pt', (x, y)), ('net', net))
        for kind, x, y, _, net in self.power:
            if kind == 'GND':
                union(('pt', (x, y)), ('net', GND))
        nets = {}
        for key, g in self.geo.items():
            for pin, (end, *_r) in g.pins.items():
                root = find(('pt', end))
                names = {n for k, n in parent if k == 'net' and find((k, n)) == root}
                nets[(key, pin)] = names
        errs = []
        for (key, pin), names in sorted(nets.items()):
            want = self.net_of(key, pin)
            got = names or {None}
            if got != {want}:
                errs.append(f'{key}.{pin}: drawn {sorted(map(str, got))}, SPEC {want}')
        for net, x, y, _ in self.labels:                 # a label must sit on a wire end
            if not any((x, y) in w for w in self.wires):
                errs.append(f'label {net} at {(x, y)} not on a wire end')
        if errs:
            raise SystemExit('connectivity differs from SPEC 7:\n  ' + '\n  '.join(errs))

    def check_wires(self):
        """No collinear overlapping wires; no foreign connection point on a wire's interior."""
        pts = {g.pins[n][0] for g in self.geo.values() for n in g.pins} | set(self.ncs)
        pts |= {(x, y) for _, x, y, _ in self.labels} | {(x, y) for _, x, y, _, _ in self.power}
        errs = []
        for i, (a, b) in enumerate(self.wires):
            if a[0] != b[0] and a[1] != b[1]:
                errs.append(f'diagonal wire {a}-{b}')
            for pt in pts:
                if pt not in (a, b) and on_segment(pt, a, b):
                    errs.append(f'point {pt} on the interior of wire {a}-{b}')
            for c, d in self.wires[i + 1:]:
                if collinear_overlap(a, b, c, d):
                    errs.append(f'overlapping wires {a}-{b} and {c}-{d}')
        if errs:
            raise SystemExit('wire errors:\n  ' + '\n  '.join(errs[:20]))

    def boxes(self):
        """(kind, name, box) of everything drawn, for the overlap check."""
        out = []
        for key, g in self.geo.items():
            out.append(('body', key, g.outline))
            ref_t, val_t = self.field_texts(g.part)
            (rx, ry), (vx, vy) = field_centres(g, ref_t, val_t)
            out.append(('text', f'{key} Reference', text_box(rx, ry, ref_t)))
            out.append(('text', f'{key} Value', text_box(vx, vy, val_t)))
        for net, x, y, ang in self.labels:
            out.append(('text', f'label {net} {x},{y}', label_box(x, y, net, ang)))
        for kind, x, y, ref, net in self.power:
            if kind == 'GND':
                out.append(('body', f'GND {x},{y}', (x - G, y, x + G, y + 2 * G)))
            else:
                out.append(('body', f'{ref} {net}', (x - G / 2, y - 2 * G, x + G / 2, y)))
                out.append(('text', f'{ref} PWR_FLAG', text_box(x, y - 3 * G, 'PWR_FLAG')))
        for text, x, y, size, _bold in TEXTS:
            w = len(text) * CHAR_W * size / FONT
            out.append(('text', f'text {text[:20]}', (mm(x), mm(y) - TEXT_H * size / FONT, mm(x) + w, mm(y))))
        return out

    def check_overlaps(self):
        items = self.boxes()
        errs = []
        for i, (k1, n1, b1) in enumerate(items):
            for k2, n2, b2 in items[i + 1:]:
                if boxes_overlap(b1, b2):
                    errs.append(f'{n1} overlaps {n2}')
        for a, b in self.wires:
            wb = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            own = {key for key, g in self.geo.items() if any(g.pins[n][0] in (a, b) for n in g.pins)}
            for k, n, box in items:
                if n not in own and boxes_overlap(wb, box, strict=True):
                    errs.append(f'wire {a}-{b} crosses {n}')
        for k, n, box in items:                                       # page: inside the frame, off the title
            if not (FRAME[0] <= box[0] and FRAME[1] <= box[1] and box[2] <= FRAME[2] and box[3] <= FRAME[3]):
                errs.append(f'{n} outside the A4 frame {tuple(round(v, 1) for v in box)}')
            if boxes_overlap(box, TITLE_BLOCK):
                errs.append(f'{n} on the title block')
        if errs:
            raise SystemExit(f'{len(errs)} layout overlaps:\n  ' + '\n  '.join(errs))

    def field_texts(self, part):
        shown = part.ref + (chr(ord('A') + part.unit - 1) if part.kind in MULTI_UNIT else '')
        return shown, self.spec[part.ref]['value']

    # -------------------------------------------------------------------------------------------- output
    def fields_for(self, part):
        ref = part.ref
        s = self.spec[ref]
        pt = self.parts_table.get(ref, {'mpn': '', 'datasheet': ''})
        ds = (check_netlist.KIPRJMOD + pt['datasheet']) if pt['datasheet'] else DATASHEET_EXTRA.get(ref, '')
        lib = self.libs[LIB[part.kind]]
        out = [('Reference', ref, True), ('Value', s['value'], True), ('Footprint', s['footprint'], False),
               ('Datasheet', ds, False), ('Description', prop(lib, 'Description') or '', False)]
        maker = MANUFACTURER.get(pt['mpn'])
        if pt['mpn'] and not maker:
            raise SystemExit(f'{ref}: no manufacturer for MPN {pt["mpn"]}: add it to MANUFACTURER')
        if maker:
            out.append(('Manufacturer', maker, False))
        if pt['mpn']:
            out.append(('MPN', pt['mpn'], False))
        return out

    def symbol_text(self, part, inst_path):
        g = self.geo[part.key]
        x0, y0 = mm(part.x), mm(part.y)
        fangle = 90 if part.rot in (90, 270) else 0
        old = self.old.get((part.ref, part.unit))
        sym_uuid = old['uuid'] if old else uid('symbol', part.key)
        fields = self.fields_for(part)
        (rx, ry), (vx, vy) = field_centres(g, *self.field_texts(part))
        pos = {'Reference': (rx, ry), 'Value': (vx, vy)}
        lines = ['\t(symbol', f'\t\t(lib_id {q(LIB[part.kind])})', f'\t\t(at {num(x0)} {num(y0)} {part.rot})',
                 f'\t\t(unit {part.unit})', '\t\t(body_style 1)', '\t\t(exclude_from_sim no)', '\t\t(in_bom yes)',
                 '\t\t(on_board yes)', '\t\t(in_pos_files yes)', '\t\t(dnp no)', f'\t\t(uuid {q(sym_uuid)})']
        for key, value, shown in fields:
            fx, fy = pos.get(key, (x0, y0))
            lines += field_lines(key, value, fx, fy, fangle, hide=not shown)
        for pin in g.pins:
            pu = (old or {}).get('pins', {}).get(pin) or uid('pin', part.key, pin)
            lines += [f'\t\t(pin {q(pin)}', f'\t\t\t(uuid {q(pu)})', '\t\t)']
        lines += ['\t\t(instances', f'\t\t\t(project {q(PROJECT)}', f'\t\t\t\t(path {q(inst_path)}',
                  f'\t\t\t\t\t(reference {q(part.ref)})', f'\t\t\t\t\t(unit {part.unit})', '\t\t\t\t)', '\t\t\t)',
                  '\t\t)', '\t)']
        return lines

    def power_text(self, item, inst_path):
        kind, x, y, ref, net = item
        lib_id = LIB[kind]
        value = GND if kind == 'GND' else 'PWR_FLAG'
        su = uid('power', kind, net, x, y)
        vy = y + 2.5 * G if kind == 'GND' else y - 3 * G
        lines = ['\t(symbol', f'\t\t(lib_id {q(lib_id)})', f'\t\t(at {num(x)} {num(y)} 0)', '\t\t(unit 1)',
                 '\t\t(body_style 1)', '\t\t(exclude_from_sim no)', '\t\t(in_bom yes)', '\t\t(on_board yes)',
                 '\t\t(in_pos_files yes)', '\t\t(dnp no)', f'\t\t(uuid {q(su)})']
        lines += field_lines('Reference', ref, x, y + 3 * G, 0, hide=True)
        lines += field_lines('Value', value, x, vy, 0, hide=(kind == 'GND'))
        lines += field_lines('Footprint', '', x, y, 0, hide=True)
        lines += field_lines('Datasheet', '', x, y, 0, hide=True)
        lines += field_lines('Description', prop(self.libs[lib_id], 'Description') or '', x, y, 0, hide=True)
        lines += ['\t\t(pin "1"', f'\t\t\t(uuid {q(uid("power-pin", kind, net, x, y))})', '\t\t)']
        lines += ['\t\t(instances', f'\t\t\t(project {q(PROJECT)}', f'\t\t\t\t(path {q(inst_path)}',
                  f'\t\t\t\t\t(reference {q(ref)})', '\t\t\t\t\t(unit 1)', '\t\t\t\t)', '\t\t\t)', '\t\t)']
        return lines + ['\t)']

    def items_text(self, inst_path):
        out = []
        for x, y in self.junctions:
            out += ['\t(junction', f'\t\t(at {num(x)} {num(y)})', '\t\t(diameter 0)', '\t\t(color 0 0 0 0)',
                    f'\t\t(uuid {q(uid("junction", x, y))})', '\t)']
        for x, y in sorted(self.ncs):
            out += ['\t(no_connect', f'\t\t(at {num(x)} {num(y)})', f'\t\t(uuid {q(uid("nc", x, y))})', '\t)']
        for a, b in sorted(self.wires):
            out += ['\t(wire', '\t\t(pts', f'\t\t\t(xy {num(a[0])} {num(a[1])}) (xy {num(b[0])} {num(b[1])})',
                    '\t\t)', '\t\t(stroke', '\t\t\t(width 0)', '\t\t\t(type default)', '\t\t)',
                    f'\t\t(uuid {q(uid("wire", a, b))})', '\t)']
        for net, x, y, ang in sorted(self.labels):
            just = 'left bottom' if ang == 0 else 'right bottom'
            out += [f'\t(label {q(net)}', f'\t\t(at {num(x)} {num(y)} {ang})', '\t\t(effects', '\t\t\t(font',
                    f'\t\t\t\t(size {num(FONT)} {num(FONT)})', '\t\t\t)', f'\t\t\t(justify {just})', '\t\t)',
                    f'\t\t(uuid {q(uid("label", net, x, y))})', '\t)']
        for text, x, y, size, bold in TEXTS:
            font = [f'\t\t\t\t(size {num(size)} {num(size)})']
            if bold:
                font += [f'\t\t\t\t(thickness {num(size * BOLD_THICKNESS)})', '\t\t\t\t(bold yes)']
            out += [f'\t(text {q(text)}', '\t\t(exclude_from_sim no)', f'\t\t(at {num(mm(x))} {num(mm(y))} 0)',
                    '\t\t(effects', '\t\t\t(font', *font, '\t\t\t)', '\t\t\t(justify left bottom)', '\t\t)',
                    f'\t\t(uuid {q(uid("text", text))})', '\t)']
        for p in PARTS:
            out += self.symbol_text(p, inst_path)
        for item in self.power:
            out += self.power_text(item, inst_path)
        return out

    def lib_symbols_text(self):
        out = ['\t(lib_symbols']
        for lib_id in sorted(self.libs):
            out.append(sexpr.dump(self.libs[lib_id], 2))
        return '\n'.join(out + ['\t)'])


def field_lines(key, value, x, y, angle, hide):
    out = [f'\t\t(property {q(key)} {q(value)}', f'\t\t\t(at {num(x)} {num(y)} {angle})']
    if hide:
        out.append('\t\t\t(hide yes)')
    out += ['\t\t\t(show_name no)', '\t\t\t(do_not_autoplace no)', '\t\t\t(effects', '\t\t\t\t(font',
            f'\t\t\t\t\t(size {num(FONT)} {num(FONT)})', '\t\t\t\t)', '\t\t\t)', '\t\t)']
    return out


def on_segment(pt, a, b):
    if a[0] == b[0] == pt[0]:
        return min(a[1], b[1]) < pt[1] < max(a[1], b[1])
    if a[1] == b[1] == pt[1]:
        return min(a[0], b[0]) < pt[0] < max(a[0], b[0])
    return False


def collinear_overlap(a, b, c, d):
    if a[0] == b[0] == c[0] == d[0]:
        lo, hi = max(min(a[1], b[1]), min(c[1], d[1])), min(max(a[1], b[1]), max(c[1], d[1]))
        return hi - lo > 1e-6
    if a[1] == b[1] == c[1] == d[1]:
        lo, hi = max(min(a[0], b[0]), min(c[0], d[0])), min(max(a[0], b[0]), max(c[0], d[0]))
        return hi - lo > 1e-6
    return False


def split_at(xy, pt):
    """Insert pt into the polyline xy (it must lie on a segment or be a vertex)."""
    if pt in xy:
        return xy
    for i, (a, b) in enumerate(zip(xy, xy[1:])):
        if on_segment(pt, a, b):
            return xy[:i + 1] + [pt] + xy[i + 1:]
    raise SystemExit(f'label point {pt} not on the link {xy}')


def split_t_junctions(wires):
    """Split a wire wherever another wire ends on its interior (KiCad joins only at wire ends)."""
    changed = True
    while changed:
        changed = False
        ends = {pt for w in wires for pt in w}
        for i, (a, b) in enumerate(wires):
            hit = next((pt for pt in ends if on_segment(pt, a, b)), None)
            if hit:
                wires = wires[:i] + [(a, hit), (hit, b)] + wires[i + 1:]
                changed = True
                break
    return wires


def boxes_overlap(a, b, strict=False):
    tol = OVERLAP_TOL if not strict else OVERLAP_TOL * 2
    return a[0] < b[2] - tol and b[0] < a[2] - tol and a[1] < b[3] - tol and b[1] < a[3] - tol


# ------------------------------------------------------------------------------------------------- main

def read_old(src, blocks):
    """{ref: [{'lib_id', 'uuid', 'pins', 'unit'}, ...]} of every placed symbol (power symbols under '#...')."""
    syms = {}
    for s, e in blocks:
        if src.startswith('(symbol', s):
            node = sexpr.parse(src[s:e])
            ref = prop(node, 'Reference')
            pins = {p[1]: sexpr.find(p, 'uuid')[1] for p in sexpr.find_all(node, 'pin')}
            syms.setdefault(ref, []).append({'lib_id': sexpr.find(node, 'lib_id')[1], 'uuid': sexpr.find(node,
                                             'uuid')[1], 'pins': pins, 'unit': int(sexpr.find(node, 'unit')[1])})
    return syms


def check_state(spec, old, text):
    """'pre-edit' or 'applied'; stops on anything else."""
    real = {r for r in old if not r.startswith('#')}
    if set(SURVIVING) | set(NEW) != set(spec) or set(REMOVED) & set(spec):
        raise SystemExit('SPEC 7 refs differ from this script\'s surviving + new lists: SPEC changed, stop')
    bad_power = sorted({v['lib_id'] for r, vs in old.items() if r.startswith('#') for v in vs} - set(POWER_LIBS))
    if bad_power:
        raise SystemExit(f'power symbols {bad_power}: unexpected state')
    kinds = {p.ref: LIB[p.kind] for p in PARTS}
    for ref in sorted(real & set(spec)):
        libs = {v['lib_id'] for v in old[ref]}
        if libs != {kinds[ref]}:
            raise SystemExit(f'{ref}: symbol {sorted(libs)}, expected {kinds[ref]}: unexpected state')
    if real & set(REMOVED):
        for ref, lib_id in REMOVED.items():
            if ref not in old or {v['lib_id'] for v in old[ref]} != {lib_id}:
                raise SystemExit(f'{ref}: expected {lib_id}, found {old.get(ref)}: unexpected state')
        missing = set(SURVIVING) - real
        extra = real - set(SURVIVING) - set(REMOVED)
        if missing or extra:
            raise SystemExit(f'pre-edit sheet: missing {sorted(missing)}, unexpected {sorted(extra)}')
        if text.count(f'(paper {PAPER_OLD})') != 1:
            raise SystemExit(f'pre-edit sheet: paper is not {PAPER_OLD}: unexpected state')
        return 'pre-edit'
    if real != set(spec):
        raise SystemExit(f'removed parts gone but the sheet is not the applied state: missing '
                         f'{sorted(set(spec) - real)}, extra {sorted(real - set(spec))}: fix by hand')
    return 'applied'


def main(argv):
    dry = '--dry-run' in argv
    if LOCK.exists():
        raise SystemExit(f'{LOCK.name} exists: close the schematic in KiCad first')
    md = check_netlist.SPEC.read_text(encoding='utf-8')
    spec, parts_table = check_netlist.parse_netlist_table(md), check_netlist.parse_parts_table(md)
    placed = {p.ref for p in PARTS}
    if placed != set(spec):
        raise SystemExit(f'layout vs SPEC 7: missing {sorted(set(spec) - placed)}, extra {sorted(placed - set(spec))}')
    with open(SHEET, encoding='utf-8', newline='') as fh:
        src = fh.read()
    eol = '\r\n' if '\r\n' in src else '\n'
    text = src.replace('\r\n', '\n')
    blocks = top_level_blocks(text)
    old = read_old(text, blocks)
    state = check_state(spec, old, text)
    old_kept = {(r, v['unit']): v for r, vs in old.items() if r in spec for v in vs}

    sheet = Sheet(spec, parts_table, old_kept)
    sheet.build()
    sheet.check_grid()
    sheet.check_wires()
    sheet.check_connectivity()
    sheet.check_overlaps()

    root_uuid = sexpr.find(sexpr.parse(text[:text.index('(lib_symbols')] + ')'), 'uuid')[1]
    inst_path = f'/{root_uuid}'
    lib_s, lib_e = next((a, b) for a, b in blocks if text.startswith('(lib_symbols', a))
    si_s, si_e = next((a, b) for a, b in blocks if text.startswith('(sheet_instances', a))
    head = text[:text.rfind('\n', 0, lib_s) + 1].replace(f'(paper {PAPER_OLD})', f'(paper {PAPER_NEW})')
    body = '\n'.join([sheet.lib_symbols_text()] + sheet.items_text(inst_path))
    out = head + body + '\n\t' + text[si_s:si_e] + text[si_e:]
    out = out.replace('\n', eol)

    if state == 'applied':
        if out == src:
            print(f'{SHEET.name}: already applied (SPEC 7 simplified sheet); nothing changed')
            return
        raise SystemExit('the sheet has the SPEC 7 parts but differs from what 03 writes (hand edits?): '
                         'stop; edit by hand or with a new script')
    if dry:
        print('dry run: layout and connectivity checks passed; nothing written')
        return
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_sch'
    shutil.copy2(SHEET, backup)
    with open(SHEET, 'w', encoding='utf-8', newline='') as fh:
        fh.write(out)
    kept = sorted({r for r, _u in old_kept})
    print(f'backup {backup.relative_to(ROOT)}')
    print(f'{SHEET.name}: removed {len(REMOVED)}; {len(kept)} kept (uuids reused), {len(set(spec) - set(kept))} new; '
          f'{len(sheet.wires)} wires, {len(sheet.labels)} labels, {len(sheet.junctions)} junctions, '
          f'{len(sheet.ncs)} no-connects, {len(sheet.power)} power symbols; paper {PAPER_NEW}')


if __name__ == '__main__':
    main(sys.argv)
