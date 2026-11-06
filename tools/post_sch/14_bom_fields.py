"""Post-schematic edit 14 (2026-11-05, phase 6 BOM): Manufacturer / MPN / Digi-Key PN / Description / Datasheet
fields on every board part, and J5's Value "GND ACC_N" -> "ACC_N GND".

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/14_bom_fields.py [--dry-run]

What and why (SPEC 6 "Parts", TODO "6 BOM"; the lead assembles 2 boards by hand from Digi-Key cut tape):
- Every board part (the 44 refs of SPEC 7: 39 parts + J1, J2, J4, J5, SW1; not the sim-only parts on
  simulation.kicad_sch, which is not touched, and not MH1-MH4, which have no symbol) gets the fields of PARTS below:
  Manufacturer, MPN, "Digi-Key PN" (the cut-tape packaging for SMD parts; U8's tube, whose cut tape is not stocked;
  bulk / tray for THT), Description, and Datasheet = ${KIPRJMOD}/ref/datasheets/<file> (J2: the Molex product page
  URL, its PDF download timed out). PARTS is the record; SPEC 6 carries the same MPN / Datasheet per ref
  (tools/check_netlist.py checks both) and the same Digi-Key PN (checked here against the SPEC table).
- Passives chosen in this phase: Vishay Dale CRCW e3 thick film (1 %, 100 ppm/K, AEC-Q200; 0805 0.125 W, 1206
  0.25 W; one datasheet with the single-pulse curve that R30 needs), KEMET X7R / C0G 0805, Cal-Chip GMC X7R
  (C8 and C22-C24 kept; C15 GMC31X7R106K50NT because the Samsung / TDK 10 uF 50 V X7R 1206 parts show 0 stock).
- J5 Value: "ACC_N GND" (project lead: after the 180 deg rotation the pins read in that order; SPEC 7 row J5).
- Nothing else changes: values (except J5), footprints, positions, uuids, Sim fields, pins and wires are kept.
  Existing field blocks keep their position and effects (only the value text changes); missing ones are inserted
  as hidden fields at the symbol's origin, in the format KiCad 10 writes, before the symbol's first Sim field or
  pin.

Guards: refuses if KiCad's lock file exists or the sheet is not CRLF. Each board ref must hold exactly SPEC 7's
footprint and value (J5: the old or the new value). Every field this script writes must hold either its pre-edit
state (PRE_ALLOWED: absent, empty, or the value the earlier scripts wrote) or the target; anything else stops.
"already applied" when the sheet equals the result. After the edit: everything outside the edited symbol blocks is
byte-identical, and inside them only the five fields (plus J5's Value) differ. SPEC 6's Digi-Key PN column must
equal PARTS. Backup to pi_power_board-backups/ first.
"""
import argparse
import datetime
import pathlib
import re
import shutil
import sys

TOOLS = pathlib.Path(__file__).resolve().parent.parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import check_netlist  # noqa: E402

SHEET = ROOT / 'pi_power_board.kicad_sch'
LOCK = ROOT / '~pi_power_board.kicad_sch.lck'
BACKUPS = ROOT / 'pi_power_board-backups'
SPEC = ROOT / 'docs' / 'SPEC.md'
NL = '\r\n'
KIPRJMOD = '${KIPRJMOD}/'
DS_DIR = 'ref/datasheets/'
URL_PREFIX = 'https://'
F_MFR, F_MPN, F_DK, F_DESC, F_DS, F_VALUE = 'Manufacturer', 'MPN', 'Digi-Key PN', 'Description', 'Datasheet', 'Value'
FIELDS = (F_MFR, F_MPN, F_DK, F_DESC, F_DS)
INSERT_ORDER = (F_MFR, F_MPN, F_DK)              # fields that may be missing (Datasheet, Description always exist)
J5_VALUE_OLD, J5_VALUE_NEW = 'GND ACC_N', 'ACC_N GND'

# Datasheet files (ref/datasheets/) shared by several rows
DS_CRCW = 'Vishay_CRCW_e3.pdf'
DS_X7R = 'KEMET_C1002_X7R.pdf'
DS_C0G = 'KEMET_C1003_C0G.pdf'
DS_GMC = 'CalChip_GMC_series.pdf'
DS_MOLEX_URL = 'https://www.molex.com/en-us/products/part-detail/484060001?display=pdf'

