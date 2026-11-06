"""Post-schematic edit 16 (2026-11-06, U8 datasheet review): buck TPS54336A fixes from reports/ic_review.md.

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/16_buck_fixes.py [--dry-run]

What and why (SPEC 4 "Buck U8", SPEC 6 "Parts", SPEC 7; DECISIONS 2026-11-06 rows; SLVSCD5D section numbers):
- L1 SRP1038A-100M -> SRP1038A-150M (15 uH, same footprint): K_IND was 0.34 at 16 V against "as high as 0.3"
  (8.2.2.6.1, eq 19: L_min 11.3 uH); now 0.23. Value, MPN, Digi-Key PN, Description.
- R16 53.6k -> 73.2k, R17 10.0k -> 13.7k (eq 15 / 16): worst-case VOUT was 5.252 V (> USB 5.25 V); now
  5.074 V nominal, 4.915-5.238 V with the reference +-1.5 % and 1 % resistors.
- R18 5.49k -> 7.32k (eq 10, Type 2B): crossover kept near 30 kHz with the fourth output capacitor.
- C31 added: second 10 uF 50 V X7R 1206 input capacitor (eq 17: 441 mV -> 227 mV p-p), a copy of C15's fields,
  VOUT / GND label-stub wiring below C19.
- C32 added: fourth 47 uF 10 V X7R 1210 output capacitor (eq 22 margin 1 % -> 35 % at 25 % DC-bias retention),
  a copy of C22's fields, +5V1 / GND label-stub wiring below C20.
- Block header "BUCK 5.1 V" -> "BUCK 5.07 V".
- simulation.kicad_sch, U8 stand-in .param line (sim master): V5SET 5.09 -> 5.07 V, C5V1 48u -> 64u (4 x 47 uF at
  the 34 % design retention), CIN_U8 5u -> 10u (2 x 10 uF at 50 %), RFB 63.6k -> 86.9k (R16 + R17). With these and
  tools/run_sim.py's canonical element order the sim passes 14 of 14 (the element order of the exported deck had
  made two fast scenarios fail to converge, independent of these values).

Text-level, CRLF kept. Every existing symbol keeps its uuid and pin uuids; the new items get uuid5 uuids seeded by
this script and are inserted right after their template item (C31 after C15, C32 after C22, the GND symbols after
#PWR14, the labels after C15's VOUT label, the wires after C15's GND wire). New power refs #PWR27, #PWR28.

Guards: refuses if KiCad's lock file exists or the sheet is not CRLF; SPEC 6 / 7 must carry the new values first.
Each edited field must hold its old or its new value; C31 / C32 must be both absent (apply) or both present with
the target text (already applied). After the edit: removing the inserted items and blanking the edited fields gives
the old sheet back, byte for byte. Backup to pi_power_board-backups/ first.
"""
import argparse
import datetime
import importlib.util
import pathlib
import re
import sys
import uuid

TOOLS = pathlib.Path(__file__).resolve().parent.parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import check_netlist  # noqa: E402

_spec14 = importlib.util.spec_from_file_location('bom14', TOOLS / 'post_sch' / '14_bom_fields.py')
bom14 = importlib.util.module_from_spec(_spec14)
_spec14.loader.exec_module(bom14)

SHEET, LOCK, BACKUPS, SPEC, NL = bom14.SHEET, bom14.LOCK, bom14.BACKUPS, bom14.SPEC, bom14.NL
F_MPN, F_DK, F_DESC, F_VALUE = bom14.F_MPN, bom14.F_DK, bom14.F_DESC, bom14.F_VALUE
UUID_NS = uuid.UUID('8f6c2a8e-6b1f-5a0e-9d3c-16b0c4f5a216')    # seed of this script's uuid5 uuids

