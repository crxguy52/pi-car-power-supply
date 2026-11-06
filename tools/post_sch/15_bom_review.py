"""Post-schematic edit 15 (2026-11-05, BOM staff review): D3 -> Stanley VFR1105W-6C9-TR (car-temperature LED),
C29 -> Murata GCM21B5C2E103FX0AL (same C0G +-1 % timing capacitor, AEC-Q200, a fifth of the price).

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/15_bom_review.py [--dry-run]

What and why (SPEC 4 "LED", SPEC 3 "C29 (CTC)", SPEC 6 "Parts", DECISIONS "BOM staff review"):
- D3: LTST-C150KRKT is rated -30 to +85 degC operating (Lite-On datasheet), narrower than a car cabin. The Stanley
  1105W "High Reliability V-Series" red LED is rated -40 to +100 degC (Stanley 1105W V-Series datasheet,
  ref/datasheets/Stanley_1105W_V-series.pdf), 3.2 x 1.6 mm like the 1206 footprint, V_F 1.9 V typ / 2.4 V max at
  20 mA (Lite-On 2.0 / 2.4 V): R3 is kept. Fields Manufacturer / MPN / Digi-Key PN / Description / Datasheet and the
  Value ("VFR1105W", SPEC 7). The footprint, the symbol and its Sim fields are not touched (the sim's LED model is a
  generic red LED stand-in).
- C29: KEMET C0805C103F5GACTU costs $3.75 at the order quantity; Murata GCM21B5C2E103FX0AL has the same C0G
  (0 +-30 ppm/K) and +-1 % tolerance, 250 V rating (>= the 50 V the Value states), AEC-Q200, 0805, cut tape
  (Murata datasheet ref/datasheets/Murata_GCM21B5C2E103FX0A.pdf). Fields Manufacturer / MPN / Digi-Key PN /
  Description / Datasheet; the Value "10 nF 50 V C0G +-1 %" stays (SPEC 7; the rating is a minimum).

Guards: refuses if KiCad's lock file exists or the sheet is not CRLF. SPEC 6 must already list the new
Manufacturer / MPN / Digi-Key PN / Datasheet for D3 and C29 and SPEC 7 the new D3 value (spec first). Each edited
field must hold exactly its old value (the tools/post_sch/14 result) or its new value, and appear once; anything
else stops. "already applied" when the sheet equals the result. After the edit: everything outside the D3 and C29
symbol blocks is byte-identical, and inside them only the listed fields differ. Backup to pi_power_board-backups/
first.
"""
import argparse
import datetime
import importlib.util
import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent.parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import check_netlist  # noqa: E402

_spec14 = importlib.util.spec_from_file_location('bom14', TOOLS / 'post_sch' / '14_bom_fields.py')
bom14 = importlib.util.module_from_spec(_spec14)
_spec14.loader.exec_module(bom14)

SHEET, LOCK, BACKUPS, SPEC, NL = bom14.SHEET, bom14.LOCK, bom14.BACKUPS, bom14.SPEC, bom14.NL
F_MFR, F_MPN, F_DK, F_DESC, F_DS, F_VALUE = (bom14.F_MFR, bom14.F_MPN, bom14.F_DK, bom14.F_DESC, bom14.F_DS,
                                            bom14.F_VALUE)
DS = bom14.KIPRJMOD + bom14.DS_DIR

# ref: {field: (old value = the 14 result, new value)}
CHANGES = {
    'D3': {
        F_MFR: ('Lite-On', 'Stanley Electric'),
        F_MPN: ('LTST-C150KRKT', 'VFR1105W-6C9-TR'),
        F_DK: ('160-1405-1-ND', '404-1321-1-ND'),
        F_DS: (DS + 'LiteOn_LTST-C150KRKT.pdf', DS + 'Stanley_1105W_V-series.pdf'),
        F_DESC: ('LED red, 1206',
                 'LED red 626 nm, 3216 (1206) dome lens, -40 to 100 °C (Stanley 1105W V-Series)'),
        F_VALUE: ('LTST-C150KRKT', 'VFR1105W'),
    },
    'C29': {
        F_MFR: ('KEMET', 'Murata Electronics'),
        F_MPN: ('C0805C103F5GACTU', 'GCM21B5C2E103FX0AL'),
        F_DK: ('399-C0805C103F5GACTUCT-ND', '490-GCM21B5C2E103FX0ALCT-ND'),
        F_DS: (DS + 'KEMET_C1003_C0G.pdf', DS + 'Murata_GCM21B5C2E103FX0A.pdf'),
        F_DESC: ('Capacitor 10 nF ±1 % 50 V C0G, 0805', 'Capacitor 10 nF ±1 % 250 V C0G, 0805, AEC-Q200'),
    },
}
SPEC6_COLS = {F_MFR: 'Manufacturer', F_MPN: 'MPN', F_DK: 'Digi-Key PN', F_DS: 'Datasheet'}
SPEC6_DS_PREFIX = bom14.DS_DIR


