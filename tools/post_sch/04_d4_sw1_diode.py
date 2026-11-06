"""Post-schematic edit 04 (2026-11-05, schematic staff review): restore D4 in series with SW1; sheet title.

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/04_d4_sw1_diode.py [--dry-run]

What and why (SPEC 2 "ACC sense", SPEC 6 Parts "D4, D5", SPEC 7 rows SW1 and D4; DECISIONS 2026-11-05 "D4
restored"): 03 tied SW1 pin 1 straight to `ACC_S` on the reasoning that SW1 only ever connects `BATT` to `ACC_S`.
That holds only while `BATT` is alive. With SW1 closed and `BATT` dead (harness fuse blown, or a bench supply on ACC
only) the ACC line feeds `BATT` backwards through D5 and SW1, and Q1 (held on by the charged C5) passes the whole
load: D5 is a 1N4148W (continuous I_F 300 mA, Vishay datasheet) and SW1 is rated 100 mA non-switching (Nidec CAS
catalogue), against a 3.5-5 A load. D4 (1N4148W, the D5 part) between SW1 pin 1 (`SW1_C`) and `ACC_S` blocks that
path; in SW1 mode `ACC_S` becomes `BATT` minus one diode drop, the same as a key-on through D5.

- D4 is added with the 03 layout engine (03's PARTS / LINKS plus one part and one link, same uuid5 namespace), so
  every other item of the sheet keeps its bytes; the only removed items are SW1 pin 1's stub and its `ACC_S` label.
- Title block: title only (the sheet had none).

Guards: refuses if KiCad's lock file exists. Accepts two states: (1) pre-edit: the sheet is byte-identical to what
03 wrote (SHA-256 below); (2) applied: the sheet equals what this script writes ("already applied"). Anything else
stops. Before writing, it runs 03's own checks (grid, wires, connectivity vs SPEC 7, overlaps, A4 frame) and checks
that the change set is exactly the expected one. Backup to pi_power_board-backups/ before writing; CRLF kept.
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

S03_PATH = TOOLS / 'post_sch' / '03_simplified.py'
_spec = importlib.util.spec_from_file_location('post_sch_03', S03_PATH)
s03 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s03)

SHEET, LOCK, BACKUPS, ROOT, STEM = s03.SHEET, s03.LOCK, s03.BACKUPS, s03.ROOT, s03.STEM
PRE_SHA256 = '165005d233b49a8250f16413d221ae68eb2472a1d401c6dd588dcd166baaa593'   # the sheet as 03 wrote it
NEW_REF = 'D4'
NEW_PINS = {'1': 'ACC_S', '2': 'SW1_C'}
SW1_PIN1_NET = 'SW1_C'
D4_PLACE = ('D4', 'D', 54, 64, 180)              # ref, kind, x, y (grid units), rotation: anode left, as D5
D4_FIELDS = 'below'
D4_LINK = ('SW1_C', ['SW1.1', 'D4.2'], (35, 64), 0)
TITLE = 'Pi 5 car power HAT'
PAPER_LINE = f'(paper {s03.PAPER_NEW})'
# Items of the 03 sheet that 04 replaces: SW1 pin 1 stub wire and its ACC_S label
EXPECTED_REMOVED_KINDS = {'wire': 1, 'label': 1}
EXPECTED_ADDED_KINDS = {'symbol': 1, 'wire': 3, 'label': 2}   # link split at its label + D4 cathode stub


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build(src, spec, parts_table, layout):
    """Sheet text from 03's engine with the given PARTS / LINKS (mirrors 03 main)."""
    text = src.replace('\r\n', '\n')
    blocks = s03.top_level_blocks(text)
    old = s03.read_old(text, blocks)
    old_kept = {(r, v['unit']): v for r, vs in old.items() if r in spec for v in vs}
    s03.PARTS[:], s03.LINKS[:] = layout
    sheet = s03.Sheet(spec, parts_table, old_kept)
    sheet.build()
    sheet.check_grid()
    sheet.check_wires()
    sheet.check_connectivity()
    sheet.check_overlaps()
    root_uuid = sexpr.find(sexpr.parse(text[:text.index('(lib_symbols')] + ')'), 'uuid')[1]
    lib_s = next(a for a, b in blocks if text.startswith('(lib_symbols', a))
    si_s, si_e = next((a, b) for a, b in blocks if text.startswith('(sheet_instances', a))
    head = text[:text.rfind('\n', 0, lib_s) + 1]
    body = '\n'.join([sheet.lib_symbols_text()] + sheet.items_text(f'/{root_uuid}'))
    return head + body + '\n\t' + text[si_s:si_e] + text[si_e:]