CHANGES = {
    'L1': {
        F_VALUE: ('SRP1038A-100M', 'SRP1038A-150M'),
        F_MPN: ('SRP1038A-100M', 'SRP1038A-150M'),
        F_DK: ('SRP1038A-100MCT-ND', 'SRP1038A-150MCT-ND'),
        F_DESC: ('Inductor 10 µH ±20 %, shielded, I_sat 12 A, 30 mΩ max, 10 x 11 mm, AEC-Q200',
                 'Inductor 15 µH ±20 %, shielded, I_sat 10 A, I_rms 6.25 A, 45 mΩ max, 10 x 11 mm, AEC-Q200'),
    },
    'R16': {
        F_VALUE: ('53.6 kΩ 1 %', '73.2 kΩ 1 %'),
        F_MPN: ('CRCW080553K6FKEA', 'CRCW080573K2FKEA'),
        F_DK: ('541-53.6KCCT-ND', '541-73.2KCCT-ND'),
        F_DESC: ('53.6 kΩ Resistor, thick film, ±1 %, 0.125 W, ±100 ppm/K, 0805, AEC-Q200',
                 '73.2 kΩ Resistor, thick film, ±1 %, 0.125 W, ±100 ppm/K, 0805, AEC-Q200'),
    },
    'R17': {
        F_VALUE: ('10.0 kΩ 1 %', '13.7 kΩ 1 %'),
        F_MPN: ('CRCW080510K0FKEA', 'CRCW080513K7FKEA'),
        F_DK: ('541-10.0KCCT-ND', '541-13.7KCCT-ND'),
        F_DESC: ('10.0 kΩ Resistor, thick film, ±1 %, 0.125 W, ±100 ppm/K, 0805, AEC-Q200',
                 '13.7 kΩ Resistor, thick film, ±1 %, 0.125 W, ±100 ppm/K, 0805, AEC-Q200'),
    },
    'R18': {
        F_VALUE: ('5.49 kΩ 1 %', '7.32 kΩ 1 %'),
        F_MPN: ('CRCW08055K49FKEA', 'CRCW08057K32FKEA'),
        F_DK: ('541-5.49KCCT-ND', '541-7.32KCCT-ND'),
        F_DESC: ('5.49 kΩ Resistor, thick film, ±1 %, 0.125 W, ±100 ppm/K, 0805, AEC-Q200',
                 '7.32 kΩ Resistor, thick film, ±1 %, 0.125 W, ±100 ppm/K, 0805, AEC-Q200'),
    },
}
TITLE_OLD, TITLE_NEW = '(text "BUCK 5.1 V"', '(text "BUCK 5.07 V"'
GRID = 1.27
# new capacitor: (ref, template ref, position, power ref, top-pin label, template label (net, at))
NEW_CAPS = (
    ('C31', 'C15', (17.78, 185.42), '#PWR27', 'VOUT'),
    ('C32', 'C22', (45.72, 185.42), '#PWR28', '+5V1'),
)
PWR_TEMPLATE, PWR_TEMPLATE_AT = '#PWR14', (17.78, 133.35)      # C15's GND symbol
LABEL_TEMPLATE_AT = (17.78, 120.65)                             # C15's VOUT label
WIRE_TEMPLATE = '(xy 17.78 130.81) (xy 17.78 133.35)'          # C15 pin 2 to its GND symbol
SIM_SHEET = ROOT / 'simulation.kicad_sch'
SIM_OLD = 'V5SET=5.09 UV_ON=4.5 UV_OFF=4.32 T_SS=3.5m C5V1=48u CIN_U8=5u RFB=63.6k'
SIM_NEW = 'V5SET=5.07 UV_ON=4.5 UV_OFF=4.32 T_SS=3.5m C5V1=64u CIN_U8=10u RFB=86.9k'
PIN_OFFSET = 3.81                                               # Device:C pin end from the symbol origin
STUB = 2.54                                                     # label / GND stub length


def uid(name):
    return str(uuid.uuid5(UUID_NS, name))


def unesc(v):
    return v.replace('\\"', '"').replace('\\\\', '\\')


def fmt(v):
    return f'{round(v, 4):g}'


def shift_at(block, dx, dy):
    def f(m):
        return f'(at {fmt(float(m.group(1)) + dx)} {fmt(float(m.group(2)) + dy)}'
    return re.sub(r'\(at ([\d.\-]+) ([\d.\-]+)', f, block)


def top_item(text, start_rx):
    """(start, end) of the one top-level item whose text matches start_rx (regex on the item)."""
    hits = []
    for m in re.finditer(r'\n\t\((?:symbol\r\n|wire\r\n|label ")', text):
        s = m.start() + 1
        e = text.index('\n\t)\r\n', s) + len('\n\t)\r\n')
        if re.search(start_rx, text[s:e]):
            hits.append((s, e))
    if len(hits) != 1:
        raise SystemExit(f'unexpected state: {len(hits)} items match {start_rx!r}')
    return hits[0]


def symbol_block(text, ref):
    hits = [(s, e) for s, e, r in bom14.symbol_blocks(text) if r == ref]
    if len(hits) != 1:
        raise SystemExit(f'unexpected state: {len(hits)} symbol blocks for {ref}')
    return hits[0]