VISHAY_DALE, KEMET, CALCHIP = 'Vishay Dale', 'KEMET', 'Cal-Chip Electronics'
R0805 = 'Resistor, thick film, ±1 %, 0.125 W, ±100 ppm/K, 0805, AEC-Q200'
R1206 = 'Resistor, thick film, ±1 %, 0.25 W, ±100 ppm/K, 1206, AEC-Q200'

# refs: (manufacturer, MPN, Digi-Key PN, datasheet file or URL, description)
PARTS = {
    ('J1',): ('Phoenix Contact', '1727023', '277-1948-ND', 'Phoenix_MKDS1-3-3.81_1727023.pdf',
              'Terminal block, 3-pos, 3.81 mm pitch, screw, horizontal entry, THT (MKDS 1/3-3,81)'),
    ('J4', 'J5'): ('Phoenix Contact', '1727010', '277-1947-ND', 'Phoenix_MKDS1-2-3.81_1727010.pdf',
                   'Terminal block, 2-pos, 3.81 mm pitch, screw, horizontal entry, THT (MKDS 1/2-3,81)'),
    ('J2',): ('Molex', '0484060001', '0484060001-ND', DS_MOLEX_URL,
              'USB 3.0 Type-A receptacle, dual stacked, right angle, THT'),
    ('SW1',): ('Nidec Components', 'CAS-120TA', 'CAS120JCT-ND', 'Nidec_CAS.pdf',
               'Slide switch SPDT, SMD J-hook, taped, washable (Nidec CAS-120A)'),
    ('Q1',): ('Vishay Siliconix', 'SQD50P04-13L_GE3', 'SQD50P04-13L_GE3CT-ND', 'Vishay_SQD50P04-13L.pdf',
              'P-MOSFET -40 V, 22 mΩ at -4.5 V, AEC-Q101, DPAK (TO-252)'),
    ('U5',): ('Texas Instruments', 'CD4541BM96', '296-3536-1-ND', 'TI_CD4541B.pdf',
              'Programmable timer: RC oscillator + 16-stage counter, 3-18 V, -55 to 125 °C, SOIC-14'),
    ('Q5', 'Q6'): ('Nexperia', '2N7002BK,215', '1727-4789-1-ND', 'Nexperia_2N7002BK.pdf',
                   'N-MOSFET 60 V 350 mA, ESD-protected gate, SOT-23'),
    ('U8',): ('Texas Instruments', 'TPS54336ADDA', '296-41978-5-ND', 'TI_TPS54336A_SLVSCD5D.pdf',
              'Synchronous buck converter 4.5-28 V in, 3 A, SO PowerPAD-8 (DDA), tube'),
    ('L1',): ('Bourns', 'SRP1038A-100M', 'SRP1038A-100MCT-ND', 'Bourns_SRP1038A.pdf',
              'Inductor 10 µH ±20 %, shielded, I_sat 12 A, 30 mΩ max, 10 x 11 mm, AEC-Q200'),
    ('TVS1', 'TVS2'): ('Bourns', 'SMBJ16A', 'SMBJ16ABCT-ND', 'Bourns_SMBJ.pdf',
                       'TVS diode, unidirectional, V_RWM 16 V, 600 W (10/1000 µs), SMB'),
    ('D4', 'D5'): ('Vishay', '1N4148W-E3-08', '1N4148W-E3-08CT-ND', 'Vishay_1N4148W.pdf',
                   'Switching diode 1N4148W, 75 V, SOD-123'),
    ('D6',): ('onsemi', 'BAS116LT1G', 'BAS116LT1GOSCT-ND', 'onsemi_BAS116LT1.pdf',
              'Switching diode, low leakage, 75 V, SOT-23 (1 A, 3 K)'),
    ('D7',): ('Vishay', 'BZT52C5V1-E3-08', 'BZT52C5V1-E3-08CT-ND', 'Vishay_BZT52.pdf',
              'Zener diode 5.1 V, SOD-123'),
    ('D3',): ('Lite-On', 'LTST-C150KRKT', '160-1405-1-ND', 'LiteOn_LTST-C150KRKT.pdf', 'LED red, 1206'),
    ('R3',): (VISHAY_DALE, 'CRCW08055K10FKEA', '541-5.10KCCT-ND', DS_CRCW, '5.1 kΩ ' + R0805),
    ('R8',): (VISHAY_DALE, 'CRCW080522K0FKEA', '541-22.0KCCT-ND', DS_CRCW, '22 kΩ ' + R0805),
    ('R25',): (VISHAY_DALE, 'CRCW080527K0FKEA', '541-27.0KCCT-ND', DS_CRCW, '27 kΩ ' + R0805),
    ('R26',): (VISHAY_DALE, 'CRCW0805100KFKEA', '541-100KCCT-ND', DS_CRCW, '100 kΩ ' + R0805),
    ('R27',): (VISHAY_DALE, 'CRCW080539K2FKEA', '541-39.2KCCT-ND', DS_CRCW, '39.2 kΩ ' + R0805),
    ('R28',): (VISHAY_DALE, 'CRCW080578K7FKEA', '541-78.7KCCT-ND', DS_CRCW, '78.7 kΩ ' + R0805),
    ('R29',): (VISHAY_DALE, 'CRCW080547K0FKEA', '541-47.0KCCT-ND', DS_CRCW, '47 kΩ ' + R0805),
    ('R30',): (VISHAY_DALE, 'CRCW12061K30FKEA', '541-1.30KFCT-ND', DS_CRCW, '1.3 kΩ ' + R1206),
    ('R17', 'R31'): (VISHAY_DALE, 'CRCW080510K0FKEA', '541-10.0KCCT-ND', DS_CRCW, '10.0 kΩ ' + R0805),
    ('R14',): (VISHAY_DALE, 'CRCW0805220KFKEA', '541-220KCCT-ND', DS_CRCW, '220 kΩ ' + R0805),
    ('R15',): (VISHAY_DALE, 'CRCW0805180KFKEA', '541-180KCCT-ND', DS_CRCW, '180 kΩ ' + R0805),
    ('R16',): (VISHAY_DALE, 'CRCW080553K6FKEA', '541-53.6KCCT-ND', DS_CRCW, '53.6 kΩ ' + R0805),
    ('R18',): (VISHAY_DALE, 'CRCW08055K49FKEA', '541-5.49KCCT-ND', DS_CRCW, '5.49 kΩ ' + R0805),
    ('R21',): (VISHAY_DALE, 'CRCW12061K50FKEA', '541-1.50KFCT-ND', DS_CRCW, '1.5 kΩ ' + R1206),
    ('C29',): (KEMET, 'C0805C103F5GACTU', '399-C0805C103F5GACTUCT-ND', DS_C0G,
               'Capacitor 10 nF ±1 % 50 V C0G, 0805'),
    ('C17', 'C18', 'C30'): (KEMET, 'C0805C104K5RACTU', '399-C0805C104K5RACTUCT-ND', DS_X7R,
                            'Capacitor 100 nF ±10 % 50 V X7R, 0805'),
    ('C19',): (KEMET, 'C0805C103K5RACTU', '399-C0805C103K5RACTUCT-ND', DS_X7R, 'Capacitor 10 nF ±10 % 50 V X7R, 0805'),
    ('C20',): (KEMET, 'C0805C153K5RACTU', '399-C0805C153K5RACTUCT-ND', DS_X7R, 'Capacitor 15 nF ±10 % 50 V X7R, 0805'),
    ('C8',): (CALCHIP, 'GMC21X7R105K50NT', '4713-GMC21X7R105K50NTCT-ND', DS_GMC, 'Capacitor 1 µF ±10 % 50 V X7R, 0805'),
    ('C15',): (CALCHIP, 'GMC31X7R106K50NT', '4713-GMC31X7R106K50NTCT-ND', DS_GMC,
               'Capacitor 10 µF ±10 % 50 V X7R, 1206'),
    ('C22', 'C23', 'C24'): (CALCHIP, 'GMC32X7R476K10NT', '4713-GMC32X7R476K10NTCT-ND', DS_GMC,
                            'Capacitor 47 µF ±10 % 10 V X7R, 1210'),
}

