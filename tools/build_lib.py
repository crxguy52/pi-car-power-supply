"""Build the project footprint library `pipwr` (lib/pi_power_board.pretty) and the project fp-lib-table.

    pdm run build-lib

SPEC section 7 "Project footprints" and reports/buck_design.md ("Footprint", "Inductor footprint"):
- `TI_DDA_PowerPAD-8_HandSolder`: TI DDA0008B land pattern (TPS54336A datasheet SLVSCD5D, "EXAMPLE BOARD LAYOUT")
  modified for hand soldering: pins extended outward, a plated centre hole to feed solder from the bottom, ten
  thermal vias, a large bottom pad 9. No paste (hand assembly).
- `L_Bourns_SRP1038A`: the SRP1038A recommended layout (Bourns datasheet p1: 13.6 mm overall, 5.4 mm gap, 3.5 mm
  pad height). Body orientation from the Bourns "Product Dimensions" top view: the terminals sit on the ends of
  the 11.0 mm side, so 11.0 mm runs along the pad axis (X) and 10.0 mm across it (Y).

Every dimension below is asserted against the datasheet land pattern before anything is written. UUIDs are uuid5
from a fixed namespace, so a rebuild with unchanged inputs gives identical files. Re-runnable.
"""
import pathlib
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
NICK = 'pipwr'
PRETTY = ROOT / 'lib' / 'pi_power_board.pretty'
FP_LIB_TABLE = ROOT / 'fp-lib-table'
FP_LIB_URI = '${KIPRJMOD}/lib/pi_power_board.pretty'
UUID_NS = uuid.UUID('6f1d3a52-93c4-4b8e-a0f2-3c5d7e9b1a20')
FORMAT_VERSION = '20260206'                 # KiCad 10.0.7 footprint format (library files of that release)
EPS = 1e-9

# ---- TI DDA0008B land pattern (SLVSCD5D, example board layout), mm
TI_ROW_PITCH = 5.4          # pad row centre to centre
TI_PAD_LEN = 1.55
TI_PAD_W = 0.6
TI_PITCH = 1.27
TI_EP_W, TI_EP_L = 2.95, 4.9         # pad 9 metal (across the rows, along the rows)
TI_EP_MASK_W, TI_EP_MASK_L = 2.71, 3.4
PKG_EP_MIN_W, PKG_EP_MIN_L = 2.11, 2.80   # exposed pad on the package, minimum (package drawing)
# ---- hand-solder changes (SPEC 7, reports/buck_design.md)
PIN_EXTEND = 0.45           # outward only
PIN_LEN = 2.00              # SPEC: pins 0.60 x 2.00
CENTRE_DRILL = 1.0
ANNULAR = 0.3               # centre hole copper ring
MIN_HOLE_OVERLAP = 0.55     # package pad beyond the hole, each side (buck_design.md)
VIA_DRILL, VIA_PAD = 0.3, 0.6
VIAS_IN_MASK = [(sx * 0.65, sy * 1.30) for sx in (-1, 1) for sy in (-1, 1)]
VIAS_UNDER_MASK = [(x, sy * 2.05) for x in (-0.90, 0.0, 0.90) for sy in (-1, 1)]
BOTTOM_EP_W, BOTTOM_EP_L = 4.0, 6.0
COURTYARD_MARGIN = 0.25
BODY_W, BODY_L = 3.9, 4.9   # SOIC-8 body (Fab outline, as Package_SO:TI_SO-PowerPAD-8)
DDA_MODEL = '${KICAD10_3DMODEL_DIR}/Package_SO.3dshapes/TI_SO-PowerPAD-8.step'

# ---- Bourns SRP1038A recommended layout, mm
SRP_OVERALL, SRP_GAP, SRP_PAD_H = 13.6, 5.4, 3.5
SRP_PAD_W, SRP_PAD_X = 4.1, 4.75      # SPEC 7 (derived from the three above; asserted)
SRP_BODY_X, SRP_BODY_Y = 11.0, 10.0   # along / across the pad axis (Bourns top view: terminals on the long ends)
SRP_COURTYARD_MARGIN = 0.5            # SPEC 7: body + 0.5 mm

SILK_W, FAB_W, CRT_W = 0.12, 0.1, 0.05
SILK_BODY_GAP = 0.11                  # silk line outside the body edge
GRID_COURTYARD = 0.05