def new_symbol(tmpl, ref, old_ref, at_old, at_new, tag):
    b = shift_at(tmpl, at_new[0] - at_old[0], at_new[1] - at_old[1])
    b = b.replace(f'(property "Reference" "{old_ref}"', f'(property "Reference" "{ref}"')
    b = b.replace(f'(reference "{old_ref}")', f'(reference "{ref}")')
    n = [0]

    def ru(m):
        n[0] += 1
        return f'(uuid "{uid(f"{tag}:{n[0]}")}")'
    b = re.sub(r'\(uuid "[0-9a-f\-]+"\)', ru, b)
    if b.count(f'"{ref}"') != 2:
        raise SystemExit(f'unexpected state: template {old_ref} reference count')
    return b


def inserts(text):
    """[(insert position, new text)] for C31 / C32 and their wiring, built from the templates."""
    out = []
    pwr_s, pwr_e = symbol_block(text, PWR_TEMPLATE)
    lab_s, lab_e = top_item(text, r'^\t\(label "VOUT"\r\n\t\t\(at ' + re.escape(
        f'{fmt(LABEL_TEMPLATE_AT[0])} {fmt(LABEL_TEMPLATE_AT[1])} 0)'))
    wir_s, wir_e = top_item(text, re.escape(WIRE_TEMPLATE))
    pwr_t, lab_t, wir_t = text[pwr_s:pwr_e], text[lab_s:lab_e], text[wir_s:wir_e]
    pwr_new, lab_new, wir_new = [], [], []
    for ref, tref, (x, y), pref, net in NEW_CAPS:
        s, e = symbol_block(text, tref)
        tmpl = text[s:e]
        at0 = tuple(float(v) for v in re.search(r'\(at ([\d.\-]+) ([\d.\-]+) 0\)', tmpl).groups())
        out.append((e, new_symbol(tmpl, ref, tref, at0, (x, y), ref)))
        pwr_new.append(new_symbol(pwr_t, pref, PWR_TEMPLATE, PWR_TEMPLATE_AT, (x, y + PIN_OFFSET + STUB), pref))
        lab = shift_at(lab_t, x - LABEL_TEMPLATE_AT[0], y - PIN_OFFSET - STUB - LABEL_TEMPLATE_AT[1])
        lab = lab.replace('(label "VOUT"', f'(label "{net}"')
        lab_new.append(re.sub(r'\(uuid "[0-9a-f\-]+"\)', f'(uuid "{uid(ref + ":label")}")', lab))
        for k, (y0, y1) in enumerate(((y - PIN_OFFSET, y - PIN_OFFSET - STUB), (y + PIN_OFFSET, y + PIN_OFFSET + STUB))):
            w = wir_t.replace(WIRE_TEMPLATE, f'(xy {fmt(x)} {fmt(y0)}) (xy {fmt(x)} {fmt(y1)})')
            wir_new.append(re.sub(r'\(uuid "[0-9a-f\-]+"\)', f'(uuid "{uid(f"{ref}:wire{k}")}")', w))
    out += [(pwr_e, ''.join(pwr_new)), (lab_e, ''.join(lab_new)), (wir_e, ''.join(wir_new))]
    return out


def edit_fields(text, want_new):
    """The sheet with every CHANGES field at its new value; checks each holds old or new."""
    out, pos = [], 0
    for s, e, ref in bom14.symbol_blocks(text):
        out.append(text[pos:s])
        block = text[s:e]
        if ref in CHANGES:
            for name, (old, new) in CHANGES[ref].items():
                rx = bom14.prop_re(name)
                hits = rx.findall(block)
                if len(hits) != 1 or unesc(hits[0][1]) not in ((new,) if want_new else (old, new)):
                    raise SystemExit(f'unexpected state: {ref} {name} = {[unesc(h[1]) for h in hits]}')
                block = rx.sub(lambda m: m.group(1) + bom14.esc(new) + m.group(3), block, count=1)
        out.append(block)
        pos = e
    out.append(text[pos:])
    return ''.join(out)


def blank_fields(text):
    out, pos = [], 0
    for s, e, ref in bom14.symbol_blocks(text):
        out.append(text[pos:s])
        block = text[s:e]
        for name in CHANGES.get(ref, {}):
            block = bom14.prop_re(name).sub(lambda m: m.group(1) + m.group(3), block, count=1)
        out.append(block)
        pos = e
    out.append(text[pos:])
    return ''.join(out).replace(TITLE_NEW, TITLE_OLD)


