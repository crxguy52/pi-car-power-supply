"""15: final reconcile of the board fields with the schematic (SPEC 7 "Parts", SPEC "Board"; 2026-11-05).

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/15_sync_fields.py`;
`--dry-run` prints the changes and never saves the master):

- exports a fresh netlist from the schematic (kicad-cli, kicadxml) to NETLIST;
- for every schematic-linked board footprint (exclude_from_board symbols, i.e. the simulation sheet, skipped),
  copies the symbol's Value, Datasheet, Description and the symbol fields (Manufacturer, MPN, Digi-Key PN,
  Sim.*) onto the footprint, like "Update PCB from Schematic" with "update fields". KiCad 10 parity compares
  Sim.* too (once the BOM fields were in, it reported the first missing Sim.* field per part). A missing field
  is inserted hidden on F.Fab, so no silkscreen changes; an existing field keeps its layer, position and
  visibility and only gets the new text;
- checks each footprint's Path against the netlist tstamps (sheet path + symbol uuid; 07 found a stale D4
  Path that parity doesn't report) and re-links a stale one; Sheetname / Sheetfile likewise.

Why: the BOM phase (A18) added Digi-Key PN / Manufacturer to the symbols and changed D3 (LED part) and the
J5 value (pin order after 05's 180 deg turn); DRC parity reported footprint_symbol_field_mismatch per
missing field and footprint_symbol_mismatch for the D3 / J5 values.

Untouched: positions, orientations, sides, footprints, pads and nets, copper, zones, the outline, every text
outside the footprint fields. The script verifies that after the edit (STATE per footprint, pad nets).

Guards: stops on KiCad lock files; on a board footprint set other than the netlist parts + mounting holes;
on a footprint id or a pad net that differs from the netlist (those are not this script's job); on a
visible Value field on a silkscreen layer (its text change would change the silk). Idempotent: on a
matching board it prints "already applied" and saves nothing. Backup to pi_power_board-backups/ first.
"""
import datetime
import pathlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import toolchain  # noqa: E402

STEM = 'pi_power_board'
PCB = ROOT / f'{STEM}.kicad_pcb'
SCH = ROOT / f'{STEM}.kicad_sch'
NETLIST = ROOT / 'build' / 'netlist.xml'
BACKUPS = ROOT / f'{STEM}-backups'
KICAD_TIMEOUT_S = 300.0
UNLINKED_OK = re.compile(r'^MH\d+$')             # mounting holes: board-only, untouched
SKIP_FIELDS = {'Footprint', 'Reference', 'Value'}
SILK_LAYERS = (pcbnew.F_SilkS, pcbnew.B_SilkS)


def export_netlist():
    NETLIST.parent.mkdir(exist_ok=True)
    r = subprocess.run([str(toolchain.Toolchain().kicad_cli), 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(NETLIST), str(SCH)], capture_output=True, text=True, timeout=KICAD_TIMEOUT_S)
    if r.returncode or not NETLIST.exists():
        raise SystemExit(f'netlist export failed: {r.stdout}{r.stderr}')


def read_netlist():
    root = ET.parse(NETLIST).getroot()
    comps = {}
    for c in root.find('components'):
        props = {p.get('name'): p.get('value') for p in c.findall('property')}
        if 'exclude_from_board' in props:
            continue                             # simulation-sheet parts: not on the board
        fields = {}
        for f in (c.find('fields') if c.find('fields') is not None else []):
            name = f.get('name')
            if name not in SKIP_FIELDS:
                fields[name] = f.text or ''
        fields.setdefault('Datasheet', c.findtext('datasheet') or '')
        fields.setdefault('Description', c.findtext('description') or '')
        comps[c.get('ref')] = {
            'value': c.findtext('value'), 'footprint': c.findtext('footprint'),
            'paths': [c.find('sheetpath').get('tstamps') + u for u in c.findtext('tstamps').split()],
            'sheetname': props.get('Sheetname', ''), 'sheetfile': props.get('Sheetfile', ''),
            'fields': fields}
    pin_net = {}
    for n in root.find('nets'):
        for node in n.findall('node'):
            pin_net[(node.get('ref'), node.get('pin'))] = n.get('name')
    return comps, pin_net


def state(fp):
    """Everything this script must not change."""
    pos = fp.GetPosition()
    return (pos.x, pos.y, fp.GetOrientationDegrees(), fp.GetLayer(), fp.GetFPIDAsString(), fp.IsLocked(),
            tuple((p.GetNumber(), p.GetPosition().x, p.GetPosition().y, p.GetNetname()) for p in fp.Pads()))


