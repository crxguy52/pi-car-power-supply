"""Post-schematic edit 08 (2026-11-05): redraw pi_power_board.kicad_sch for the CD4541B counter timer (SPEC 7).

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/08_cd4541_timer.py [--dry-run]

What and why (SPEC header notes "counter timer on paper" and "project lead decisions a-c", SPEC 2-4, SPEC 6 Parts,
SPEC 7 contract; DECISIONS 2026-11-05): the LM2903B RC / comparator timer is replaced by U5 CD4541B (RC
oscillator + 16-stage counter) on VDD_TMR, which is +5V1 through D7 with C8 as hold-up (project lead: U5 rides
through a U8 hiccup off time). 37 parts plus J1, J2, J4, J5 and SW1.

- removed with every wire, label, no-connect and note of the old sheet: U1 (units A, B, C), R4, R5, R9, R23, R24,
  C5, C27, C28 (SPEC 7 "Removed"); nets REF, C5_T, D6_A go with them. 07_low_trip_timer.py never ran: its C28
  removal is part of this edit;
- the 31 surviving parts keep their symbol uuid and pin uuids (the board links footprints by symbol uuid; J1, J2,
  J4, J5 are fixed on the board); their value, footprint and fields follow SPEC 7 / SPEC 6 (R8 22 kohm and pin 2
  on ACC_G, D6 on ACC_G / HOLD_G, C8 10 uF 1206 on VDD_TMR, C22-C24 X7R 1210);
- new: U5 (`Timer:CD4541BM`), Q5, Q6 (`Transistor_FET:2N7002`), R25-R29, C29, C30, D7 (`Diode:BAT43W-V`), KiCad 10
  library symbols flattened into lib_symbols (lib_symbols holds only the symbols this sheet uses);
- layout (A4, the lead's block style): INPUT / ACC SENSE (J1, TVS1/2, D5, SW1, D4 as before; R8 / R25 divider
  added), TIMER U5 (U5 with its VDD / VSS pins drawn: VDD wired to the D7 / C8 block above it, VSS to GND below;
  R27 / C29 / R28 one row each at pins 1-3 joined on U5_TJ; A / B / Q-SELECT tied on one VDD_TMR wire; MODE and
  AR to GND; R26 into MR; R29 and D6 forming HOLD_G), P-FET SWITCH (Q1, R14 || C30, R15, Q5 on DRV), STATUS / LED /
  PI 12 V (Q6, R21, J5, J4, D3, R3), BUCK 5.1 V and USB (positions unchanged); one header and one short note per
  block, no values in the notes;
- PWR_FLAGs only on nets no power-output pin drives: BATT, GND (J1), VOUT (Q1 drain), +5V1 (L1), VDD_TMR (D7).

Uses 03's layout engine (03 / 04 imported: label-stub wiring, fields from SPEC 6/7, seeded uuid5, grid /
wire / connectivity-vs-SPEC 7 / overlap / A4 frame checks before writing). tools/check_netlist.py then checks the
KiCad netlist export against SPEC 7 independently (`pdm run verify-sch`).

Guards: refuses if KiCad's lock file exists. Accepts two states: (1) pre-edit: the sheet is byte-identical to what
06 wrote (SHA-256 below; 07 never ran); (2) applied: the sheet equals what this script writes ("already applied").
Anything else stops. SPEC 7 must hold exactly the parts this script places, with U5 / C8 / D7 on VDD_TMR. After the
build: every surviving part keeps its symbol uuid, no removed part or net remains, lib_symbols holds exactly the
expected symbols. Backup to pi_power_board-backups/ first; CRLF kept.
"""
import datetime
import hashlib
import importlib.util
import pathlib
import shutil
import sys

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import check_netlist  # noqa: E402
import sexpr  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


s04 = _load('post_sch_04', TOOLS / 'post_sch' / '04_d4_sw1_diode.py')
s03 = s04.s03
P = s03.P

