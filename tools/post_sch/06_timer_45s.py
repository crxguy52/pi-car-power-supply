"""Post-schematic edit 06 (2026-11-05, project lead): delay-off hold >= 45 s worst case.

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/06_timer_45s.py [--dry-run]

What and why (project lead 2026-11-05: on a rapid key cycle the Pi 5 must cold-boot, see "ACC off" and shut down
before the power drops, so the hold after the last key-off must be >= 45 s worst case; SPEC 3 "Delay-off timer",
SPEC 6 Parts rows C5 / R9, SPEC 7 rows C5, C27, C28, R9; DECISIONS 2026-11-05 "timer 45 s"; numbers in
`tools/design_calc.py` `timer()`): the topology stays (U1A = RC threshold with hysteresis); the timing passives are
resized:

- C27 and C28 (10 uF 50 V X7R 1206, the C5 part) are added in parallel with C5 (`C5_T` to GND): 3 x 10 uF.
- R9 2.4 Mohm -> 4.7 Mohm (value from SPEC 7).
- C5, C27, C28 get the chosen part (MPN, manufacturer, datasheet from the SPEC 6 Parts row).
- Layout: C27 and C28 sit right of C5 on the same `C5_T` wire, one value-text width apart; R9 moves right of them.
  The timer note names the three capacitors.

Uses 03's layout engine with 05's PARTS / LINKS (05 imported, which imports 04), so every other item of the sheet
keeps its bytes. New uuids are uuid5 from 03's namespace (reproducible); C5 and R9 keep their symbol / pin uuids
(board link). Refs C27 / C28 are unused on the sheet and on the old board (C6 / C7 / C9 still exist there).

Guards: refuses if KiCad's lock file exists. Accepts two states: (1) pre-edit: the sheet is byte-identical to what
05 wrote (SHA-256 below); (2) applied: the sheet equals what this script writes ("already applied"). Anything else
stops. SPEC 7 must hold the C27 / C28 rows this script draws. Before writing, 03's checks run (grid, wires,
connectivity vs SPEC 7, overlaps, A4 frame), then a change-set check: only C5, C27, C28, R9, their wires / GND
symbols and the timer note change; lib_symbols unchanged. Backup to pi_power_board-backups/ first; CRLF kept.
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


s05 = _load('post_sch_05', TOOLS / 'post_sch' / '05_u1_power_block.py')
s04, s03 = s05.s04, s05.s03

SHEET, LOCK, BACKUPS, ROOT, STEM = s03.SHEET, s03.LOCK, s03.BACKUPS, s03.ROOT, s03.STEM
PRE_SHA256 = '012f5f5ced41cf59875494937c9d65a268a0cbbd6f197bedf4a695f471458cec'   # the sheet as 05 wrote it
EOL = '\r\n'

TIMER_NET = 'C5_T'
NEW_CAPS = ('C27', 'C28')
CAP_PINS = {'1': TIMER_NET, '2': s03.GND}
R9_VALUE = '4.7 MΩ 1 %'
R9_PRINT = R9_VALUE.replace('Ω', 'ohm')            # console text (cp1252 consoles)
C5_MPN, C5_MAKER = 'GMC31X7R106K50NT', 'Cal-Chip Electronics'

# Layout, grid units (03 / 05): C5 stays at (C5_X, ROW_Y). PITCH: the smallest spacing that clears the value text
# in 03's overlap check; C27 lands on R9's old position, so the C5-to-R9 wire is kept as the C5-to-C27 wire
C5_X, ROW_Y, WIRE_Y = 88, 65, 60
PITCH = 18
OLD_R9_X = 106
CAP_X = {ref: C5_X + PITCH * (i + 1) for i, ref in enumerate(NEW_CAPS)}
R9_X = C5_X + PITCH * (len(NEW_CAPS) + 1)
OLD_R9_LINK = (TIMER_NET, [(C5_X, WIRE_Y), (OLD_R9_X, WIRE_Y), 'R9.1'], None, 0)
OLD_NOTE = 'Key off: delay ~ R9 C5 ln(V0 / REF) (SPEC 3)'
NEW_NOTE = 'Key off: delay ~ R9 (C5 + C27 + C28) ln(V0 / REF) (SPEC 3)'

CHANGED_REFS = {'C5', 'R9'} | set(NEW_CAPS)
# Changed placed items (power symbols compared without their #PWR reference), from the dry run.
# Removed: C5 (MPN, maker, datasheet fields), R9 (value, position); the timer note.
# Added: C5, R9, C27, C28 and the two new GND symbols; the C5_T wires and their junctions; the note.
EXPECTED_REMOVED_KINDS = {'symbol': 2, 'text': 1}
EXPECTED_ADDED_KINDS = {'junction': 2, 'symbol': 6, 'text': 1, 'wire': 6}
POWER_REF = re.compile(r'(\(property "Reference" |\(reference )"#(PWR|FLG)\d+"')


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def layout():
    """05's PARTS / LINKS with C27 / C28 added right of C5 and R9 moved right of them."""
    parts, links = s05.layout()
    idx_r9 = [i for i, p in enumerate(parts) if p.key == 'R9']
    idx_c5 = [i for i, p in enumerate(parts) if p.key == 'C5']
    idx_l = [i for i, lk in enumerate(links) if lk == OLD_R9_LINK]
    if len(idx_r9) != 1 or len(idx_c5) != 1 or len(idx_l) != 1 or \
            (parts[idx_c5[0]].x, parts[idx_c5[0]].y) != (C5_X, ROW_Y):
        raise SystemExit('05 layout: R9, C5 or the C5_T link to R9 not found once where expected: stop')
    parts[idx_r9[0]] = s03.P('R9', 'R', R9_X, ROW_Y)
    parts += [s03.P(ref, 'C', x, ROW_Y) for ref, x in CAP_X.items()]
    xs = [C5_X] + list(CAP_X.values())
    new_links = [(TIMER_NET, [(a, WIRE_Y), (b, WIRE_Y), f'{ref}.1'], None, 0)
                 for a, b, ref in zip(xs, xs[1:], NEW_CAPS)]
    new_links.append((TIMER_NET, [(xs[-1], WIRE_Y), (R9_X, WIRE_Y), 'R9.1'], None, 0))
    links[idx_l[0]:idx_l[0] + 1] = new_links
    return parts, links