def with_title(text):
    if '(title_block' in text:
        return text
    if text.count(PAPER_LINE) != 1:
        raise SystemExit(f'{PAPER_LINE} not found once: unexpected state')
    return text.replace(PAPER_LINE, f'{PAPER_LINE}\n\t(title_block\n\t\t(title {s03.q(TITLE)})\n\t)', 1)


def item_blocks(text):
    """{block text: kind} of the placed items (symbols, wires, labels, ...), lib_symbols excluded."""
    out = {}
    for a, b in s03.top_level_blocks(text):
        blk = text[a:b]
        kind = blk[1:blk.find('\n') if '\n' in blk else None].split()[0]
        if kind not in ('lib_symbols', 'sheet_instances', 'title_block', 'paper', 'version', 'generator',
                        'generator_version', 'uuid', 'embedded_fonts'):
            out[blk] = kind
    return out


def check_changes(before, after):
    old, new = item_blocks(before), item_blocks(after)
    removed = [k for b, k in old.items() if b not in new]
    added = [k for b, k in new.items() if b not in old]
    count = lambda kinds: {k: kinds.count(k) for k in sorted(set(kinds))}  # noqa: E731
    if count(removed) != EXPECTED_REMOVED_KINDS or count(added) != EXPECTED_ADDED_KINDS:
        raise SystemExit(f'change set removed {count(removed)}, added {count(added)}; expected '
                         f'{EXPECTED_REMOVED_KINDS} / {EXPECTED_ADDED_KINDS}: stop')
    lib_old = [before[a:b] for a, b in s03.top_level_blocks(before) if before.startswith('(lib_symbols', a)]
    lib_new = [after[a:b] for a, b in s03.top_level_blocks(after) if after.startswith('(lib_symbols', a)]
    if lib_old != lib_new:
        raise SystemExit('lib_symbols changed (D4 uses the D5 symbol, already embedded): stop')
    return count(removed), count(added)


def main(argv):
    dry = '--dry-run' in argv
    if LOCK.exists():
        raise SystemExit(f'{LOCK.name} exists: close the schematic in KiCad first')
    md = check_netlist.SPEC.read_text(encoding='utf-8')
    spec, parts_table = check_netlist.parse_netlist_table(md), check_netlist.parse_parts_table(md)
    want = set(s03.SURVIVING) | set(s03.NEW) | {NEW_REF}
    if set(spec) != want or spec[NEW_REF]['pins'] != NEW_PINS or spec['SW1']['pins'].get('1') != SW1_PIN1_NET:
        raise SystemExit('SPEC 7 is not the D4 state this script implements (refs, D4 pins, SW1 pin 1): stop')
    with open(SHEET, encoding='utf-8', newline='') as fh:
        src = fh.read()
    eol = '\r\n' if '\r\n' in src else '\n'
    text = src.replace('\r\n', '\n')

    layout = (list(s03.PARTS) + [s03.P(*D4_PLACE, fields=D4_FIELDS)], list(s03.LINKS) + [D4_LINK])
    pre_edit = sha256(src) == PRE_SHA256
    out = with_title(build(text, spec, parts_table, layout))
    if not pre_edit:
        if out.replace('\n', eol) == src:
            print(f'{SHEET.name}: already applied (D4 in series with SW1); nothing changed')
            return
        raise SystemExit(f'{SHEET.name}: neither the 03 sheet (SHA-256 {PRE_SHA256[:12]}...) nor the 04 result: '
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
        fh.write(out.replace('\n', eol))
    print(f'backup {backup.relative_to(ROOT)}')
    print(f'{SHEET.name}: D4 added (SW1_C -> ACC_S); removed {removed}, added {added}; title "{TITLE}"')


if __name__ == '__main__':
    main(sys.argv)
