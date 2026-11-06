"""Post-schematic edit 09 (2026-11-05): U5 supplied from VOUT through R30 with the D7 zener clamp (SPEC 7).

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/09_u5_vout_supply.py [--dry-run]

What and why (project lead decision 2026-11-05; SPEC header note "U5 from VOUT", SPEC 2-4, SPEC 6 Parts, SPEC 7;
DECISIONS 2026-11-05): with U5 on +5V1 through the BAT43W and a 10 uF hold-up, a hard USB short kept U8 in hiccup,
U5 sat below its operating minimum with its output high, and Q5 held Q1 on with the key off (sim OVL). U5 now runs
from VOUT, which exists only while Q1 is on: VOUT -> R30 -> VDD_TMR, D7 zener VDD_TMR -> GND (clamp), R31
VDD_TMR -> GND (bleed: holds U5 unpowered against Q1's off-state leakage when parked), C8 decoupling.

- D7 keeps its ref, symbol uuid, pin uuids and SOD-123 footprint; its symbol becomes `Device:D_Zener` (1 K, 2 A,
  the same pin numbers), value BZT52C5V1; pin 2 moves from +5V1 to GND;
- C8 10 uF 1206 -> 1 uF 0805 (fields from SPEC 6 / 7);
- new R30 (R_1206, VOUT -> VDD_TMR) and R31 (R_0805, VDD_TMR -> GND); `Diode:BAT43W-V` leaves lib_symbols;
- layout: the TIMER U5 block keeps every position of 08; the VDD_TMR rail above U5 now carries, left to right,
  U5 VDD, C8, D7, R31 (each to its own GND symbol) and R30 (down to a VOUT label): one supply block on U5's VDD.
  The PWR_FLAG on VDD_TMR stays (no power-output pin drives it). The block note no longer names D7 / C8.

Uses 03's layout engine through 08's layout (imported; seeded uuid5 for the new items, label-stub wiring, fields
from SPEC 6 / 7, grid / wire / connectivity-vs-SPEC 7 / overlap / A4 frame checks before writing).
tools/check_netlist.py then checks the KiCad netlist export against SPEC 7 independently (`pdm run verify-sch`).

Guards: refuses if KiCad's lock file exists. Accepts two states: (1) pre-edit: the sheet is byte-identical to what
08 wrote (SHA-256 below); (2) applied: the sheet equals what this script writes ("already applied"). Anything else
stops. SPEC 7 must hold exactly the parts this script places, with the VDD_TMR pins below. After the build: every
08 part keeps its symbol uuid (D7 included), lib_symbols holds exactly the expected symbols, D7 is a zener. Backup to
pi_power_board-backups/ first; CRLF kept.
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


s08 = _load('post_sch_08', TOOLS / 'post_sch' / '08_cd4541_timer.py')
s04, s03 = s08.s04, s08.s03
P = s03.P

SHEET, LOCK, BACKUPS, ROOT, STEM = s03.SHEET, s03.LOCK, s03.BACKUPS, s03.ROOT, s03.STEM
PRE_SHA256 = 'e2ad415c087d18c114ed24a53ab6b5aa21fa7aff12d95a0a1bd64a79c7afc265'   # the sheet as 08 wrote it
EOL = '\r\n'
GND = s03.GND
TMR_NET = s08.TMR_NET

KEPT = s08.SURVIVING + s08.NEW                      # every 08 part keeps its uuid (D7 included)
NEW = ('R30', 'R31')
ZENER = 'D7'
ZENER_LIB = 'Device:D_Zener'
DROPPED_LIB = 'Diode:BAT43W-V'
EXPECT_PINS = {'U5': {'9': TMR_NET, '12': TMR_NET, '13': TMR_NET, '14': TMR_NET},
               'C8': {'1': TMR_NET, '2': GND}, 'D7': {'1': TMR_NET, '2': GND},
               'R31': {'1': TMR_NET, '2': GND}, 'R30': {'1': 'VOUT', '2': TMR_NET}}

LIB = {k: v for k, v in s08.LIB.items() if k != 'SCH'}    # D7 uses 'TVS' (Device:D_Zener), as TVS1 / TVS2
MAKERS = dict(s08.MAKERS)
MAKERS.update({'BZT52C5V1-E3-08': 'Vishay', 'GMC21X7R105K50NT': 'Cal-Chip Electronics'})

# ------------------------------------------------------------------------------------------------- layout
# 08's layout; the VDD_TMR rail (y RAIL_Y) runs right from U5 VDD over C8, D7, R31 to R30. Grid units.
RAIL_Y = s08.RAIL_Y
SUPPLY_X = {'C8': 108, 'D7': 120, 'R31': 132, 'R30': 143}   # value text width apart
HANG_Y = RAIL_Y + 3                                 # 2-pin parts hang from the rail: pin on the rail, centre 3 below
SUPPLY_PARTS = [
    P('C8', 'C', SUPPLY_X['C8'], HANG_Y),
    P('D7', 'TVS', SUPPLY_X['D7'], HANG_Y, 270),    # K (pin 1) up on the rail, A down to GND
    P('R31', 'R', SUPPLY_X['R31'], HANG_Y),
    P('R30', 'R', SUPPLY_X['R30'], HANG_Y, 180,     # pin 2 up on the rail, pin 1 down to the VOUT label,
      pins={'1': {'angle': 180}}),                # its text to the left, clear of the P-FET block
]
PARTS = [p for p in s08.PARTS if p.ref not in ('C8', 'D7')] + SUPPLY_PARTS
SUPPLY_LINK = (TMR_NET, ['U5.14', (s08.U5_X, RAIL_Y), 'C8.1', 'D7.1', 'R31.1', 'R30.2'], None, 0)
OLD_SUPPLY_LINK = (TMR_NET, ['U5.14', (s08.U5_X, RAIL_Y), 'C8.1', 'D7.1'], None, 0)
if s08.LINKS.count(OLD_SUPPLY_LINK) != 1:
    raise SystemExit('08 layout: VDD_TMR supply link not found once: unexpected state')
LINKS = [SUPPLY_LINK if lk == OLD_SUPPLY_LINK else lk for lk in s08.LINKS]

OLD_NOTE = 'ACC holds reset; key off: OUT low after the count; D7 + C8 hold VDD_TMR'
NEW_NOTE = 'ACC holds reset; key off: OUT low after the count; U5 runs from VOUT'
if sum(t[0] == OLD_NOTE for t in s08.TEXTS) != 1:
    raise SystemExit('08 layout: timer note not found once: unexpected state')
TEXTS = [(NEW_NOTE,) + t[1:] if t[0] == OLD_NOTE else t for t in s08.TEXTS]


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def install():
    """Point 03's engine at this layout."""
    for p in PARTS:
        p.pins.update(s08.PIN_OVERRIDES.get(p.ref, {}))
    s03.LIB.clear()
    s03.LIB.update(LIB)
    s03.LINK_STUB.clear()
    s03.LINK_STUB.update(s08.LINK_STUB)
    s03.FLAGS[:] = s08.FLAGS
    s03.TEXTS[:] = TEXTS
    for mpn, maker in MAKERS.items():
        s03.MANUFACTURER.setdefault(mpn, maker)