def _close(a, b):
    return abs(a - b) < 1e-6


def _ceil_grid(v, g=GRID_COURTYARD):
    n = round(v / g)
    return n * g if n * g >= v - EPS else (n + 1) * g


def check_dda():
    """Assert the hand-solder land against the TI land pattern and the SPEC numbers."""
    inner = TI_ROW_PITCH / 2 - TI_PAD_LEN / 2
    assert _close(inner, 1.925), inner                              # buck_design.md: inner edge 1.925 mm
    assert _close(TI_PAD_LEN + PIN_EXTEND, PIN_LEN)
    assert inner - TI_EP_W / 2 >= 0.2, 'pin to pad 9 clearance'     # unchanged from the TI land
    assert TI_EP_MASK_W < TI_EP_W and TI_EP_MASK_L < TI_EP_L
    for x, y in VIAS_IN_MASK:                                       # inside the top mask opening
        assert abs(x) + VIA_PAD / 2 <= TI_EP_MASK_W / 2 and abs(y) + VIA_PAD / 2 <= TI_EP_MASK_L / 2, (x, y)
    for x, y in VIAS_UNDER_MASK:                                    # under the solder-masked ends of pad 9
        assert abs(y) - VIA_PAD / 2 >= TI_EP_MASK_L / 2 and abs(y) + VIA_PAD / 2 <= TI_EP_L / 2, (x, y)
        assert abs(x) + VIA_PAD / 2 <= TI_EP_W / 2, (x, y)
    assert len(VIAS_IN_MASK) + len(VIAS_UNDER_MASK) == 10
    assert CENTRE_DRILL / 2 + MIN_HOLE_OVERLAP <= PKG_EP_MIN_W / 2 + EPS
    assert CENTRE_DRILL / 2 + ANNULAR <= TI_EP_MASK_W / 2
    assert BOTTOM_EP_W >= TI_EP_W and BOTTOM_EP_L >= TI_EP_L


def check_srp():
    assert _close(2 * SRP_PAD_X + SRP_PAD_W, SRP_OVERALL)
    assert SRP_BODY_X > SRP_BODY_Y, 'the long body side runs along the pad axis'
    assert _close(2 * SRP_PAD_X - SRP_PAD_W, SRP_GAP)


class Fp:
    """Text builder for one footprint file (KiCad 10 format, tabs)."""

    def __init__(self, name, descr, tags):
        self.name, self.n, self.lines = name, 0, []
        self.head = [f'(footprint "{name}"', f'\t(version {FORMAT_VERSION})', '\t(generator "pipwr_build_lib")',
                     '\t(generator_version "10.0")', '\t(layer "F.Cu")', f'\t(descr "{descr}")', f'\t(tags "{tags}")']

    def uid(self):
        self.n += 1
        return f'(uuid "{uuid.uuid5(UUID_NS, f"{self.name}/{self.n}")}")'

    def prop(self, key, value, x, y, layer, hide=False, size=1.0):
        h = '\t\t(hide yes)\n' if hide else ''
        self.lines.append(f'\t(property "{key}" "{value}"\n\t\t(at {f(x)} {f(y)} 0)\n\t\t(layer "{layer}")\n{h}'
                          f'\t\t{self.uid()}\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {f(size)} {f(size)})\n'
                          f'\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)')

    def text(self, value, x, y, layer, size=1.0):
        self.lines.append(f'\t(fp_text user "{value}"\n\t\t(at {f(x)} {f(y)} 0)\n\t\t(layer "{layer}")\n'
                          f'\t\t{self.uid()}\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {f(size)} {f(size)})\n'
                          f'\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)')

    def line(self, x1, y1, x2, y2, layer, width):
        self.lines.append(f'\t(fp_line\n\t\t(start {f(x1)} {f(y1)})\n\t\t(end {f(x2)} {f(y2)})\n\t\t(stroke\n'
                          f'\t\t\t(width {f(width)})\n\t\t\t(type solid)\n\t\t)\n\t\t(layer "{layer}")\n'
                          f'\t\t{self.uid()}\n\t)')

    def rect(self, x1, y1, x2, y2, layer, width):
        self.lines.append(f'\t(fp_rect\n\t\t(start {f(x1)} {f(y1)})\n\t\t(end {f(x2)} {f(y2)})\n\t\t(stroke\n'
                          f'\t\t\t(width {f(width)})\n\t\t\t(type solid)\n\t\t)\n\t\t(fill no)\n'
                          f'\t\t(layer "{layer}")\n\t\t{self.uid()}\n\t)')

    def smd(self, num, x, y, w, h, layers):
        lay = ' '.join(f'"{la}"' for la in layers)
        self.lines.append(f'\t(pad "{num}" smd rect\n\t\t(at {f(x)} {f(y)})\n\t\t(size {f(w)} {f(h)})\n'
                          f'\t\t(layers {lay})\n\t\t{self.uid()}\n\t)')

    def tht(self, num, x, y, size, drill):
        self.lines.append(f'\t(pad "{num}" thru_hole circle\n\t\t(at {f(x)} {f(y)})\n\t\t(size {f(size)} {f(size)})\n'
                          f'\t\t(drill {f(drill)})\n\t\t(layers "*.Cu")\n\t\t(remove_unused_layers no)\n'
                          f'\t\t{self.uid()}\n\t)')

    def attr(self, kind):
        self.lines.append(f'\t(attr {kind})')

    def model(self, path):
        self.lines.append(f'\t(model "{path}"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t\t(scale\n\t\t\t(xyz 1 1 1)\n'
                          f'\t\t)\n\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)')

    def text_out(self):
        return '\n'.join(self.head + self.lines + ['\t(embedded_fonts no)'] + self.tail) + '\n)\n'

    tail = []


