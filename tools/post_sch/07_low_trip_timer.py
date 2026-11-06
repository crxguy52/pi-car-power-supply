"""Post-schematic edit 07 (2026-11-05, staff review of 06): low-trip 45 s timer, C28 removed.

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/07_low_trip_timer.py [--dry-run]

What and why (staff review of `06_timer_45s.py`; SPEC 3 "Delay-off timer", SPEC 6 Parts rows R4 / R5 / R23 / R24 /
C5, SPEC 7 rows R4, R5, R23, R24, C5, C27; DECISIONS 2026-11-05 "low-trip timer"; numbers in `tools/design_calc.py`
`timer()` / `recharge()`): the 06 timer met >= 45 s only if C5's insulation stayed >= 417 ohm.F hot, a figure the
GMC datasheet doesn't support (its X7R 125 C row repeats the 25 C row). MLCC insulation is an ohm x farad product,
so the capacitors discharge themselves with that time constant whatever the split; the delay is that time
constant times ln(V0 / V_trip). Lowering the trip from 0.314 x BATT to 0.094 x BATT doubles the log factor, so the
short stack needs >= 71 ohm.F hot (>= 710 ohm.F at 25 C with a 1/10 hot factor) and one capacitor goes:

- C28 removed (C5 + C27 = 2 x 10 uF stay on `C5_T`); R9 (4.7 Mohm, unchanged) moves onto C28's old position, so
  the C27-to-C28 wire becomes the C27-to-R9 wire.
- R4 1.8 Mohm -> 4.7 Mohm, R5 1.0 Mohm -> 510 kohm, R23 4.7 Mohm -> 10 Mohm (trip 0.094 / 0.136 x BATT; R23 also
  keeps Q1's off-state V_GS below the 06 values).
- R24 1 kohm -> 2.2 kohm: its key-on peak power at 16 V (0.11 W) sits inside the 0805 continuous rating.
- Timer note names the two capacitors.

Values come from SPEC 7 through 03's engine. Uses 03's layout engine with 06's PARTS / LINKS (06 imported, which
imports 05 / 04), so every other item of the sheet keeps its bytes. R4, R5, R23, R24, R9, C5, C27 keep their
symbol / pin uuids (board link).

Guards: refuses if KiCad's lock file exists. Accepts two states: (1) pre-edit: the sheet is byte-identical to what
06 wrote (SHA-256 below); (2) applied: the sheet equals what this script writes ("already applied"). Anything else
stops. SPEC 6 / 7 must hold the values this script expects. Before writing, 03's checks run (grid, wires,
connectivity vs SPEC 7, overlaps, A4 frame), then a change-set check: only R4, R5, R23, R24, R9, C28 (removed),
the `C5_T` wire / GND symbol of C28 and the timer note change; lib_symbols unchanged. Backup to
pi_power_board-backups/ first; CRLF kept.
"""
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
import sexpr  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


s06 = _load('post_sch_06', TOOLS / 'post_sch' / '06_timer_45s.py')
s05, s04, s03 = s06.s05, s06.s04, s06.s03

SHEET, LOCK, BACKUPS, ROOT, STEM = s03.SHEET, s03.LOCK, s03.BACKUPS, s03.ROOT, s03.STEM
PRE_SHA256 = '11735be7cef1077e058f1b105d31f7da96fcd04ae8d4da59231e6079f50a160c'   # the sheet as 06 wrote it
EOL = '\r\n'

TIMER_NET = 'C5_T'
DROPPED = 'C28'
KEPT_CAPS = ('C5', 'C27')
NEW_VALUES = {'R4': '4.7 MΩ 1 %', 'R5': '510 kΩ 1 %', 'R23': '10 MΩ 1 %', 'R24': '2.2 kΩ', 'R9': '4.7 MΩ 1 %'}
OLD_NOTE = s06.NEW_NOTE
NEW_NOTE = 'Key off: delay ~ R9 (C5 + C27) ln(V0 / REF) (SPEC 3)'

R9_X = s06.CAP_X[DROPPED]                          # R9 takes C28's place
ROW_Y, WIRE_Y = s06.ROW_Y, s06.WIRE_Y

