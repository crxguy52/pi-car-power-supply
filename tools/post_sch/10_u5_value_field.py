"""Post-schematic edit 10 (2026-11-05): U5 value text moved below the U5 body (legibility; SPEC 7 unchanged).

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/10_u5_value_field.py [--dry-run]

What and why (staff review of 08 / 09, 2026-11-05): on the 09 sheet U5's Value field ("CD4541BM96") sits above the
U5 body, directly under C8's value and between the C8 and D7 ground symbols, so it reads as C8's part number. It
moves below the U5 body, right of the VSS pin. Nothing else changes: no part, pin, net, wire, label, uuid or
field value; SPEC 7 and the 09 layout otherwise hold as they are.

Uses 03's layout engine through 09's layout (imported); 03's grid / wire / connectivity-vs-SPEC 7 / overlap / A4
frame checks run before writing. tools/check_netlist.py then checks the netlist export (`pdm run verify-sch`).

Guards: refuses if KiCad's lock file exists. Accepts two states: (1) pre-edit: the sheet is byte-identical to what
09 wrote (SHA-256 below); (2) applied: the sheet equals what this script writes ("already applied"). Anything else
stops. SPEC 7 must hold exactly 09's parts and VDD_TMR pins (09's check). After the build: every part keeps its
symbol uuid, the only changed item is the U5 symbol block, and in it only the Value field position. Backup to
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


s09 = _load('post_sch_09', TOOLS / 'post_sch' / '09_u5_vout_supply.py')
s08, s04, s03 = s09.s08, s09.s04, s09.s03
P = s03.P

SHEET, LOCK, BACKUPS, ROOT, STEM = s03.SHEET, s03.LOCK, s03.BACKUPS, s03.ROOT, s03.STEM
PRE_SHA256 = 'd58396ff0ef3a8744de7409f8178fffe68f93c218f3bc581228d98148770da97'   # the sheet as 09 wrote it
EOL = '\r\n'
REF = 'U5'

# ------------------------------------------------------------------------------------------------- layout
# Grid units, offsets from the U5 symbol origin. Reference keeps 08's place (above left of the body); Value goes
# below the body, right of the VSS pin and its ground symbol, left of the D6 / ACC_G group.
REF_OFFSET = (-6, -13)
VALUE_OFFSET = (8, 14)
OLD_FIELDS = (REF_OFFSET, (8, -13))

old_u5 = [p for p in s09.PARTS if p.ref == REF]
if len(old_u5) != 1 or old_u5[0].fields != OLD_FIELDS:
    raise SystemExit(f'09 layout: {REF} not found once with fields {OLD_FIELDS}: unexpected state')
NEW_U5 = P(REF, old_u5[0].kind, old_u5[0].x, old_u5[0].y, old_u5[0].rot, old_u5[0].unit,
           fields=(REF_OFFSET, VALUE_OFFSET), pins=dict(old_u5[0].pins))
PARTS = [NEW_U5 if p.ref == REF else p for p in s09.PARTS]
LINKS = s09.LINKS


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def install():
    """Point 03's engine at this layout (09's install, over this PARTS list)."""
    for p in PARTS:
        p.pins.update(s08.PIN_OVERRIDES.get(p.ref, {}))
    s03.LIB.clear()
    s03.LIB.update(s09.LIB)
    s03.LINK_STUB.clear()
    s03.LINK_STUB.update(s08.LINK_STUB)
    s03.FLAGS[:] = s08.FLAGS
    s03.TEXTS[:] = s09.TEXTS
    for mpn, maker in s09.MAKERS.items():
        s03.MANUFACTURER.setdefault(mpn, maker)


VALUE_AT_RE = re.compile(r'(\(property "Value" "[^"]*"\s*\(at )[-\d. ]+\)')


def check_result(old_text, out):
    """Only the U5 symbol block differs, and only in its Value field position; every uuid kept."""
    old_items, new_items = s04.item_blocks(old_text), s04.item_blocks(out)
    gone = [b for b in old_items if b not in new_items]
    added = [b for b in new_items if b not in old_items]
    errs = []
    if len(gone) != 1 or len(added) != 1:
        errs.append(f'{len(gone)} item(s) removed / {len(added)} added: expected only the {REF} symbol to change')
    else:
        g, a = gone[0], added[0]
        if f'(property "Reference" "{REF}"' not in g:
            errs.append('the changed item is not the U5 symbol')
        if VALUE_AT_RE.sub(r'\1@)', g) != VALUE_AT_RE.sub(r'\1@)', a):
            errs.append(f'{REF}: more than the Value field position changed')
    old_syms = s03.read_old(old_text, s03.top_level_blocks(old_text))
    new_syms = s03.read_old(out, s03.top_level_blocks(out))
    for ref, vs in old_syms.items():
        if sorted(v['uuid'] for v in vs) != sorted(v['uuid'] for v in new_syms.get(ref, [])):
            errs.append(f'{ref}: symbol uuid changed')
    if errs:
        raise SystemExit('result check failed:\n  ' + '\n  '.join(errs))


def main(argv):
    dry = '--dry-run' in argv
    if LOCK.exists():
        raise SystemExit(f'{LOCK.name} exists: close the schematic in KiCad first')
    md = check_netlist.SPEC.read_text(encoding='utf-8')
    spec, parts_table = check_netlist.parse_netlist_table(md), check_netlist.parse_parts_table(md)
    s09.check_spec(spec)
    placed = {p.ref for p in PARTS}
    if placed != set(spec):
        raise SystemExit(f'layout vs SPEC 7: missing {sorted(set(spec) - placed)}, extra {sorted(placed - set(spec))}')
    with open(SHEET, encoding='utf-8', newline='') as fh:
        src = fh.read()
    if '\r\n' not in src:
        raise SystemExit(f'{SHEET.name}: not CRLF: unexpected state')
    text = src.replace('\r\n', '\n')

    install()
    out = s04.with_title(s04.build(text, spec, parts_table, (PARTS, LINKS)))
    if sha256(src) != PRE_SHA256:
        if out.replace('\n', EOL) == src:
            print(f'{SHEET.name}: already applied (U5 value below the body); nothing changed')
            return
        raise SystemExit(f'{SHEET.name}: neither the 09 sheet (SHA-256 {PRE_SHA256[:12]}...) nor the 10 result: '
                         'stop; edit by hand or with a new script')
    check_result(text, out)
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
    print(f'{SHEET.name}: {REF} Value field moved below the body; {len(spec)} parts on the sheet')


if __name__ == '__main__':
    main(sys.argv)