def check_spec(md):
    errs = []
    spec7 = check_netlist.parse_netlist_table(md)
    for ref, ch in CHANGES.items():
        if spec7[ref]['value'] != ch[F_VALUE][1]:
            errs.append(f"SPEC 7 {ref} value {spec7[ref]['value']!r}, expected {ch[F_VALUE][1]!r}")
    for ref, tref, *_ in NEW_CAPS:
        if ref not in spec7 or spec7[ref]['value'] != spec7[tref]['value']:
            errs.append(f'SPEC 7 has no {ref} row with the {tref} value')
    header, rows = check_netlist._rows(check_netlist._section(md, check_netlist.PARTS_HEADING), 'Ref')
    col = {n: i for i, n in enumerate(header)}
    mpn = {r: row[col['MPN']] for row in rows for r in re.split(r'\s*,\s*', row[col['Ref']])}
    for ref, ch in CHANGES.items():
        if mpn.get(ref) != ch[F_MPN][1]:
            errs.append(f'SPEC 6 {ref} MPN {mpn.get(ref)!r}, expected {ch[F_MPN][1]!r}')
    for ref, tref, *_ in NEW_CAPS:
        if mpn.get(ref) != mpn.get(tref):
            errs.append(f'SPEC 6 {ref} not in the {tref} row')
    return errs


def build(text):
    refs = [r for *_, r in bom14.symbol_blocks(text)]
    present = [c[0] in refs for c in NEW_CAPS] + [c[3] in refs for c in NEW_CAPS]
    if all(present):
        if edit_fields(text, True) != text or TITLE_NEW not in text:
            raise SystemExit('unexpected state: C31 / C32 present but the fields or the title are not the target')
        return text
    if any(present):
        raise SystemExit('unexpected state: partly applied (some of C31, C32, #PWR27, #PWR28 present)')
    if text.count(TITLE_OLD) != 1:
        raise SystemExit('unexpected state: block title "BUCK 5.1 V" not found once')
    ins = sorted(inserts(text), reverse=True)
    new = text
    for pos, chunk in ins:
        new = new[:pos] + chunk + new[pos:]
    new = edit_fields(new, False).replace(TITLE_OLD, TITLE_NEW)
    return new


def check_result(old, new):
    stripped = new
    for ref, *_ in NEW_CAPS:
        s, e = symbol_block(stripped, ref)
        stripped = stripped[:s] + stripped[e:]
    for _, _, _, pref, _ in NEW_CAPS:
        s, e = symbol_block(stripped, pref)
        stripped = stripped[:s] + stripped[e:]
    for ref, *_ in NEW_CAPS:
        for tag in ('label', 'wire0', 'wire1'):
            s, e = top_item(stripped, re.escape(uid(f'{ref}:{tag}')))
            stripped = stripped[:s] + stripped[e:]
    if blank_fields(stripped) != blank_fields(old):
        raise SystemExit('check: the sheet changed beyond the inserted items and the listed fields')
    if '\n' in new.replace('\r\n', '') or '\r' in new.replace('\r\n', ''):
        raise SystemExit('check: line endings are not all CRLF')
    for ref, *_ in NEW_CAPS:
        if new.count(f'(reference "{ref}")') != 1:
            raise SystemExit(f'check: {ref} instance count')


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
    sim = SIM_SHEET.read_bytes().decode('utf-8')
    if sim.count(SIM_OLD) + sim.count(SIM_NEW) != 1:
        raise SystemExit('unexpected state: simulation.kicad_sch U8 stand-in .param line is neither old nor new')
    sim_new = sim.replace(SIM_OLD, SIM_NEW)
    new = build(text)
    if new == text and sim_new == sim:
        print('already applied')
        return 0
    if new != text:
        check_result(text, new)
    if a.dry_run:
        print(f'dry run: {len(new) - len(text):+d} chars; nothing written')
        return 0
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    (BACKUPS / f'{SHEET.stem}_{stamp}{SHEET.suffix}').write_bytes(SHEET.read_bytes())
    if sim_new != sim:
        (BACKUPS / f'{SIM_SHEET.stem}_{stamp}{SIM_SHEET.suffix}').write_bytes(SIM_SHEET.read_bytes())
        SIM_SHEET.write_bytes(sim_new.encode('utf-8'))
        print('applied: simulation.kicad_sch U8 stand-in parameters')
    if new == text:
        return 0
    SHEET.write_bytes(new.encode('utf-8'))
    print(f'applied: {", ".join(CHANGES)} fields, C31 / C32 added, title; backup {stamp}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
