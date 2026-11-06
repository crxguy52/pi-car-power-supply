"""Post-schematic edit 05 (2026-11-05, project lead): U1's power unit as a proper block with C8.

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/05_u1_power_block.py [--dry-run]

What and why (project lead review of the schematic: "U1 is fine as 3 units, but the power unit's V+ and GND are
drawn as bare floating pins; make it a proper block"; SPEC 7 "U1 symbol"; DECISIONS 2026-11-05 "U1 power block"):
the KiCad 10 `Comparator:LM2903` power unit (unit C) is two pins with no body graphics. KiCad 10 has no variant of
this part whose power unit has a body (every dual comparator / op-amp power unit in the stock libraries is bare
pins), so the project gets its own symbol library:

- `lib/pi_power_board.kicad_sym` (nickname `pipwr`, the footprint library's nickname; `sym-lib-table` added) holds
  `LM2903`: a copy of the stock `Comparator:LM2903` with unit C given a rectangle body. Units A and B, every pin
  number, pin position, pin type and every property are the stock ones. Unit C: pin length shortened so the pins
  end where the stock ones do and start on the body edge; pin 4 renamed V- -> GND (SLCS005AH table 4-1: 4 GND,
  8 VCC; the lead's wording "V+ and GND"); pin 8 keeps the KiCad name V+.
- U1 (all three units) points at `pipwr:LM2903`; the embedded lib_symbols entry is the library symbol (KiCad's
  "symbol differs from library" ERC check then passes). U1 keeps its symbol and pin uuids and its unit / pin
  numbering (the board links its footprint by symbol uuid).
- Block: C8 moves next to U1C (4 grid units right of its body). U1 pin 8 and C8 pin 1 share one `BATT` wire with a
  label; U1 pin 4 has its stub and GND symbol, and C8 pin 2 joins that GND point by a wire (one GND symbol for the
  block). Everything stays on the 50 mil grid.

Uses 03's layout engine with 04's PARTS / LINKS (04 imported), so every other item keeps its bytes. Side effect:
the block has one GND symbol fewer, so the hidden power references (#PWRnn, numbered in build order) after it
shift by one; their uuids and positions don't change.

Guards: refuses if KiCad's lock file exists. Accepts two states: (1) pre-edit: the sheet is byte-identical to what
04 wrote (SHA-256 below) and neither the symbol library nor sym-lib-table exists (or each already holds exactly
what this script writes); (2) applied: sheet, library and table equal what this script writes ("already
applied"). Anything else stops. The stock unit C is checked to be the bare two-pin unit this script expects.
Before writing, 03's checks run (grid, wires, connectivity vs SPEC 7, overlaps, A4 frame), then a change-set check:
only U1, C8, the block's wires / label / GND symbol and the U1 lib_symbols entry change. Backup of the sheet to
pi_power_board-backups/ before writing; CRLF kept (library and table written with CRLF, as KiCad's own).
"""
import copy
import datetime
import hashlib
import importlib.util
import pathlib
import re
import shutil
import sys

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import check_netlist  # noqa: E402
import sch_lib  # noqa: E402
import sexpr  # noqa: E402
from sexpr import Sym  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


s04 = _load('post_sch_04', TOOLS / 'post_sch' / '04_d4_sw1_diode.py')
s03 = s04.s03

SHEET, LOCK, BACKUPS, ROOT, STEM = s03.SHEET, s03.LOCK, s03.BACKUPS, s03.ROOT, s03.STEM
PRE_SHA256 = '5a4c1b550cc620b13f4953d090e52520f08829f8876c4454f7d2fe7f42e38404'   # the sheet as 04 wrote it
EOL = '\r\n'