# Pre-edit field states this script accepts besides "absent" / "empty" (what scripts 03-13 wrote)
PRE_ALLOWED = {
    F_MFR: {'Cal-Chip Electronics', 'KEMET', 'Lite-On', 'Vishay', 'onsemi', 'Phoenix Contact', 'Molex', 'Bourns',
            'Vishay Siliconix', 'Nexperia', 'Nidec Components', 'Texas Instruments'},
    F_DESC: {'Unpolarized capacitor', 'Light emitting diode', '75V 0.15A Fast Switching Diode, SOD-123', 'Zener diode',
             'Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)',
             'Generic screw terminal, single row, 01x03, script generated (kicad-library-utils/schlib/autogen/connector/)',
             'USB 3.0 A connector, stacked', 'Inductor', 'P-MOSFET transistor, gate/drain/source',
             'Switch, single pole double throw', 'Resistor, US symbol'},
    F_DS: {'https://www.molex.com/en-us/products/part-detail/484060001'},
}
PRE_PREFIX = {F_DESC: ('0.115A Id, 60V Vds, N-Channel MOSFET', '250V, 0.4A, High-speed Switching Diode',
                       '20V, Programmable Timer', '4.5V to 28V Input, 3A, Synchronous Step-')}


def target(ref):
    for refs, (mfr, mpn, dk, ds, desc) in PARTS.items():
        if ref in refs:
            return {F_MFR: mfr, F_MPN: mpn, F_DK: dk, F_DESC: desc,
                    F_DS: ds if ds.startswith(URL_PREFIX) else KIPRJMOD + DS_DIR + ds}
    return None