def check_spec(spec):
    want = set(KEPT) | set(NEW)
    if set(spec) != want:
        raise SystemExit(f'SPEC 7 refs differ from this script: missing {sorted(want - set(spec))}, extra '
                         f'{sorted(set(spec) - want)}: stop')
    for ref, pins in EXPECT_PINS.items():
        bad = {p: spec[ref]['pins'].get(p) for p, n in pins.items() if spec[ref]['pins'].get(p) != n}
        if bad:
            raise SystemExit(f'SPEC 7 {ref}: {bad} not as this script expects {pins}: stop')


def check_result(old, out):
    blocks = s03.top_level_blocks(out)
    new = s03.read_old(out, blocks)
    errs = []
    for ref in KEPT:
        if sorted(v['uuid'] for v in old[ref]) != sorted(v['uuid'] for v in new.get(ref, [])):
            errs.append(f'{ref}: symbol uuid changed')
    errs += [f'{ref}: not drawn' for ref in NEW if ref not in new]
    if [v['lib_id'] for v in new.get(ZENER, [])] != [ZENER_LIB]:
        errs.append(f'{ZENER}: lib_id {[v["lib_id"] for v in new.get(ZENER, [])]} != {ZENER_LIB}')
    if sorted(old[ZENER][0]['pins'].values()) != sorted(new[ZENER][0]['pins'].values()):
        errs.append(f'{ZENER}: pin uuids changed')
    lib = next(out[a:b] for a, b in blocks if out.startswith('(lib_symbols', a))
    have = sorted(n[1] for n in sexpr.find_all(sexpr.parse(lib), 'symbol'))
    if have != sorted(set(LIB.values())) or DROPPED_LIB in have:
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
            print(f'{SHEET.name}: already applied (U5 from VOUT: R30, D7 zener, R31, C8; SPEC 7); nothing changed')
            return
        raise SystemExit(f'{SHEET.name}: neither the 08 sheet (SHA-256 {PRE_SHA256[:12]}...) nor the 09 result: '
                         'stop; edit by hand or with a new script')
    missing = [r for r in KEPT if r not in old]
    extra = [r for r in NEW if r in old]
    if missing or extra:
        raise SystemExit(f'pre-edit sheet lacks {missing} / already has {extra}: unexpected state')
    if [v['lib_id'] for v in old[ZENER]] != [DROPPED_LIB]:
        raise SystemExit(f'pre-edit {ZENER} is not {DROPPED_LIB}: unexpected state')
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
    print(f'{SHEET.name}: D7 -> zener (uuid kept), C8 1 uF 0805, {len(NEW)} new ({", ".join(NEW)}); '
          f'{len(spec)} parts on the sheet')


if __name__ == '__main__':
    main(sys.argv)