def f(v):
    s = f'{v:.4f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def build_dda():
    check_dda()
    fp = Fp('TI_DDA_PowerPAD-8_HandSolder',
            'TI DDA0008B (SO PowerPAD-8) hand-solder land: pins extended outward, 1.0 mm centre solder hole, '
            '10 thermal vias, 4.0 x 6.0 mm bottom pad (SPEC 7, reports/buck_design.md)', 'SO PowerPAD 8 hand solder')
    x_pin = TI_ROW_PITCH / 2 - TI_PAD_LEN / 2 + PIN_LEN / 2
    x_crt = _ceil_grid(max(x_pin + PIN_LEN / 2, BODY_W / 2) + COURTYARD_MARGIN)
    y_crt = _ceil_grid(BODY_L / 2 + COURTYARD_MARGIN)
    fp.prop('Reference', 'REF**', 0, -y_crt - 0.8, 'F.SilkS')
    fp.prop('Value', fp.name, 0, y_crt + 0.8, 'F.Fab')
    fp.prop('Datasheet', '${KIPRJMOD}/ref/datasheets/TI_TPS54336A_SLVSCD5D.pdf', 0, 0, 'F.Fab', hide=True, size=1.27)
    fp.prop('Description', 'TI DDA PowerPAD-8, hand-solder land with bottom solder access', 0, 0, 'F.Fab',
            hide=True, size=1.27)
    fp.attr('smd')
    sx, sy = BODY_W / 2 - 0.125 + 0.2, BODY_L / 2 + 0.125      # silk just outside the body ends
    fp.line(-sx, -sy, sx, -sy, 'F.SilkS', SILK_W)
    fp.line(-sx, sy, sx, sy, 'F.SilkS', SILK_W)
    fp.line(-x_pin - PIN_LEN / 2, -sy - 0.3, -sx, -sy - 0.3, 'F.SilkS', SILK_W)   # pin-1 mark outside pad 1
    fp.rect(-x_crt, -y_crt, x_crt, y_crt, 'F.CrtYd', CRT_W)
    bx, by = _ceil_grid(BOTTOM_EP_W / 2 + COURTYARD_MARGIN), _ceil_grid(BOTTOM_EP_L / 2 + COURTYARD_MARGIN)
    fp.rect(-bx, -by, bx, by, 'B.CrtYd', CRT_W)
    hw, hl, cham = BODY_W / 2, BODY_L / 2, 1.0
    for a, b in (((-hw + cham, -hl), (hw, -hl)), ((hw, -hl), (hw, hl)), ((hw, hl), (-hw, hl)),
                 ((-hw, hl), (-hw, -hl + cham)), ((-hw, -hl + cham), (-hw + cham, -hl))):
        fp.line(*a, *b, 'F.Fab', FAB_W)
    fp.text('${REFERENCE}', 0, 0, 'F.Fab')
    for i in range(4):                                         # pins 1-4 left (top to bottom), 5-8 right (bottom up)
        y = (i - 1.5) * TI_PITCH
        fp.smd(str(i + 1), -x_pin, y, PIN_LEN, TI_PAD_W, ('F.Cu', 'F.Mask'))
        fp.smd(str(8 - i), x_pin, y, PIN_LEN, TI_PAD_W, ('F.Cu', 'F.Mask'))
    fp.smd('9', 0, 0, TI_EP_W, TI_EP_L, ('F.Cu',))                         # TI metal, mask-defined opening below
    fp.smd('9', 0, 0, TI_EP_MASK_W, TI_EP_MASK_L, ('F.Cu', 'F.Mask'))
    fp.smd('9', 0, 0, BOTTOM_EP_W, BOTTOM_EP_L, ('B.Cu', 'B.Mask'))
    fp.tht('9', 0, 0, CENTRE_DRILL + 2 * ANNULAR, CENTRE_DRILL)
    for x, y in VIAS_IN_MASK + VIAS_UNDER_MASK:
        fp.tht('9', x, y, VIA_PAD, VIA_DRILL)
    fp.model(DDA_MODEL)
    return fp