def board_refs():
    return [r for refs in PARTS for r in refs]


def symbol_blocks(text):
    """[(start, end, ref)] of every placed symbol block of the root sheet (not lib_symbols)."""
    out = []
    for m in re.finditer(r'\n\t\(symbol\r\n', text):
        s = m.start() + 1
        e = text.index('\n\t)\r\n', s) + len('\n\t)\r\n')
        r = re.search(r'\(property "Reference" "([^"]*)"', text[s:e])
        if r:
            out.append((s, e, r.group(1)))
    return out


def esc(v):
    return v.replace('\\', '\\\\').replace('"', '\\"')


def prop_re(name):
    return re.compile(r'(\t\t\(property "' + re.escape(name) + r'" ")((?:[^"\\]|\\.)*)(")')


def field_block(name, value, at):
    return (f'\t\t(property "{name}" "{esc(value)}"{NL}\t\t\t(at {at} 0){NL}\t\t\t(hide yes){NL}'
            f'\t\t\t(show_name no){NL}\t\t\t(do_not_autoplace no){NL}\t\t\t(effects{NL}\t\t\t\t(font{NL}'
            f'\t\t\t\t\t(size 1.27 1.27){NL}\t\t\t\t){NL}\t\t\t){NL}\t\t){NL}')


def pre_ok(name, value, want):
    return (value in ('', want) or value in PRE_ALLOWED.get(name, ())
            or any(value.startswith(p) for p in PRE_PREFIX.get(name, ()))
            or (name == F_DS and value.startswith(KIPRJMOD + DS_DIR)) or (name == F_DS and value == DS_MOLEX_URL))


def edit_block(block, ref, spec7):
    """New text of one symbol block; stops on an unexpected state."""
    want = target(ref)
    fp = re.search(r'\(property "Footprint" "([^"]*)"', block).group(1)
    val = prop_re(F_VALUE).search(block).group(2)
    if fp != spec7['footprint']:
        raise SystemExit(f'unexpected state: {ref} footprint {fp!r}, SPEC 7 {spec7["footprint"]!r}')
    vals = (J5_VALUE_OLD, J5_VALUE_NEW) if ref == 'J5' else (spec7['value'],)
    if val not in vals:
        raise SystemExit(f'unexpected state: {ref} value {val!r}, expected one of {vals}')
    if ref == 'J5':
        block = prop_re(F_VALUE).sub(lambda m: m.group(1) + J5_VALUE_NEW + m.group(3), block, count=1)
    at = re.search(r'\n\t\t\(at ([-\d.]+ [-\d.]+)', block).group(1)
    for name in FIELDS:
        rx = prop_re(name)
        hits = rx.findall(block)
        if len(hits) > 1:
            raise SystemExit(f'unexpected state: {ref} has {len(hits)} {name} fields')
        if hits:
            cur = hits[0][1].replace('\\"', '"').replace('\\\\', '\\')
            if not pre_ok(name, cur, want[name]):
                raise SystemExit(f'unexpected state: {ref} {name} = {cur!r} (neither pre-edit nor target)')
            block = rx.sub(lambda m: m.group(1) + esc(want[name]) + m.group(3), block, count=1)
        else:
            if name not in INSERT_ORDER:
                raise SystemExit(f'unexpected state: {ref} has no {name} field')
            m = re.search(r'\t\t\(property "Sim\.|\t\t\(pin "', block)
            block = block[:m.start()] + field_block(name, want[name], at) + block[m.start():]
    return block