# Project symbol library
LIB_NICK = 'pipwr'
SYM_LIB = ROOT / 'lib' / f'{STEM}.kicad_sym'
SYM_TABLE = ROOT / 'sym-lib-table'
SYM_TABLE_TEXT = ('(sym_lib_table\n\t(version 7)\n'
                  f'\t(lib (name "{LIB_NICK}")(type "KiCad")(uri "${{KIPRJMOD}}/lib/{STEM}.kicad_sym")(options "")'
                  '(descr "Pi power HAT project symbols (tools/post_sch/05_u1_power_block.py)"))\n)\n')
LIB_HEADER = ['(kicad_symbol_lib', '\t(version 20251024)', '\t(generator "kicad_symbol_editor")',
              '\t(generator_version "10.0")']
STOCK_ID = 'Comparator:LM2903'
SYM_NAME = 'LM2903'
NEW_ID = f'{LIB_NICK}:{SYM_NAME}'
POWER_UNIT = f'{SYM_NAME}_3_1'

# Power unit geometry, library mm (Y up). Stock pins: x PIN_X, ends at +/- PIN_END_Y, length STOCK_PIN_LEN.
PIN_X = -2.54
PIN_END_Y = 7.62
STOCK_PIN_LEN = 3.81
PIN_LEN = 2.54                         # 100 mil: the pins start on the body edge
BODY_HALF_W = 2.54                     # body centred on the pin line
BODY_HALF_H = PIN_END_Y - PIN_LEN
BODY_STROKE = 0.254                    # the stock units' body stroke
STOCK_PINS = {'4': ('V-', -PIN_END_Y, 90), '8': ('V+', PIN_END_Y, 270)}   # number: (name, end y, angle)
NEW_PIN_NAMES = {'4': 'GND', '8': 'V+'}

# Layout (grid units, as 03 / 04)
U1C_PLACE = dict(ref='U1', kind='CMP', x=162, y=34, unit=3, fields='left')
C8_PLACE = dict(ref='C8', kind='C', x=166, y=34)
BATT_LINK = ('BATT', ['U1/3.8', (160, 26), (166, 26), 'C8.1'], (161, 26), 0)
GND_LINK = ('GND', ['C8.2', (166, 42), (160, 42)], None, 0)       # to U1 pin 4's stub tip and GND symbol
OLD_BATT_LINK_NET, OLD_BATT_LINK_FIRST = 'BATT', 'U1/3.8'
BLOCK_REFS = {'U1', 'C8'}
# Changed placed items (power symbols compared without their #PWR reference)
EXPECTED_REMOVED_KINDS = {'label': 1, 'symbol': 5, 'wire': 5}     # U1 x3, C8, C8's GND; old BATT link + C8 stub
EXPECTED_ADDED_KINDS = {'label': 1, 'symbol': 4, 'wire': 6}       # U1 x3, C8; BATT link (split) + GND link
POWER_REF = re.compile(r'(\(property "Reference" |\(reference )"#(PWR|FLG)\d+"')


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ------------------------------------------------------------------------------------------------ library

