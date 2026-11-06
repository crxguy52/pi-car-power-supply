"""01: update pi_power_board.kicad_pcb from the signed-off schematic (SPEC 7), like "Update PCB from Schematic".

What (KiCad python, run under timeout from the project root: `python.exe -I tools/post_route/01_update_from_schematic.py`):

- exports the schematic netlist (kicad-cli, kicadxml) to build/netlist.xml;
- removes the footprints deleted from the schematic: exactly REMOVED (K1, U2, R10; C10 never reached the board);
  the mounting holes (no schematic link) are left untouched;
- replaces every schematic-linked footprint with a fresh copy of its schematic footprint from the library
  (KiCad 10 standard libraries, project library `pipwr` = lib/pi_power_board.pretty). This swaps the changed
  footprints (U3 SOT-23-5_HandSoldering, D1/D2 SOD-123, J1/J4/J5 Metz -> Phoenix MKDS, U8 -> pipwr DDA hand-solder)
  and clears the KiCad 9 -> 10 library drift (lib_footprint_mismatch). Position, orientation, side and lock state
  are kept;
- adds the new footprints (SPEC 7 "New") in a staging grid left of the board, for 02_placement.py;
- sets Path (/sheet-uuid/symbol-uuid; a multi-unit symbol keeps the board's existing unit uuid), Sheetname,
  Sheetfile, Value and the symbol fields (Manufacturer, MPN, Datasheet, Description; hidden, F.Fab);
- assigns every pad's net from the netlist (no-connect pins get KiCad's single-pad `unconnected-(...)` nets);
  pads the netlist doesn't name (mounting holes) get no net. Unused old nets are dropped;
- reseeds the uuids of every footprint it wrote (uuid5 from the reference), so a re-generation is reproducible.

Why: the board still carried the relay design (K1, U2 TPL7407LA, Metz terminals): DRC parity reported 44
missing_footprint, 87 net_conflict, 27 footprint_symbol_mismatch. SPEC 7 is the netlist; the schematic implements it.

Hard constraints (project lead, overnight run 2026-11-04): Edge.Cuts, MH1-MH4, J1/J2/J4/J5 positions, orientations
and pad coordinates, the lead's drawings and rule areas never change: tools/check_fixed.py runs on the result, and
the script refuses to save if a J1/J2/J4/J5 pad would move (> PAD_TOL_NM). J1/J4/J5: the Phoenix and Metz KiCad
footprints both have pad 1 at the origin, the row along +x at 3.81 mm and the wire entry on the +y face (body
-3.7/+3.6 mm about the pad row; Phoenix 1727010 drawing: the pins sit 3.6 mm from the wire-entry face; a scratch
3D render of the Phoenix footprint shows the openings on +y), so the same position and orientation keep every pad
and the wire-entry side.

Guards: stops on KiCad lock files, on a footprint set other than expected, on a missing library footprint, on a
netlist pin with no pad. Idempotent: on a board that already matches the netlist (footprint ids, fields, nets) it
prints "already applied" and saves nothing. Backup to pi_power_board-backups/ before saving.
"""
import datetime
import pathlib
import re
import shutil
import subprocess
import sys
import uuid
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
PROJECT_LIBS = {'pipwr': ROOT / 'lib' / 'pi_power_board.pretty'}
REMOVED = {'K1', 'U2', 'R10'}                    # SPEC 7 "Removed" that are on the board
UNLINKED_OK = re.compile(r'^MH\d+$')             # mounting holes: board-only, untouched
FIXED_PADS = ('J1', 'J2', 'J4', 'J5')
PAD_RENAMES = {'J2': {'19': 'SH'}}
PAD_TOL_NM = 1000
KICAD_TIMEOUT_S = 300.0
STAGE_X0_MM, STAGE_Y0_MM = 60.0, 60.0            # staging grid for new parts, left of the board
STAGE_PITCH_MM = 8.0
STAGE_COLS = 7
UUID_NS = uuid.uuid5(uuid.NAMESPACE_URL, 'pi-car-power-supply/tools/post_route/01_update_from_schematic')
SKIP_FIELDS = {'Footprint'}

LIB_IO = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)   # one plugin for the run (lessons doc)