SHEET, LOCK, BACKUPS, ROOT, STEM = s03.SHEET, s03.LOCK, s03.BACKUPS, s03.ROOT, s03.STEM
PRE_SHA256 = '11735be7cef1077e058f1b105d31f7da96fcd04ae8d4da59231e6079f50a160c'   # the sheet as 06 wrote it
EOL = '\r\n'
GND = s03.GND

SURVIVING = ('J1 J2 J4 J5 SW1 Q1 U8 L1 TVS1 TVS2 D3 D4 D5 D6 R3 R8 R14 R15 R16 R17 R18 R21 C8 C15 C17 C18 C19 C20 '
             'C22 C23 C24').split()
NEW = ('U5 Q5 Q6 R25 R26 R27 R28 R29 C29 C30 D7').split()
REMOVED = ('U1 R4 R5 R9 R23 R24 C5 C27 C28').split()
REMOVED_NETS = ('REF', 'C5_T', 'D6_A')
TMR_NET = 'VDD_TMR'
TMR_PINS = {'U5': ('9', '12', '13', '14'), 'C8': ('1',), 'D7': ('1',)}

# lib_id per symbol kind: only the symbols this sheet uses (03's LIB is replaced)
LIB = {
    'R': 'Device:R_US', 'C': 'Device:C', 'L': 'Device:L', 'D': 'Diode:1N4148W', 'TVS': 'Device:D_Zener',
    'LED': 'Device:LED', 'BAS': 'Diode:BAS21', 'SCH': 'Diode:BAT43W-V', 'PMOS': 'Transistor_FET:Q_PMOS_GDS',
    'NMOS': 'Transistor_FET:2N7002', 'TMR': 'Timer:CD4541BM', 'BUCK': 'Regulator_Switching:TPS54336ADDA',
    'USB': 'Connector:USB3_A_Stacked', 'T2': 'Connector:Screw_Terminal_01x02',
    'T3': 'Connector:Screw_Terminal_01x03', 'SW': 'Switch:SW_Nidec_CAS-120A1', 'GND': 'power:GND',
    'FLAG': 'power:PWR_FLAG',
}
MAKERS = {'CD4541BM96': 'Texas Instruments', '2N7002BK,215': 'Nexperia', 'BAT43W-E3-08': 'Vishay',
          'C0805C103F5GACTU': 'KEMET', 'GMC31X7R106K50NT': 'Cal-Chip Electronics',
          'GMC32X7R476K10NT': 'Cal-Chip Electronics'}

# ------------------------------------------------------------------------------------------------- layout
# A4, grid units (03: G = 50 mil). Top row: input / ACC sense, timer U5, P-FET switch (right), status / LED / Pi
# 12 V (right, below the switch). Bottom row: buck, USB (unchanged from 03).
U5_X, U5_Y = 104, 46
ROW_X, ROWS = 80, (19, 26, 33)                     # R27 / C29 / R28 rows, left of U5 pins 1-3
RISER_X = (94, 92, 90)                             # vertical wires from U5 pins 1 / 2 / 3 up to their rows
TJ_X = 70                                          # the U5_TJ wire joining the row ends
TIE_X = 94                                         # A / B / Q-SELECT tie
RAIL_Y = 22                                        # VDD_TMR rail above U5 (D7, C8)
FLAG_X = 100                                       # VDD_TMR PWR_FLAG on the rail's left end