def set_note():
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
        if k == 'text' and OLD_NOTE not in b and NEW_NOTE not in b:
            raise SystemExit('a text other than the timer note changed: stop')

    def libs(text):
        return [text[a:b] for a, b in s03.top_level_blocks(text) if text.startswith('(lib_symbols', a)]

    if libs(before) != libs(after):
        raise SystemExit('lib_symbols changed (C27 / C28 use the C5 symbol, already embedded): stop')
    return count(removed), count(added)


def main(argv):
    dry = '--dry-run' in argv
    if LOCK.exists():
        raise SystemExit(f'{LOCK.name} exists: close the schematic in KiCad first')
    md = check_netlist.SPEC.read_text(encoding='utf-8')
    spec, parts_table = check_netlist.parse_netlist_table(md), check_netlist.parse_parts_table(md)
    want = set(s03.SURVIVING) | set(s03.NEW) | {s04.NEW_REF} | set(NEW_CAPS)
    if set(spec) != want or any(spec[r]['pins'] != CAP_PINS for r in ('C5',) + NEW_CAPS) or \
            any(spec[r]['footprint'] != spec['C5']['footprint'] or spec[r]['value'] != spec['C5']['value']
                for r in NEW_CAPS) or spec['R9']['value'] != R9_VALUE or \
            any(parts_table.get(r, {}).get('mpn') != C5_MPN for r in ('C5',) + NEW_CAPS):
        raise SystemExit('SPEC 6 / 7 is not the 45 s timer state this script implements (refs, C27 / C28 rows, R9 '
                         'value, C5 MPN): stop')
    with open(SHEET, encoding='utf-8', newline='') as fh:
        src = fh.read()
    if '\r\n' not in src:
        raise SystemExit(f'{SHEET.name}: not CRLF: unexpected state')
    text = src.replace('\r\n', '\n')

    s03.MANUFACTURER.setdefault(C5_MPN, C5_MAKER)
    set_note()
    s05.install_symbol(s05.project_symbol())
    out = s04.with_title(s04.build(text, spec, parts_table, layout()))
    if sha256(src) != PRE_SHA256:
        if out.replace('\n', EOL) == src:
            print(f'{SHEET.name}: already applied (45 s timer: C27, C28, R9 {R9_PRINT}); nothing changed')
            return
        raise SystemExit(f'{SHEET.name}: neither the 05 sheet (SHA-256 {PRE_SHA256[:12]}...) nor the 06 result: '
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
    print(f'{SHEET.name}: C27, C28 added on {TIMER_NET}, R9 -> {R9_PRINT}; removed {removed}, added {added}')


if __name__ == '__main__':
    main(sys.argv)