def std_fp_dir():
    return pathlib.Path(toolchain.Toolchain().kicad_cli).parent.parent / 'share' / 'kicad' / 'footprints'


def load_lib_fp(fpid):
    nick, name = fpid.split(':')
    lib = PROJECT_LIBS.get(nick, std_fp_dir() / f'{nick}.pretty')
    fp = LIB_IO.FootprintLoad(str(lib), name, False)
    if fp is None:
        raise SystemExit(f'{fpid}: not found in {lib}')
    fp.SetFPID(pcbnew.LIB_ID(nick, name))
    return fp


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
        sp = c.find('sheetpath').get('tstamps')
        props = {p.get('name'): p.get('value') for p in c.findall('property')}
        fields = {f.get('name'): (f.text or '') for f in c.find('fields')}
        comps[c.get('ref')] = {'value': c.findtext('value'), 'footprint': c.findtext('footprint'),
                               'sheet': sp, 'uuids': c.findtext('tstamps').split(), 'props': props,
                               'fields': {k: v for k, v in fields.items() if k not in SKIP_FIELDS}}
    pin_net = {}
    for n in root.find('nets'):
        for node in n.findall('node'):
            pin_net[(node.get('ref'), node.get('pin'))] = n.get('name')
    return comps, pin_net


def want_path(comp, existing):
    """KIID path; a multi-unit symbol keeps the unit uuid the board already uses."""
    if existing is not None:
        cur = existing.GetPath().AsString()
        for u in comp['uuids']:
            if cur == comp['sheet'] + u:
                return cur
    return comp['sheet'] + comp['uuids'][0]


def fp_matches(fp, comp, pin_net):
    """True if the board footprint already carries the schematic footprint, fields and pad nets."""
    if fp.GetFPIDAsString() != comp['footprint'] or fp.GetValue() != comp['value']:
        return False
    for k, v in comp['fields'].items():
        if not fp.HasField(k) or fp.GetFieldText(k) != v:
            return False
    ref = fp.GetReference()
    for p in fp.Pads():
        if p.GetNetname() != pin_net.get((ref, p.GetNumber()), ''):
            return False
    return True


def apply_fields(fp, ref, comp, path):
    fp.SetReference(ref)
    fp.SetValue(comp['value'])
    fp.SetPath(pcbnew.KIID_PATH(path))
    fp.SetSheetname(comp['props'].get('Sheetname', ''))
    fp.SetSheetfile(comp['props'].get('Sheetfile', ''))
    for k, v in comp['fields'].items():
        fp.SetField(k, v)
        f = fp.GetField(k)
        f.SetVisible(False)
        if k not in ('Datasheet', 'Description'):
            f.SetLayer(pcbnew.F_Fab)
    fp.SetDNP('dnp' in comp['props'])
    fp.SetExcludedFromBOM('exclude_from_bom' in comp['props'])


def pad_coords(fp):
    renames = PAD_RENAMES.get(fp.GetReference(), {})
    return sorted((renames.get(p.GetNumber(), p.GetNumber()), p.GetPosition().x, p.GetPosition().y)
                  for p in fp.Pads())


def same_pads(a, b):
    return len(a) == len(b) and all(x[0] == y[0] and abs(x[1] - y[1]) <= PAD_TOL_NM and abs(x[2] - y[2]) <= PAD_TOL_NM
                                    for x, y in zip(a, b))


def reseed_uuids(text, refs):
    """Replace every (uuid ...) inside the (footprint ...) blocks of `refs` with uuid5(ref, index)."""
    out, pos = [], 0
    for m in re.finditer(r'\n\t\(footprint "', text):
        start = m.start() + 1
        depth, i, in_str = 0, start, False
        while True:
            ch = text[i]
            if in_str:
                if ch == '\\':
                    i += 1
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        block = text[start:i + 1]
        ref = re.search(r'\(property "Reference" "([^"]*)"', block).group(1)
        if ref in refs:
            count = iter(range(10 ** 6))
            block = re.sub(r'\(uuid "[0-9a-f-]+"\)',
                           lambda _m: f'(uuid "{uuid.uuid5(UUID_NS, f"{ref}/{next(count)}")}")', block)
        out.append(text[pos:start])
        out.append(block)
        pos = i + 1
    out.append(text[pos:])
    return ''.join(out)