def project_symbol():
    """The project LM2903 (library form, named SYM_NAME): stock symbol, unit C with a body."""
    node = sch_lib.flat_symbol(STOCK_ID)
    node[1] = SYM_NAME
    unit = next((s for s in sexpr.find_all(node, 'symbol') if s[1] == POWER_UNIT), None)
    if unit is None:
        raise SystemExit(f'{STOCK_ID}: no {POWER_UNIT}: the KiCad library changed, stop')
    graphics = [x for x in unit if isinstance(x, list) and x and x[0] != 'pin']
    pins = sexpr.find_all(unit, 'pin')
    got = {sexpr.find(p, 'number')[1]: (sexpr.find(p, 'name')[1], float(sexpr.find(p, 'at')[2]),
                                        float(sexpr.find(p, 'at')[3]), float(sexpr.find(p, 'at')[1]),
                                        float(sexpr.find(p, 'length')[1])) for p in pins}
    want = {n: (nm, y, a, PIN_X, STOCK_PIN_LEN) for n, (nm, y, a) in STOCK_PINS.items()}
    if graphics or got != want:
        raise SystemExit(f'{STOCK_ID} unit C is not the bare two-pin unit this script expects: {got}: stop')
    for p in pins:
        sexpr.find(p, 'length')[1] = Sym(sexpr.fmt_num(PIN_LEN))
        sexpr.find(p, 'name')[1] = NEW_PIN_NAMES[sexpr.find(p, 'number')[1]]
    x1, x2 = PIN_X - BODY_HALF_W, PIN_X + BODY_HALF_W
    rect = [Sym('rectangle'), [Sym('start'), Sym(sexpr.fmt_num(x1)), Sym(sexpr.fmt_num(BODY_HALF_H))],
            [Sym('end'), Sym(sexpr.fmt_num(x2)), Sym(sexpr.fmt_num(-BODY_HALF_H))],
            [Sym('stroke'), [Sym('width'), Sym(sexpr.fmt_num(BODY_STROKE))], [Sym('type'), Sym('default')]],
            [Sym('fill'), [Sym('type'), Sym('background')]]]
    unit.insert(2, rect)                                    # after the name, before the pins
    return node


def library_text(node):
    return EOL.join(LIB_HEADER + [sexpr.dump(node, 1).replace('\n', EOL), ')']) + EOL


def read_or_none(path):
    if not path.exists():
        return None
    with open(path, encoding='utf-8', newline='') as fh:
        return fh.read()


# ------------------------------------------------------------------------------------------------ sheet

def layout():
    """04's PARTS / LINKS with the U1C / C8 block replaced."""
    parts, links = s04.s03.PARTS, s04.s03.LINKS
    base_parts = list(parts) + [s03.P(*s04.D4_PLACE, fields=s04.D4_FIELDS)]
    base_links = list(links) + [s04.D4_LINK]
    idx_u = [i for i, p in enumerate(base_parts) if p.key == 'U1/3']
    idx_c = [i for i, p in enumerate(base_parts) if p.key == 'C8']
    idx_l = [i for i, l in enumerate(base_links) if l[0] == OLD_BATT_LINK_NET and l[1][0] == OLD_BATT_LINK_FIRST]
    if len(idx_u) != 1 or len(idx_c) != 1 or len(idx_l) != 1:
        raise SystemExit('03 / 04 layout: U1C, C8 or the U1C BATT link not found once: stop')
    base_parts[idx_u[0]] = s03.P(**U1C_PLACE)
    base_parts[idx_c[0]] = s03.P(**C8_PLACE)
    base_links[idx_l[0]] = BATT_LINK
    return base_parts, base_links + [GND_LINK]


def install_symbol(node):
    """03's engine: CMP parts use pipwr:LM2903, served from the project symbol (cache form: named NEW_ID)."""
    cached = copy.deepcopy(node)
    cached[1] = NEW_ID
    stock_flat = sch_lib.flat_symbol
    s03.sch_lib.flat_symbol = lambda lib_id: copy.deepcopy(cached) if lib_id == NEW_ID else stock_flat(lib_id)
    s03.LIB['CMP'] = NEW_ID


def norm_power(blk):
    return POWER_REF.sub(r'\1"#\2"', blk)