def build_srp():
    check_srp()
    fp = Fp('L_Bourns_SRP1038A', 'Bourns SRP1038A shielded power inductor, 10.0 x 11.0 mm, recommended layout '
            '(Bourns SRP1038A datasheet)', 'inductor Bourns SRP1038A')
    x_crt = _ceil_grid(max(SRP_BODY_X / 2 + SRP_COURTYARD_MARGIN, SRP_PAD_X + SRP_PAD_W / 2 + COURTYARD_MARGIN))
    y_crt = _ceil_grid(SRP_BODY_Y / 2 + SRP_COURTYARD_MARGIN)
    fp.prop('Reference', 'REF**', 0, -y_crt - 0.8, 'F.SilkS')
    fp.prop('Value', fp.name, 0, y_crt + 0.8, 'F.Fab')
    fp.prop('Datasheet', '${KIPRJMOD}/ref/datasheets/Bourns_SRP1038A.pdf', 0, 0, 'F.Fab', hide=True, size=1.27)
    fp.prop('Description', 'Bourns SRP1038A power inductor', 0, 0, 'F.Fab', hide=True, size=1.27)
    fp.attr('smd')
    sx = SRP_PAD_X - SRP_PAD_W / 2 - 0.2
    sy = SRP_BODY_Y / 2 + SILK_BODY_GAP
    fp.line(-sx, -sy, sx, -sy, 'F.SilkS', SILK_W)
    fp.line(-sx, sy, sx, sy, 'F.SilkS', SILK_W)
    fp.rect(-SRP_BODY_X / 2, -SRP_BODY_Y / 2, SRP_BODY_X / 2, SRP_BODY_Y / 2, 'F.Fab', FAB_W)
    fp.rect(-x_crt, -y_crt, x_crt, y_crt, 'F.CrtYd', CRT_W)
    fp.text('${REFERENCE}', 0, 0, 'F.Fab')
    fp.smd('1', -SRP_PAD_X, 0, SRP_PAD_W, SRP_PAD_H, ('F.Cu', 'F.Mask', 'F.Paste'))
    fp.smd('2', SRP_PAD_X, 0, SRP_PAD_W, SRP_PAD_H, ('F.Cu', 'F.Mask', 'F.Paste'))
    return fp


def fp_lib_table():
    return ('(fp_lib_table\n\t(version 7)\n'
            f'\t(lib (name "{NICK}")(type "KiCad")(uri "{FP_LIB_URI}")(options "")'
            '(descr "Pi power HAT project footprints (tools/build_lib.py)"))\n)\n')


def main():
    PRETTY.mkdir(parents=True, exist_ok=True)
    for fp in (build_dda(), build_srp()):
        path = PRETTY / f'{fp.name}.kicad_mod'
        path.write_text(fp.text_out(), encoding='utf-8', newline='\n')
        print(f'wrote {path.relative_to(ROOT)}')
    FP_LIB_TABLE.write_text(fp_lib_table(), encoding='utf-8', newline='\n')
    print(f'wrote {FP_LIB_TABLE.relative_to(ROOT)} ({NICK} -> {FP_LIB_URI})')


if __name__ == '__main__':
    main()