PARTS = [
    # Input / ACC sense (03 / 04 positions) + the ACC_G divider
    P('J1', 'T3', 14, 30, 180, fields=((2, -6.5), (6, -5))),
    P('TVS1', 'TVS', 30, 38, 270), P('TVS2', 'TVS', 42, 38, 270),
    P('D5', 'D', 30, 52, 180, fields='above'),
    P('SW1', 'SW', 30, 62, fields='below'),
    P('D4', 'D', 54, 64, 180, fields='below'),
    P('R8', 'R', 62, 46), P('R25', 'R', 62, 55),
    # Timer U5
    P('U5', 'TMR', U5_X, U5_Y, fields=((-6, -13), (8, -13))),
    P('R27', 'R', ROW_X, ROWS[0], 270, fields='updown'),
    P('C29', 'C', ROW_X, ROWS[1], 270, fields='updown'),
    P('R28', 'R', ROW_X, ROWS[2], 270, fields='updown'),
    P('C8', 'C', 112, RAIL_Y + 3),
    P('D7', 'SCH', 119, RAIL_Y, fields='above'),
    P('R26', 'R', 82, 52, 90, fields='updown'),
    P('R29', 'R', 124, 46, 90, fields='updown'),
    P('D6', 'BAS', 126, 56, 180, fields='below'),
    # P-FET switch
    P('C30', 'C', 158, 30, fields='left'),
    P('R14', 'R', 172, 30, fields='left'),
    P('Q1', 'PMOS', 172, 41, 270, fields='below'),
    P('R15', 'R', 182, 33, 90, fields='updown'),
    P('Q5', 'NMOS', 200, 42),
    # Status / LED / Pi 12 V
    P('Q6', 'NMOS', 152, 66),
    P('R21', 'R', 166, 60, 90, fields='updown'),
    P('J4', 'T2', 212, 58, fields='below'),
    P('J5', 'T2', 184, 66, 180, fields='below'),
    P('D3', 'LED', 220, 74, 90, fields='left'), P('R3', 'R', 220, 85, fields='left'),
    # Buck 5.1 V (03 positions)
    P('U8', 'BUCK', 60, 106, fields=((0, -10), (0, -8.5))),
    P('C15', 'C', 14, 100), P('C17', 'C', 29, 100),
    P('C19', 'C', 14, 122), P('R18', 'R', 32, 120), P('C20', 'C', 32, 130),
    P('C18', 'C', 84, 100), P('L1', 'L', 90, 114, 90, fields='updown'),
    P('R16', 'R', 104, 104), P('R17', 'R', 104, 113),
    P('C22', 'C', 56, 132), P('C23', 'C', 74, 132), P('C24', 'C', 92, 132),
    # USB (03 positions)
    P('J2', 'USB', 136, 104, unit=1, fields=((0, -16), (0, -14.5))),
    P('J2', 'USB', 170, 104, unit=2, fields=((0, -16), (0, -14.5))),
]

