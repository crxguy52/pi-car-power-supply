"""Post-schematic edit 02 (2026-11-04, overnight): small-signal passives 1206 -> 0805 HandSolder footprints.

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/02_0805_footprints.py

What: the "Footprint" property of the symbols in TO_0805 changes from the 1206 HandSolder footprint to the 0805
HandSolder one (SPEC 7 aliases `R_0805` / `C_0805`). Nothing else changes: text-level edit of exactly those
property values, CRLF line endings kept, every other byte untouched.

Why (SPEC 5 "Parts rule", SPEC 6, SPEC 7; DECISIONS 2026-11-04 "Small-signal passives 1206 -> 0805"): the placement
at 1206 did not fit the board (R11/D1/D4/D5 parked off-board, no routing room). The coordinator moved the
small-signal passives to 0805 HandSolder (allowed by the lead's hand-solder rule). KEEP_1206 stay 1206: power path,
pulse power (R13), wiring-fault current (R21), or capacitance at DC bias (C5/C6, C11, C14, C15/C16, C22-C24).

Guards: refuses if KiCad's lock file exists; each ref in TO_0805 and KEEP_1206 must be exactly one symbol with the
expected footprint (1206 or, for TO_0805, already 0805); a mix of 1206 and 0805 in TO_0805 (partial hand edit)
stops the script. Idempotent: if every TO_0805 symbol already carries the 0805 footprint it prints
"already applied" and writes nothing. Backup to pi_power_board-backups/ before writing.
Then: `pdm run verify-sch` (ERC + netlist vs SPEC 7, which reads the new footprints from SPEC 7).
"""
import datetime
import pathlib
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[2]
STEM = 'pi_power_board'
SHEET = ROOT / f'{STEM}.kicad_sch'
LOCK = ROOT / f'~{STEM}.kicad_sch.lck'
BACKUPS = ROOT / f'{STEM}-backups'

R_1206 = 'Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder'
C_1206 = 'Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder'
R_0805 = 'Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder'
C_0805 = 'Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder'
OLD = {'R': R_1206, 'C': C_1206}
NEW = {'R': R_0805, 'C': C_0805}

TO_0805 = ('R1 R2 R3 R4 R5 R6 R7 R8 R9 R11 R12 R14 R15 R16 R17 R18 R19 R20 R22 '
           'C2 C3 C4 C7 C8 C9 C13 C17 C18 C19 C20 C21').split()
KEEP_1206 = 'R13 R21 C5 C6 C11 C14 C15 C16 C22 C23 C24'.split()

SYMBOL_RE = re.compile(r'\r\n\t\(symbol\r\n.*?\r\n\t\)(?=\r\n)', re.S)     # top-level placed symbols only
REF_RE = re.compile(r'\(property "Reference" "([^"]*)"')
FP_RE = re.compile(r'(\(property "Footprint" ")([^"]*)(")')


def symbol_blocks(text):
    """{ref: [(start, end)]} of every placed symbol block."""
    out = {}
    for m in SYMBOL_RE.finditer(text):
        r = REF_RE.search(m.group(0))
        if r:
            out.setdefault(r.group(1), []).append((m.start(), m.end()))
    return out


def footprint_of(text, span):
    fps = FP_RE.findall(text[span[0]:span[1]])
    if len(fps) != 1:
        raise SystemExit(f'{len(fps)} Footprint properties in one symbol block: unexpected')
    return fps[0][1]


def main():
    if LOCK.exists():
        raise SystemExit(f'{LOCK.name} exists: close the schematic in KiCad first')
    raw = SHEET.read_bytes()
    text = raw.decode('utf-8')
    if text.count('\n') != text.count('\r\n'):
        raise SystemExit('sheet is not pure CRLF: unexpected (hand-saved sheets are CRLF)')
    blocks = symbol_blocks(text)
    for ref in TO_0805 + KEEP_1206:
        if len(blocks.get(ref, [])) != 1:
            raise SystemExit(f'{ref}: {len(blocks.get(ref, []))} symbol blocks (expected 1)')
    for ref in KEEP_1206:
        fp = footprint_of(text, blocks[ref][0])
        if fp != OLD[ref[0]]:
            raise SystemExit(f'{ref}: footprint {fp}, expected {OLD[ref[0]]} (kept at 1206)')
    state = {}
    for ref in TO_0805:
        fp = footprint_of(text, blocks[ref][0])
        if fp == OLD[ref[0]]:
            state[ref] = 'old'
        elif fp == NEW[ref[0]]:
            state[ref] = 'new'
        else:
            raise SystemExit(f'{ref}: unexpected footprint {fp}')
    if all(s == 'new' for s in state.values()):
        print(f'{SHEET.name}: already applied ({len(TO_0805)} symbols on 0805); nothing changed')
        return
    if any(s == 'new' for s in state.values()):
        raise SystemExit(f'partly applied (0805 already on {sorted(r for r, s in state.items() if s == "new")}): '
                         'unexpected state, check by hand')

    spans = sorted(blocks[r][0] + (r,) for r in TO_0805)
    out, pos = [], 0
    for start, end, ref in spans:
        block = text[start:end]
        new_block, n = FP_RE.subn(lambda m: m.group(1) + NEW[ref[0]] + m.group(3), block)
        if n != 1:
            raise SystemExit(f'{ref}: {n} footprint replacements: unexpected')
        out += [text[pos:start], new_block]
        pos = end
    out.append(text[pos:])
    new_text = ''.join(out)

    check = symbol_blocks(new_text)
    for ref in TO_0805:
        if footprint_of(new_text, check[ref][0]) != NEW[ref[0]]:
            raise SystemExit(f'{ref}: self-check failed')
    expected_delta = sum(len(NEW[r[0]]) - len(OLD[r[0]]) for r in TO_0805)
    if len(new_text) - len(text) != expected_delta:
        raise SystemExit('self-check failed: more than the footprint values changed')

    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_sch'
    shutil.copy2(SHEET, backup)
    print(f'backup {backup.relative_to(ROOT)}')
    SHEET.write_bytes(new_text.encode('utf-8'))
    print(f'{SHEET.name}: {len(TO_0805)} footprints 1206 -> 0805 ({", ".join(TO_0805)})')


if __name__ == '__main__':
    main()