def plan(board, comps, pin_net):
    """List of (ref, kind, name, old, new) changes; stops on any state this script doesn't own."""
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    extra = sorted(r for r in set(fps) - set(comps) if not UNLINKED_OK.match(r))
    missing = sorted(set(comps) - set(fps))
    if extra or missing:
        raise SystemExit(f'footprint set differs from the netlist: extra {extra}, missing {missing}')
    changes = []
    for ref in sorted(comps):
        fp, comp = fps[ref], comps[ref]
        if fp.GetFPIDAsString() != comp['footprint']:
            raise SystemExit(f'{ref}: footprint {fp.GetFPIDAsString()} != schematic {comp["footprint"]}')
        for p in fp.Pads():
            want = pin_net.get((ref, p.GetNumber()), '')
            if p.GetNumber() and p.GetNetname() != want:
                raise SystemExit(f'{ref} pad {p.GetNumber()}: net {p.GetNetname()!r} != netlist {want!r}')
        path = fp.GetPath().AsString()
        if path not in comp['paths']:
            changes.append((ref, 'path', 'Path', path, comp['paths'][0]))
        if fp.GetSheetname() != comp['sheetname']:
            changes.append((ref, 'sheet', 'Sheetname', fp.GetSheetname(), comp['sheetname']))
        if fp.GetSheetfile() != comp['sheetfile']:
            changes.append((ref, 'sheet', 'Sheetfile', fp.GetSheetfile(), comp['sheetfile']))
        if fp.GetValue() != comp['value']:
            vf = fp.GetField('Value')
            if vf.IsVisible() and vf.GetLayer() in SILK_LAYERS:
                raise SystemExit(f'{ref}: Value is visible on silkscreen; a text change would change the silk')
            changes.append((ref, 'value', 'Value', fp.GetValue(), comp['value']))
        for name, text in comp['fields'].items():
            if not fp.HasField(name):
                changes.append((ref, 'insert', name, None, text))
            elif fp.GetFieldText(name) != text:
                changes.append((ref, 'update', name, fp.GetFieldText(name), text))
    return fps, changes


def apply(fps, changes):
    for ref, kind, name, _old, new in changes:
        fp = fps[ref]
        if kind == 'path':
            fp.SetPath(pcbnew.KIID_PATH(new))
        elif name == 'Sheetname':
            fp.SetSheetname(new)
        elif name == 'Sheetfile':
            fp.SetSheetfile(new)
        elif kind == 'value':
            fp.SetValue(new)
        elif kind == 'insert':
            fp.SetField(name, new)
            field = fp.GetField(name)
            field.SetVisible(False)
            field.SetLayer(pcbnew.F_Fab)
        else:
            fp.SetField(name, new)


def main(argv):
    dry_run = '--dry-run' in argv
    locks = sorted(ROOT.glob('~*.lck'))
    if locks:
        raise SystemExit(f'KiCad lock files present (close KiCad first): {[p.name for p in locks]}')
    export_netlist()
    comps, pin_net = read_netlist()
    board = pcbnew.LoadBoard(str(PCB))
    fps, changes = plan(board, comps, pin_net)
    if not changes:
        print(f'already applied: {len(comps)} footprints match the schematic fields, values and Paths; nothing saved')
        return 0
    before = {r: state(fp) for r, fp in fps.items()}
    kinds = {}
    for ref, kind, name, old, new in changes:
        kinds[kind] = kinds.get(kind, 0) + 1
        print(f'{ref:6s} {kind:6s} {name:12s} {old!r} -> {new!r}')
    apply(fps, changes)
    after = {r: state(fp) for r, fp in fps.items()}
    moved = sorted(r for r in before if before[r] != after[r])
    if moved:
        raise SystemExit(f'protected state changed on {moved}: nothing saved')
    _fps2, left = plan(board, comps, pin_net)
    if left:
        raise SystemExit(f'{len(left)} changes still pending after apply: {left[:3]}; nothing saved')
    print('changes by kind: ' + ', '.join(f'{k} {n}' for k, n in sorted(kinds.items())))
    if dry_run:
        print('--dry-run: nothing saved')
        return 0
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_pcb'
    shutil.copy2(PCB, backup)
    print(f'backup {backup.relative_to(ROOT)}')
    pcbnew.SaveBoard(str(PCB), board)
    print(f'saved {PCB.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
