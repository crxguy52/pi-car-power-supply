"""Remove the one dangling wire stub left by the project lead's layout tidy-up.

What: deletes the wire with uuid DANGLING_WIRE_UUID, from (44.45, 73.66) to (46.99, 73.66) mm,
whose ends connect to nothing (ERC: wire_dangling, unconnected_wire_endpoint).
Why: the project lead rearranged the sheet for legibility in a copy of the project
(2026-11-05); the master took that layout (netlist, values, footprints, fields and symbol
UUIDs identical to the previous master). The rearrangement left this orphan stub.
SPEC: no design change (section 7 unchanged).

Guarded: refuses if the schematic is open in KiCad, stops unless exactly one wire with that
uuid and those end points exists. Idempotent: a second run reports "already applied".
Text-level edit; line endings kept.
"""
import pathlib
import re
import shutil
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCH = ROOT / 'pi_power_board.kicad_sch'
LOCK = ROOT / '~pi_power_board.kicad_sch.lck'
BACKUPS = ROOT / 'pi_power_board-backups'
DANGLING_WIRE_UUID = '221f0bfc-8038-5cdd-bbbf-7eb3c40f33ad'
END_POINTS = '(xy 46.99 73.66) (xy 44.45 73.66)'


def main():
    if LOCK.exists():
        sys.exit(f'refusing: {LOCK.name} exists (schematic open in KiCad)')
    raw = SCH.read_bytes()
    newline = b'\r\n' if b'\r\n' in raw else b'\n'
    text = raw.decode('utf-8')
    if DANGLING_WIRE_UUID not in text:
        print('already applied')
        return
    nl = newline.decode()
    pattern = re.compile(
        r'\t\(wire' + re.escape(nl) + r'(?:(?!\t\(wire).)*?\(uuid "' + DANGLING_WIRE_UUID + r'"\)'
        + re.escape(nl) + r'\t\)' + re.escape(nl), re.S)
    found = pattern.findall(text)
    if len(found) != 1 or END_POINTS not in found[0]:
        sys.exit(f'unexpected state: {len(found)} matching wire blocks; nothing written')
    BACKUPS.mkdir(exist_ok=True)
    stamp = time.strftime('%Y-%m-%d_%H%M%S')
    shutil.copy2(SCH, BACKUPS / f'{SCH.stem}_{stamp}{SCH.suffix}')
    SCH.write_bytes(pattern.sub('', text, count=1).encode('utf-8'))
    print('removed dangling wire', DANGLING_WIRE_UUID)


if __name__ == '__main__':
    main()