def build(text, spec):
    blocks = symbol_blocks(text)
    refs = [r for _, _, r in blocks]
    for ref in board_refs():
        if ref not in spec:
            raise SystemExit(f'unexpected state: {ref} not in SPEC 7')
        if ref not in refs:
            raise SystemExit(f'unexpected state: {ref} not on the sheet')
    missing = sorted(set(spec) - set(board_refs()))
    if missing:
        raise SystemExit(f'unexpected state: SPEC 7 refs without a PARTS entry: {missing}')
    out, pos = [], 0
    for s, e, ref in blocks:
        out.append(text[pos:s])
        out.append(edit_block(text[s:e], ref, spec[ref]) if ref in spec else text[s:e])
        pos = e
    out.append(text[pos:])
    return ''.join(out)


def strip_fields(block):
    """The block without the five field blocks and the Value text: what must not change."""
    for name in FIELDS:
        block = re.sub(r'\t\t\(property "' + re.escape(name) + r'" "(?:[^"\\]|\\.)*"\r\n.*?\r\n\t\t\)\r\n', '',
                       block, flags=re.S)
    return prop_re(F_VALUE).sub(lambda m: m.group(1) + m.group(3), block)


def check_result(old, new):
    a, b = symbol_blocks(old), symbol_blocks(new)
    if [r for *_, r in a] != [r for *_, r in b]:
        raise SystemExit('check: symbol block list changed')
    gaps_a = [old[e0:s1] for (_, e0, _), (s1, _, _) in zip(a, a[1:])] + [old[:a[0][0]], old[a[-1][1]:]]
    gaps_b = [new[e0:s1] for (_, e0, _), (s1, _, _) in zip(b, b[1:])] + [new[:b[0][0]], new[b[-1][1]:]]
    if gaps_a != gaps_b:
        raise SystemExit('check: text outside the symbol blocks changed')
    for (s0, e0, ref), (s1, e1, _) in zip(a, b):
        x, y = old[s0:e0], new[s1:e1]
        if strip_fields(x) != strip_fields(y):
            raise SystemExit(f'check: {ref} changed beyond the BOM fields')
        if ref != 'J5' and prop_re(F_VALUE).search(x).group(2) != prop_re(F_VALUE).search(y).group(2):
            raise SystemExit(f'check: {ref} value changed')
        want = target(ref)
        if want:
            for name in FIELDS:
                got = prop_re(name).findall(y)
                if len(got) != 1 or got[0][1] != esc(want[name]):
                    raise SystemExit(f'check: {ref} {name} not the target')
    if '\n' in new.replace('\r\n', '') or '\r' in new.replace('\r\n', ''):
        raise SystemExit('check: line endings are not all CRLF')


def check_spec_dk(md):
    """SPEC 6 Digi-Key PN / Manufacturer per ref = PARTS."""
    header, rows = check_netlist._rows(check_netlist._section(md, check_netlist.PARTS_HEADING), 'Ref')
    col = {name: i for i, name in enumerate(header)}
    errs = []
    for row in rows:
        for ref in re.split(r'\s*,\s*', row[col['Ref']]):
            want = target(ref)
            if want is None:
                errs.append(f'SPEC 6 ref {ref} not in PARTS')
                continue
            for c, f in (('Digi-Key PN', F_DK), ('Manufacturer', F_MFR), ('MPN', F_MPN)):
                if row[col[c]] != want[f]:
                    errs.append(f'SPEC 6 {ref} {c} {row[col[c]]!r}, PARTS {want[f]!r}')
    return errs


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv[1:])
    if LOCK.exists():
        raise SystemExit(f'{LOCK.name} exists: close the schematic in KiCad first')
    raw = SHEET.read_bytes()
    text = raw.decode('utf-8')
    if text.count('\r\n') != text.count('\n'):
        raise SystemExit('unexpected state: the sheet is not CRLF')
    md = SPEC.read_text(encoding='utf-8')
    spec = check_netlist.parse_netlist_table(md)
    errs = check_spec_dk(md)
    if errs:
        raise SystemExit('SPEC 6 differs from PARTS:\n  ' + '\n  '.join(errs))
    new = build(text, spec)
    if new == text:
        print('already applied')
        return 0
    check_result(text, new)
    if a.dry_run:
        print(f'dry run: {len(new) - len(text):+d} chars, {len(board_refs())} refs; nothing written')
        return 0
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    shutil.copy2(SHEET, BACKUPS / f'{SHEET.stem}_{stamp}{SHEET.suffix}')
    SHEET.write_bytes(new.encode('utf-8'))
    print(f'applied: BOM fields on {len(board_refs())} refs, J5 value {J5_VALUE_NEW!r}; backup {stamp}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