LINKS = [
    ('SW1_C', ['SW1.1', 'D4.2'], (35, 64), 0),
    ('ACC_G', ['R8.2', 'R25.1'], (62, 51), 0),
    # U5 oscillator: each pin up its riser to its row; the row ends joined on U5_TJ
    ('U5_RTC', ['U5.1', (RISER_X[0], 38), (RISER_X[0], ROWS[0]), 'R27.1'], (85, ROWS[0]), 0),
    ('U5_CTC', ['U5.2', (RISER_X[1], 40), (RISER_X[1], ROWS[1]), 'C29.1'], (85, ROWS[1]), 0),
    ('U5_RS', ['U5.3', (RISER_X[2], 42), (RISER_X[2], ROWS[2]), 'R28.1'], (85, ROWS[2]), 0),
    ('U5_TJ', ['R27.2', (TJ_X, ROWS[0]), (TJ_X, ROWS[2]), 'R28.2'], (TJ_X, 30), 180),
    ('U5_TJ', ['C29.2', (TJ_X, ROWS[1])], None, 0),
    # U5 tied inputs and MR
    (TMR_NET, ['U5.13', (TIE_X, 46), (TIE_X, 50), 'U5.9'], (TIE_X, 50), 180),
    (TMR_NET, ['U5.12', (TIE_X, 48)], None, 0),
    ('U5_MR', ['R26.2', 'U5.6'], (88, 52), 0),
    # U5 supply: VDD up to the D7 / C8 rail
    (TMR_NET, ['U5.14', (U5_X, RAIL_Y), 'C8.1', 'D7.1'], None, 0),
    (TMR_NET, [(U5_X, RAIL_Y), (FLAG_X, RAIL_Y)], None, 0),
    # hold OR
    ('U5_OUT', ['U5.8', 'R29.1'], (114, 46), 0),
    ('HOLD_G', ['R29.2', (129, 46), 'D6.3'], None, 0),
    ('HOLD_G', [(129, 46), (132, 46)], (132, 46), 0),
    # P-FET switch: R14 || C30 from BATT to Q1_G; R15 to DRV; Q5 drain on DRV
    ('BATT', ['C30.1', 'R14.1'], None, 0),
    ('Q1_G', ['C30.2', 'R14.2'], None, 0),
    ('Q1_G', ['R14.2', 'Q1.1'], None, 0),
    ('Q1_G', ['R14.2', 'R15.1'], (174, 33), 0),
    ('DRV', ['R15.2', (202, 33), 'Q5.3'], (188, 33), 0),
    # status: Q6 drain to R21
    ('STAT_O', ['Q6.3', (154, 60), 'R21.1'], (155, 60), 0),
    ('D3_K', ['D3.1', 'R3.1'], (220, 80), 180),
    # buck / USB (03)
    ('U8_CRC', ['R18.2', 'C20.1'], (32, 125), 0),
    ('U8_FB', ['R16.2', 'R17.1'], (104, 109), 0),
    (GND, ['U8.4', 'U8.9'], None, 0),
    ('USB1_D', ['J2.2', 'J2.3'], None, 0),
    ('USB2_D', ['J2/2.11', 'J2/2.12'], None, 0),
    (GND, ['J2.SH', 'J2.7', 'J2.4'], None, 0),
    (GND, ['J2/2.SH', 'J2/2.16', 'J2/2.13'], None, 0),
]
# Pins on a link that still get their own stub and label
LINK_STUB = {'U8.4', 'J2.2', 'J2/2.11', 'J2.4', 'J2/2.13', 'R14.1'}
# Pin stub overrides: MODE's GND symbol clear of the A / B / Q-SELECT tie
PIN_OVERRIDES = {'U5': {'10': {'stub': 6}}}

FLAGS = [('BATT', 34, 28), (GND, 54, 28), ('VOUT', 210, 34), ('+5V1', 112, 128), (TMR_NET, FLAG_X, RAIL_Y - s03.STUB)]

HEADER, NOTE = s03.HEADER_FONT, s03.FONT
TEXTS = [
    ('INPUT / ACC SENSE', 10, 13, HEADER, True),
    ('Harness fuse; SW1 closed = key on', 10, 15.5, NOTE, False),
    ('TIMER U5', 66, 13, HEADER, True),
    ('ACC holds reset; key off: OUT low after the count; D7 + C8 hold VDD_TMR', 66, 15.5, NOTE, False),
    ('P-FET SWITCH', 142, 13, HEADER, True),
    ('HOLD_G high: Q5 pulls DRV low, Q1 on', 142, 15.5, NOTE, False),
    ('STATUS / LED / PI 12 V', 142, 52, HEADER, True),
    ('J5 low = ACC on (Pi pull-up)', 142, 54.5, NOTE, False),
    ('BUCK 5.1 V', 10, 82, HEADER, True),
    ('EN floats: enabled by its pull-up', 10, 84.5, NOTE, False),
    ('USB', 124, 82, HEADER, True),
    ('D+ shorted to D- per port (BC1.2)', 124, 84.5, NOTE, False),
]


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def install():
    """Point 03's engine at this layout."""
    for p in PARTS:
        p.pins.update(PIN_OVERRIDES.get(p.ref, {}))
    s03.LIB.clear()
    s03.LIB.update(LIB)
    s03.LINK_STUB.clear()
    s03.LINK_STUB.update(LINK_STUB)
    s03.FLAGS[:] = FLAGS
    s03.TEXTS[:] = TEXTS
    for mpn, maker in MAKERS.items():
        s03.MANUFACTURER.setdefault(mpn, maker)