def unesc(v):
    return v.replace('\\"', '"').replace('\\\\', '\\')


def check_spec(md):
    """SPEC 6 rows of D3 / C29 and SPEC 7's D3 value already carry the new values (spec first)."""
    errs = []
    header, rows = check_netlist._rows(check_netlist._section(md, check_netlist.PARTS_HEADING), 'Ref')
    col = {name: i for i, name in enumerate(header)}
    seen = set()
    for row in rows:
        for ref in re.split(r'\s*,\s*', row[col['Ref']]):
            if ref not in CHANGES:
                continue
            seen.add(ref)
            for f, c in SPEC6_COLS.items():
                want = CHANGES[ref][f][1]
                if f == F_DS:
                    want = SPEC6_DS_PREFIX + want[len(DS):]
                if row[col[c]] != want:
                    errs.append(f'SPEC 6 {ref} {c} {row[col[c]]!r}, expected {want!r}')
    errs += [f'SPEC 6 has no row for {r}' for r in sorted(set(CHANGES) - seen)]
    spec7 = check_netlist.parse_netlist_table(md)
    for ref, ch in CHANGES.items():
        if F_VALUE in ch and spec7[ref]['value'] != ch[F_VALUE][1]:
            errs.append(f"SPEC 7 {ref} value {spec7[ref]['value']!r}, expected {ch[F_VALUE][1]!r}")
    return errs


def edit_block(block, ref):
    for name, (old, new) in CHANGES[ref].items():
        rx = bom14.prop_re(name)
        hits = rx.findall(block)
        if len(hits) != 1:
            raise SystemExit(f'unexpected state: {ref} has {len(hits)} {name} fields')
        cur = unesc(hits[0][1])
        if cur not in (old, new):
            raise SystemExit(f'unexpected state: {ref} {name} = {cur!r} (neither {old!r} nor {new!r})')
        block = rx.sub(lambda m: m.group(1) + bom14.esc(new) + m.group(3), block, count=1)
    return block


def build(text):
    blocks = bom14.symbol_blocks(text)
    refs = [r for *_, r in blocks]
    for ref in CHANGES:
        if refs.count(ref) != 1:
            raise SystemExit(f'unexpected state: {refs.count(ref)} symbol blocks for {ref}')
    out, pos = [], 0
    for s, e, ref in blocks:
        out.append(text[pos:s])
        out.append(edit_block(text[s:e], ref) if ref in CHANGES else text[s:e])
        pos = e
    out.append(text[pos:])
    return ''.join(out)


def strip_changed(block, ref):
    """The block with the edited field values blanked: what must not change."""
    for name in CHANGES[ref]:
        block = bom14.prop_re(name).sub(lambda m: m.group(1) + m.group(3), block, count=1)
    return block


def check_result(old, new):
    a, b = bom14.symbol_blocks(old), bom14.symbol_blocks(new)
    if [r for *_, r in a] != [r for *_, r in b]:
        raise SystemExit('check: symbol block list changed')
    pos_a = pos_b = 0
    for (s0, e0, ref), (s1, e1, _) in zip(a, b):
        if old[pos_a:s0] != new[pos_b:s1]:
            raise SystemExit('check: text outside the symbol blocks changed')
        x, y = old[s0:e0], new[s1:e1]
        if ref in CHANGES:
            if strip_changed(x, ref) != strip_changed(y, ref):
                raise SystemExit(f'check: {ref} changed beyond the listed fields')
            for name, (_, want) in CHANGES[ref].items():
                got = bom14.prop_re(name).findall(y)
                if len(got) != 1 or unesc(got[0][1]) != want:
                    raise SystemExit(f'check: {ref} {name} not the target')
        elif x != y:
            raise SystemExit(f'check: {ref} changed')
        pos_a, pos_b = e0, e1
    if old[pos_a:] != new[pos_b:]:
        raise SystemExit('check: text after the last symbol block changed')
    if '\n' in new.replace('\r\n', '') or '\r' in new.replace('\r\n', ''):
        raise SystemExit('check: line endings are not all CRLF')


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv[1:])
    if LOCK.exists():
        raise SystemExit(f'{LOCK.name} exists: close the schematic in KiCad first')
    text = SHEET.read_bytes().decode('utf-8')
    if text.count('\r\n') != text.count('\n'):
        raise SystemExit('unexpected state: the sheet is not CRLF')
    errs = check_spec(SPEC.read_text(encoding='utf-8'))
    if errs:
        raise SystemExit('SPEC not updated first:\n  ' + '\n  '.join(errs))
    new = build(text)
    if new == text:
        print('already applied')
        return 0
    check_result(text, new)
    if a.dry_run:
        print(f'dry run: {len(new) - len(text):+d} chars on {", ".join(CHANGES)}; nothing written')
        return 0
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    (BACKUPS / f'{SHEET.stem}_{stamp}{SHEET.suffix}').write_bytes(SHEET.read_bytes())
    SHEET.write_bytes(new.encode('utf-8'))
    print(f'applied: {", ".join(CHANGES)} fields; backup {stamp}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