def check_changes(before, after):
    old = {norm_power(b): k for b, k in s04.item_blocks(before).items()}
    new = {norm_power(b): k for b, k in s04.item_blocks(after).items()}
    removed = [(b, k) for b, k in old.items() if b not in new]
    added = [(b, k) for b, k in new.items() if b not in old]
    count = lambda items: {k: [x[1] for x in items].count(k) for k in sorted({x[1] for x in items})}  # noqa: E731
    if count(removed) != EXPECTED_REMOVED_KINDS or count(added) != EXPECTED_ADDED_KINDS:
        raise SystemExit(f'change set removed {count(removed)}, added {count(added)}; expected '
                         f'{EXPECTED_REMOVED_KINDS} / {EXPECTED_ADDED_KINDS}: stop')
    for b, k in removed + added:
        if k == 'symbol':
            ref = s03.prop(sexpr.parse(b), 'Reference')
            if ref not in BLOCK_REFS and not ref.startswith('#PWR'):
                raise SystemExit(f'symbol {ref} changed: only {sorted(BLOCK_REFS)} may: stop')

    def libs(text):
        blk = next(text[a:b] for a, b in s03.top_level_blocks(text) if text.startswith('(lib_symbols', a))
        return {n[1]: sexpr.dump(n) for n in sexpr.find_all(sexpr.parse(blk), 'symbol')}

    lo, ln = libs(before), libs(after)
    if set(lo) - set(ln) != {STOCK_ID} or set(ln) - set(lo) != {NEW_ID} or \
            any(lo[k] != ln[k] for k in set(lo) & set(ln)):
        raise SystemExit('lib_symbols: expected only Comparator:LM2903 -> pipwr:LM2903: stop')
    return count(removed), count(added)


def main(argv):
    dry = '--dry-run' in argv
    if LOCK.exists():
        raise SystemExit(f'{LOCK.name} exists: close the schematic in KiCad first')
    md = check_netlist.SPEC.read_text(encoding='utf-8')
    spec, parts_table = check_netlist.parse_netlist_table(md), check_netlist.parse_parts_table(md)
    if spec['U1']['pins'].get('8') != 'BATT' or spec['U1']['pins'].get('4') != s03.GND or \
            spec['C8']['pins'] != {'1': 'BATT', '2': s03.GND}:
        raise SystemExit('SPEC 7 U1 pins 4 / 8 or C8 are not the nets this script draws: stop')
    with open(SHEET, encoding='utf-8', newline='') as fh:
        src = fh.read()
    if '\r\n' not in src:
        raise SystemExit(f'{SHEET.name}: not CRLF: unexpected state')
    text = src.replace('\r\n', '\n')

    node = project_symbol()
    lib_want = library_text(node)
    lib_have, table_have = read_or_none(SYM_LIB), read_or_none(SYM_TABLE)
    table_want = SYM_TABLE_TEXT.replace('\n', EOL)
    for path, have, want in ((SYM_LIB, lib_have, lib_want), (SYM_TABLE, table_have, table_want)):
        if have is not None and have != want:
            raise SystemExit(f'{path.name} exists and differs from what 05 writes: stop')

    install_symbol(node)
    out = s04.with_title(s04.build(text, spec, parts_table, layout()))
    if sha256(src) != PRE_SHA256:
        if out.replace('\n', EOL) == src and lib_have == lib_want and table_have == table_want:
            print(f'{SHEET.name}: already applied (U1 power block, {NEW_ID}); nothing changed')
            return
        raise SystemExit(f'{SHEET.name}: neither the 04 sheet (SHA-256 {PRE_SHA256[:12]}...) nor the 05 result '
                         '(with its library and table): stop; edit by hand or with a new script')
    removed, added = check_changes(text, out)
    if dry:
        print(f'dry run: checks passed; would remove {removed}, add {added}; write {SYM_LIB.name}, '
              f'{SYM_TABLE.name}; nothing written')
        return
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_sch'
    shutil.copy2(SHEET, backup)
    for path, have, want in ((SYM_LIB, lib_have, lib_want), (SYM_TABLE, table_have, table_want)):
        if have is None:
            with open(path, 'w', encoding='utf-8', newline='') as fh:
                fh.write(want)
            print(f'wrote {path.relative_to(ROOT)}')
    with open(SHEET, 'w', encoding='utf-8', newline='') as fh:
        fh.write(out.replace('\n', EOL))
    print(f'backup {backup.relative_to(ROOT)}')
    print(f'{SHEET.name}: U1 -> {NEW_ID} (power unit with body), C8 block; removed {removed}, added {added}')


if __name__ == '__main__':
    main(sys.argv)