def check_spec(spec):
    if set(spec) != set(SURVIVING) | set(NEW) or set(spec) & set(REMOVED):
        raise SystemExit(f'SPEC 7 refs differ from this script: missing {sorted((set(SURVIVING) | set(NEW)) - set(spec))}'
                         f', extra {sorted(set(spec) - set(SURVIVING) - set(NEW))}: stop')
    for ref, pins in TMR_PINS.items():
        if any(spec[ref]['pins'].get(p) != TMR_NET for p in pins):
            raise SystemExit(f'SPEC 7 {ref}: pins {pins} not on {TMR_NET}: not the D7 / C8 state: stop')
    nets = {n for s in spec.values() for n in s['pins'].values()}
    if nets & set(REMOVED_NETS):
        raise SystemExit(f'SPEC 7 still names {sorted(nets & set(REMOVED_NETS))}: stop')


def check_result(old, out):
    blocks = s03.top_level_blocks(out)
    new = s03.read_old(out, blocks)
    errs = []
    for ref in SURVIVING:
        if sorted(v['uuid'] for v in old[ref]) != sorted(v['uuid'] for v in new.get(ref, [])):
            errs.append(f'{ref}: symbol uuid changed')
    errs += [f'{ref}: still drawn' for ref in REMOVED if ref in new]
    errs += [f'net label {n} remains' for n in REMOVED_NETS if f'(label "{n}"' in out]
    lib = next(out[a:b] for a, b in blocks if out.startswith('(lib_symbols', a))
    have = sorted(n[1] for n in sexpr.find_all(sexpr.parse(lib), 'symbol'))
    if have != sorted(set(LIB.values())):
        errs.append(f'lib_symbols {have} != {sorted(set(LIB.values()))}')
    if errs:
        raise SystemExit('result check failed:\n  ' + '\n  '.join(errs))


def main(argv):
    dry = '--dry-run' in argv
    if LOCK.exists():
        raise SystemExit(f'{LOCK.name} exists: close the schematic in KiCad first')
    md = check_netlist.SPEC.read_text(encoding='utf-8')
    spec, parts_table = check_netlist.parse_netlist_table(md), check_netlist.parse_parts_table(md)
    check_spec(spec)
    placed = {p.ref for p in PARTS}
    if placed != set(spec):
        raise SystemExit(f'layout vs SPEC 7: missing {sorted(set(spec) - placed)}, extra {sorted(placed - set(spec))}')
    with open(SHEET, encoding='utf-8', newline='') as fh:
        src = fh.read()
    if '\r\n' not in src:
        raise SystemExit(f'{SHEET.name}: not CRLF: unexpected state')
    text = src.replace('\r\n', '\n')
    old = s03.read_old(text, s03.top_level_blocks(text))

    install()
    out = s04.with_title(s04.build(text, spec, parts_table, (PARTS, LINKS)))
    if sha256(src) != PRE_SHA256:
        if out.replace('\n', EOL) == src:
            print(f'{SHEET.name}: already applied (CD4541B counter timer, SPEC 7); nothing changed')
            return
        raise SystemExit(f'{SHEET.name}: neither the 06 sheet (SHA-256 {PRE_SHA256[:12]}...) nor the 08 result: '
                         'stop; edit by hand or with a new script')
    missing = [r for r in SURVIVING + REMOVED if r not in old]
    if missing:
        raise SystemExit(f'pre-edit sheet lacks {missing}: unexpected state')
    check_result(old, out)
    if dry:
        print('dry run: layout, connectivity and result checks passed; nothing written')
        return
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_sch'
    shutil.copy2(SHEET, backup)
    with open(SHEET, 'w', encoding='utf-8', newline='') as fh:
        fh.write(out.replace('\n', EOL))
    print(f'backup {backup.relative_to(ROOT)}')
    print(f'{SHEET.name}: removed {len(REMOVED)} parts (U1 3 units); {len(SURVIVING)} kept (uuids reused), '
          f'{len(NEW)} new; {len(spec)} parts on the sheet')


if __name__ == '__main__':
    main(sys.argv)