CHANGED_REFS = {'R4', 'R5', 'R23', 'R24', 'R9', DROPPED}
# Changed placed items (power symbols compared without their #PWR reference), from the dry run.
# Removed: R4, R5, R23, R24 (value), R9 and its GND symbol at the old position, C28; R9's two old pin stubs and the
# C28-to-R9 wire; the junction at C28's pin; the timer note.
# Added: R4, R5, R23, R24, R9; the note. R9 reuses C28's stubs, GND symbol and the C27-to-C28 wire unchanged.
EXPECTED_REMOVED_KINDS = {'junction': 1, 'symbol': 7, 'text': 1, 'wire': 3}
EXPECTED_ADDED_KINDS = {'symbol': 5, 'text': 1}
POWER_REF = re.compile(r'(\(property "Reference" |\(reference )"#(PWR|FLG)\d+"')


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def layout():
    """06's PARTS / LINKS without C28; R9 on C28's position, linked from C27."""
    parts, links = s06.layout()
    idx_c28 = [i for i, p in enumerate(parts) if p.key == DROPPED]
    idx_r9 = [i for i, p in enumerate(parts) if p.key == 'R9']
    c27_x = s06.CAP_X['C27']
    old_c28_link = (TIMER_NET, [(c27_x, WIRE_Y), (R9_X, WIRE_Y), f'{DROPPED}.1'], None, 0)
    old_r9_link = (TIMER_NET, [(R9_X, WIRE_Y), (s06.R9_X, WIRE_Y), 'R9.1'], None, 0)
    idx_l = [i for i, lk in enumerate(links) if lk in (old_c28_link, old_r9_link)]
    if len(idx_c28) != 1 or len(idx_r9) != 1 or len(idx_l) != 2:
        raise SystemExit('06 layout: C28, R9 or their C5_T links not found once where expected: stop')
    parts[idx_r9[0]] = s03.P('R9', 'R', R9_X, ROW_Y)
    del parts[idx_c28[0]]
    first = min(idx_l)
    links[first:first + 2] = [(TIMER_NET, [(c27_x, WIRE_Y), (R9_X, WIRE_Y), 'R9.1'], None, 0)]
    return parts, links


def set_note():
    s06.set_note()
    idx = [i for i, t in enumerate(s03.TEXTS) if t[0] in (OLD_NOTE, NEW_NOTE)]
    if len(idx) != 1:
        raise SystemExit('03 TEXTS: the timer note not found once: stop')
    s03.TEXTS[idx[0]] = (NEW_NOTE,) + tuple(s03.TEXTS[idx[0]][1:])


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
            if ref not in CHANGED_REFS and not ref.startswith('#PWR'):
                raise SystemExit(f'symbol {ref} changed: only {sorted(CHANGED_REFS)} may: stop')
            if (b, k) in added and ref == DROPPED:
                raise SystemExit(f'{DROPPED} still drawn: stop')
        if k == 'text' and OLD_NOTE not in b and NEW_NOTE not in b:
            raise SystemExit('a text other than the timer note changed: stop')

    def libs(text):
        return [text[a:b] for a, b in s03.top_level_blocks(text) if text.startswith('(lib_symbols', a)]

    if libs(before) != libs(after):
        raise SystemExit('lib_symbols changed: stop')
    return count(removed), count(added)


def main(argv):
    dry = '--dry-run' in argv
    if LOCK.exists():
        raise SystemExit(f'{LOCK.name} exists: close the schematic in KiCad first')
    md = check_netlist.SPEC.read_text(encoding='utf-8')
    spec, parts_table = check_netlist.parse_netlist_table(md), check_netlist.parse_parts_table(md)
    want = set(s03.SURVIVING) | set(s03.NEW) | {s04.NEW_REF, 'C27'}
    if set(spec) != want or any(spec[r]['value'] != v for r, v in NEW_VALUES.items()) or \
            any(spec[r]['pins'] != s06.CAP_PINS for r in KEPT_CAPS) or \
            any(parts_table.get(r, {}).get('mpn') != s06.C5_MPN for r in KEPT_CAPS):
        raise SystemExit('SPEC 6 / 7 is not the low-trip timer state this script implements (refs without C28, '
                         'R4 / R5 / R23 / R24 / R9 values, C5 / C27 rows): stop')
    with open(SHEET, encoding='utf-8', newline='') as fh:
        src = fh.read()
    if '\r\n' not in src:
        raise SystemExit(f'{SHEET.name}: not CRLF: unexpected state')
    text = src.replace('\r\n', '\n')

    s03.MANUFACTURER.setdefault(s06.C5_MPN, s06.C5_MAKER)
    set_note()
    s05.install_symbol(s05.project_symbol())
    out = s04.with_title(s04.build(text, spec, parts_table, layout()))
    if sha256(src) != PRE_SHA256:
        if out.replace('\n', EOL) == src:
            print(f'{SHEET.name}: already applied (low-trip timer, C28 removed); nothing changed')
            return
        raise SystemExit(f'{SHEET.name}: neither the 06 sheet (SHA-256 {PRE_SHA256[:12]}...) nor the 07 result: '
                         'stop; edit by hand or with a new script')
    removed, added = check_changes(text, out)
    if dry:
        print(f'dry run: checks passed; would remove {removed}, add {added}; nothing written')
        return
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_sch'
    shutil.copy2(SHEET, backup)
    with open(SHEET, 'w', encoding='utf-8', newline='') as fh:
        fh.write(out.replace('\n', EOL))
    print(f'backup {backup.relative_to(ROOT)}')
    print(f'{SHEET.name}: C28 removed, R4 / R5 / R23 / R24 values, R9 moved; removed {removed}, added {added}')


if __name__ == '__main__':
    main(sys.argv)