def resave():
    """Load and save once more: KiCad orders footprints by uuid on save, so the order follows the seeded uuids."""
    pcbnew.SaveBoard(str(PCB), pcbnew.LoadBoard(str(PCB)))


def main():
    locks = sorted(ROOT.glob('~*.lck'))
    if locks:
        raise SystemExit(f'KiCad lock files present ({[p.name for p in locks]}): close KiCad first')
    export_netlist()
    comps, pin_net = read_netlist()
    board = pcbnew.LoadBoard(str(PCB))
    fps = {f.GetReference(): f for f in board.GetFootprints()}

    extra = {r for r, f in fps.items() if r not in comps and not UNLINKED_OK.match(r)}
    if extra and extra != REMOVED:
        raise SystemExit(f'unexpected board-only footprints {sorted(extra)} (expected {sorted(REMOVED)} or none)')
    todo = [r for r in sorted(comps) if r not in fps or not fp_matches(fps[r], comps[r], pin_net)]
    if not extra and not todo:
        print('already applied: every footprint, field and pad net matches the schematic; nothing saved')
        return
    first_run = bool(extra)
    if not first_run and any(r not in fps for r in todo):
        raise SystemExit(f'parts missing after the first run: {[r for r in todo if r not in fps]}: '
                         'update by hand or with a new script')

    before = {r: pad_coords(fps[r]) for r in FIXED_PADS}
    removed = []    # removed footprints stay referenced until the save: a garbage-collected proxy of a removed
    for r in sorted(extra):     # footprint breaks SWIG's FOOTPRINT typing for the rest of the run (KiCad 10)
        removed.append(fps.pop(r))
        board.Remove(removed[-1])

    nets = {}
    for name in sorted(set(pin_net.values())):
        n = board.FindNet(name)
        if n is None:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
        nets[name] = n

    written, staged = [], 0
    for ref in (sorted(comps) if first_run else todo):
        comp = comps[ref]
        old = fps.get(ref)
        fp = load_lib_fp(comp['footprint'])
        fp.SetParent(board)
        apply_fields(fp, ref, comp, want_path(comp, old))
        if old is not None:
            if old.IsFlipped():
                fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
            fp.SetOrientation(old.GetOrientation())
            fp.SetPosition(old.GetPosition())
            fp.SetLocked(old.IsLocked())
            removed.append(old)
            board.Remove(old)
        else:
            fp.SetPosition(pcbnew.VECTOR2I_MM(STAGE_X0_MM + STAGE_PITCH_MM * (staged % STAGE_COLS),
                                              STAGE_Y0_MM + STAGE_PITCH_MM * (staged // STAGE_COLS)))
            staged += 1
        pads = {}
        for p in fp.Pads():
            pads.setdefault(p.GetNumber(), []).append(p)
        for (r, pin), net in pin_net.items():
            if r == ref:
                if pin not in pads:
                    raise SystemExit(f'{ref}: netlist pin {pin} has no pad in {comp["footprint"]}')
                for p in pads[pin]:
                    p.SetNet(nets[net])
        board.Add(fp)
        fps[ref] = fp
        written.append(ref)

    after = {r: pad_coords(fps[r]) for r in FIXED_PADS}
    moved = [r for r in FIXED_PADS if not same_pads(before[r], after[r])]
    if moved:
        raise SystemExit(f'fixed connector pads would move: {moved}: not saved')
    board.RemoveUnusedNets(None)

    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f'{STEM}_{stamp}.kicad_pcb'
    shutil.copy2(PCB, backup)
    print(f'backup {backup.relative_to(ROOT)}')
    pcbnew.SaveBoard(str(PCB), board)
    text = PCB.read_text(encoding='utf-8')
    PCB.write_text(reseed_uuids(text, set(written)), encoding='utf-8', newline='')
    resave()
    print(f'removed {sorted(extra)}; wrote {len(written)} footprints ({staged} new, staged off-board); '
          f'{len(nets)} nets')


if __name__ == '__main__':
    main()
