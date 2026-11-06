"""12: OSH Park fab rules, board stackup, sense line off the notch edge (routing staff review; SPEC 5; 2026-11-05).

What (KiCad python, under timeout, from the project root: `python.exe -I tools/post_route/12_osh_rules.py`;
`--dry-run` saves nothing; `--root DIR` works on a scratch copy of the project files in DIR, no backups):

1. Fab = OSH Park 2-layer (project lead, 2026-11-05: 1.6 mm FR4 175Tg, 1 oz both sides, ENIG, Er 4.5). Board Setup
   constraints in `pi_power_board.kicad_pro` set to its floors (OSH_RULES): copper to edge (fab 0.381 mm, set
   COPPER_EDGE_MM), trace and space, via annular ring, drill, via diameter (= drill + 2 rings), hole to hole,
   silk text thickness. The design values stay in the net classes (Default 0.25 mm / 0.2 mm clearance; 09).
   Hole-to-copper clearance and text height unchanged (no fab figure given).
2. `pi_power_board.kicad_dru` (KiCad has no native setting): minimum slot width (DRU_TEXT). The board has no slots
   today; the rule is proven by `--selftest-dru` on a scratch copy.
3. Solder mask (board setup): expansion = the fab's mask alignment (MASK_EXPANSION_MM: the mask never reaches a
   pad at worst-case registration, hand soldering), minimum web MASK_MIN_WEB_MM (narrower webs are merged).
4. Stackup (text patch, lessons doc): 2 copper layers, core, copper and mask thickness, core Er (STACKUP_*);
   mask material written so KiCad keeps its Er. Mask Er and both loss tangents: typical values (assumption: the
   fab gives none). Board thickness = the stackup sum.
5. The `+5V1` VSENSE line along the GPIO-notch edge (09) sat only just over the fab floor (FAB_COPPER_EDGE_MM), below
   COPPER_EDGE_MM: its long run moves from SENSE_Y_OLD to SENSE_Y_NEW (same three segments, ends
   moved; still >= the 0.2 mm design clearance to the C15 / C22-C24 GND pads below it). Then every zone is
   refilled one priority at a time (the new edge clearance cuts the pours back).

Staff review of 08-11 (findings that need no copper change) is recorded in DECISIONS "Routing staff review".

Guards: KiCad lock files; tools/check_fixed.py before and after; the three sense-line segments at the 09
coordinates (or all at the new ones); every item applied -> "already applied", some -> stop. Backup of the board and
the .kicad_pro before saving. Seeded uuids (route_lib.save); no new copper items.
"""
import json
import math
import pathlib
import re
import subprocess
import sys

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import route_lib as rl  # noqa: E402

NAMESPACE = 'pipwr/12_osh_rules'

# ---------------------------------------------------------------- OSH Park 2-layer floors (project lead)
FAB_COPPER_EDGE_MM = 0.381    # the fab's floor
COPPER_EDGE_MM = 0.4          # set: margin over the fab floor
VIA_ANNULAR_MM = 0.127
DRILL_MIN_MM = 0.254
OSH_RULES = {
    'min_copper_edge_clearance': COPPER_EDGE_MM,
    'min_track_width': 0.1524,
    'min_clearance': 0.1524,
    'min_via_annular_width': VIA_ANNULAR_MM,
    'min_through_hole_diameter': DRILL_MIN_MM,
    'min_via_diameter': round(DRILL_MIN_MM + 2 * VIA_ANNULAR_MM, 4),
    'min_hole_to_hole': 0.127,
    'min_text_thickness': 0.0762,
}
MIN_SLOT_MM = 0.508
SELFTEST_SLOT_DELTA_MM = 0.1  # selftest-dru: slot this much under / over MIN_SLOT_MM
DRU_TEXT = (
    '(version 1)\n'
    '# OSH Park 2-layer (project lead 2026-11-05): minimum slot width; KiCad has no native setting.\n'
    '# hole_size checks the smaller dimension of an oval hole.\n'
    '(rule "osh_min_slot_width"\n'
    "\t(condition \"A.Type == 'Pad' && A.Hole_Size_X != A.Hole_Size_Y\")\n"
    f'\t(constraint hole_size (min {MIN_SLOT_MM}mm)))\n'
)
MASK_EXPANSION_MM = 0.0762    # = the fab's mask alignment
MASK_MIN_WEB_MM = 0.1016

# ---------------------------------------------------------------- stackup
STACKUP_CORE_MM = 1.524
STACKUP_CU_MM = 0.0356
STACKUP_MASK_MM = 0.0152
STACKUP_CORE_ER = 4.5
STACKUP_CORE_TAN_D = 0.02     # assumption: typical FR4
STACKUP_MASK_ER = 3.3         # assumption: typical LPI mask
STACKUP_MASK_MATERIAL = 'LPI'
STACKUP_CORE_MATERIAL = 'FR4'
STACKUP_FINISH = 'ENIG'
BOARD_THICKNESS_MM = round(STACKUP_CORE_MM + 2 * STACKUP_CU_MM + 2 * STACKUP_MASK_MM, 4)


def stackup_lines():
    mask = lambda name, kind: [f'(layer "{name}"', f'\t(type "{kind}")', f'\t(thickness {STACKUP_MASK_MM})',
                               f'\t(material "{STACKUP_MASK_MATERIAL}")', f'\t(epsilon_r {STACKUP_MASK_ER})',
                               '\t(loss_tangent 0)', ')']
    cu = lambda name: [f'(layer "{name}"', '\t(type "copper")', f'\t(thickness {STACKUP_CU_MM})', ')']
    plain = lambda name, kind: [f'(layer "{name}"', f'\t(type "{kind}")', ')']
    body = (plain('F.SilkS', 'Top Silk Screen') + plain('F.Paste', 'Top Solder Paste')
            + mask('F.Mask', 'Top Solder Mask') + cu('F.Cu')
            + ['(layer "dielectric 1"', '\t(type "core")', f'\t(thickness {STACKUP_CORE_MM})',
               f'\t(material "{STACKUP_CORE_MATERIAL}")', f'\t(epsilon_r {STACKUP_CORE_ER})',
               f'\t(loss_tangent {STACKUP_CORE_TAN_D})', ')']
            + cu('B.Cu') + mask('B.Mask', 'Bottom Solder Mask') + plain('B.Paste', 'Bottom Solder Paste')
            + plain('B.SilkS', 'Bottom Silk Screen')
            + [f'(copper_finish "{STACKUP_FINISH}")', '(dielectric_constraints no)'])
    return ['\t\t(stackup'] + ['\t\t\t' + s for s in body] + ['\t\t)']


STACKUP_MARKERS = [f'(thickness {STACKUP_CORE_MM})', f'(epsilon_r {STACKUP_CORE_ER})',
                   f'(material "{STACKUP_MASK_MATERIAL}")', f'(copper_finish "{STACKUP_FINISH}")']

# ---------------------------------------------------------------- VSENSE line (09) along the GPIO-notch edge
SENSE_NET = '/+5V1'
SENSE_W_MM = 0.25
SENSE_X = (142.0, 171.9)      # the run's two ends (09: down to R16, down to C24)
SENSE_DOWN_Y = (79.3, 70.85)  # the far ends of the two down-runs (untouched)
SENSE_Y_OLD = 66.55
SENSE_Y_NEW = 66.65
NOTCH_EDGE_Y = 66.04          # GPIO-notch edge (lead's outline) the run follows
EPS_NM = 1


def sense_segments(board, y):
    """The three 09 sense-line segments with the run at y: [(track, which_end_is_on_the_run)] or None."""
    run_a, run_b = rl.P(SENSE_X[0], y), rl.P(SENSE_X[1], y)
    wanted = [((run_a, run_b), None), ((rl.P(SENSE_X[0], SENSE_DOWN_Y[0]), run_a), None),
              ((rl.P(SENSE_X[1], SENSE_DOWN_Y[1]), run_b), None)]
    found = []
    for (p, q), _ in wanted:
        hit = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() == SENSE_NET
               and t.GetLayer() == rl.F and t.GetWidth() == rl.nm(SENSE_W_MM)
               and {(t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)} == {(p.x, p.y), (q.x, q.y)}]
        if len(hit) != 1:
            return None
        found.append(hit[0])
    return found


def move_sense(board):
    segs = sense_segments(board, SENSE_Y_OLD)
    if segs is None:
        raise SystemExit('sense line not at the 09 coordinates: stop')
    old_y, new_y = rl.nm(SENSE_Y_OLD), rl.nm(SENSE_Y_NEW)
    for t in segs:
        for get, put in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
            p = get()
            if abs(p.y - old_y) <= EPS_NM:
                put(pcbnew.VECTOR2I(p.x, new_y))
    if sense_segments(board, SENSE_Y_NEW) is None:
        raise SystemExit('sense line move failed: stop')


def edge_gap_mm(board):
    """Distance from the sense run's copper to the notch edge it follows."""
    return SENSE_Y_NEW - SENSE_W_MM / 2 - NOTCH_EDGE_Y


# ---------------------------------------------------------------- state

def pro_state(pro):
    rules = json.loads(pro.read_text(encoding='utf-8'))['board']['design_settings']['rules']
    return all(math.isclose(rules.get(k, -1), v, abs_tol=1e-9) for k, v in OSH_RULES.items())


def write_pro(pro):
    d = json.loads(pro.read_text(encoding='utf-8'))
    d['board']['design_settings']['rules'].update(OSH_RULES)
    pro.write_text(json.dumps(d, indent=2) + '\n', encoding='utf-8')


def dru_state(dru):
    if not dru.exists():
        return False
    if dru.read_text(encoding='utf-8').replace('\r\n', '\n') != DRU_TEXT:
        raise SystemExit(f'{dru.name} exists with other content: stop')
    return True


def mask_state(board):
    ds = board.GetDesignSettings()
    return ds.m_SolderMaskExpansion == rl.nm(MASK_EXPANSION_MM) and ds.m_SolderMaskMinWidth == rl.nm(MASK_MIN_WEB_MM)


def stackup_state(text):
    if '(stackup' not in text:
        return False
    block = text[text.index('(stackup'):]
    block = block[:block.index('(pad_to_mask_clearance')]
    if all(m in block for m in STACKUP_MARKERS) and f'(thickness {BOARD_THICKNESS_MM})' in text:
        return True
    raise SystemExit('a different stackup is on the board: stop')


def patch_stackup(pcb):
    text = pcb.read_text(encoding='utf-8')
    nl = '\r\n' if '\r\n' in text else '\n'
    setup = f'\t(setup{nl}'
    if text.count(setup) != 1 or '(stackup' in text:
        raise SystemExit('setup block not as expected for the stackup patch: stop')
    text = text.replace(setup, setup + nl.join(stackup_lines()) + nl, 1)
    thick = re.findall(r'\(general\s*\(thickness [0-9.]+\)', text)
    if len(thick) != 1:
        raise SystemExit('general thickness not found once: stop')
    text = re.sub(r'(\(general\s*\(thickness )[0-9.]+(\))', rf'\g<1>{BOARD_THICKNESS_MM}\g<2>', text, count=1)
    pcb.write_text(text, encoding='utf-8', newline='')
    b2 = pcbnew.LoadBoard(str(pcb))
    pcbnew.SaveBoard(str(pcb), b2)
    if not stackup_state(pcb.read_text(encoding='utf-8')):
        raise SystemExit('stackup lost on re-save: stop')


# ---------------------------------------------------------------- DRU self-test (scratch copy only)

def selftest_dru(root):
    """A slot narrower than MIN_SLOT_MM must fire the rule, a wider one must not (scratch copy of root)."""
    cli = pathlib.Path(sys.executable).with_name('kicad-cli.exe')
    results = {}
    for label, w in (('narrow', MIN_SLOT_MM - SELFTEST_SLOT_DELTA_MM), ('wide', MIN_SLOT_MM + SELFTEST_SLOT_DELTA_MM)):
        board = pcbnew.LoadBoard(str(root / f'{rl.STEM}.kicad_pcb'))
        fp = board.FindFootprintByReference('J2')
        pad = [p for p in fp.Pads() if p.GetNumber() == 'SH'][0]
        pad.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
        pad.SetDrillSize(pcbnew.VECTOR2I(rl.nm(w), rl.nm(2 * MIN_SLOT_MM)))
        out = root / f'{rl.STEM}.kicad_pcb'
        pcbnew.SaveBoard(str(out), board)
        rpt = root / f'drc_{label}.rpt'
        subprocess.run([str(cli), 'pcb', 'drc', '--severity-all', '-o', str(rpt), str(out)], capture_output=True,
                       timeout=rl.CHECK_TIMEOUT_S)
        results[label] = 'osh_min_slot_width' in rpt.read_text(encoding='utf-8', errors='replace')
    print(f'selftest-dru: narrow slot fires {results["narrow"]}, wide slot fires {results["wide"]}')
    if not results['narrow'] or results['wide']:
        raise SystemExit('selftest-dru FAILED')


# ---------------------------------------------------------------- main

def main():
    if '--stage2' in sys.argv:
        stage2(pathlib.Path(sys.argv[sys.argv.index('--stage2') + 1]))
        return
    root = rl.ROOT
    scratch = '--root' in sys.argv
    if scratch:
        root = pathlib.Path(sys.argv[sys.argv.index('--root') + 1]).resolve()
        if root == rl.ROOT:
            raise SystemExit('--root must be a scratch copy')
    pcb, pro, dru = (root / f'{rl.STEM}.{ext}' for ext in ('kicad_pcb', 'kicad_pro', 'kicad_dru'))
    if '--selftest-dru' in sys.argv:
        if not scratch:
            raise SystemExit('--selftest-dru needs --root DIR (it mutates the board)')
        selftest_dru(root)
        return
    if not scratch:
        rl.guard_locks()
    rl.check_fixed(pcb)
    before_text = pcb.read_text(encoding='utf-8')
    board = pcbnew.LoadBoard(str(pcb))
    sense_new = sense_segments(board, SENSE_Y_NEW) is not None
    state = {'pro': pro_state(pro), 'dru': dru_state(dru), 'mask': mask_state(board),
             'stackup': stackup_state(before_text), 'sense': sense_new}
    if all(state.values()):
        print(f'already applied: {state}; nothing saved')
        return
    if any(state.values()):
        raise SystemExit(f'partly applied {state}: stop')
    if sense_segments(board, SENSE_Y_OLD) is None:
        raise SystemExit('sense line not at the 09 coordinates: stop')
    gap = edge_gap_mm(board)
    if gap < COPPER_EDGE_MM:
        raise SystemExit(f'sense line would be {gap:.3f} mm from the edge: stop')
    if '--dry-run' in sys.argv:
        print(f'dry run: would set {OSH_RULES}, {dru.name}, mask {MASK_EXPANSION_MM} / {MASK_MIN_WEB_MM} mm, '
              f'stackup {BOARD_THICKNESS_MM} mm, sense run y {SENSE_Y_OLD} -> {SENSE_Y_NEW} (edge gap {gap:.3f} mm)')
        return
    if not scratch:
        rl.backup(pcb)
        rl.backup(pro)
    write_pro(pro)
    dru.write_text(DRU_TEXT, encoding='utf-8', newline='\n')
    # stage 2 in a fresh process: this one holds the project with the old rules (fills would use them)
    r = subprocess.run([sys.executable, '-I', __file__, '--stage2', str(root)], timeout=rl.CHECK_TIMEOUT_S)
    if r.returncode != 0:
        raise SystemExit('stage 2 failed: stop (restore the backups)')
    rl.check_fixed(pcb)


def stage2(root):
    pcb, pro, dru = (root / f'{rl.STEM}.{ext}' for ext in ('kicad_pcb', 'kicad_pro', 'kicad_dru'))
    before_text = pcb.read_text(encoding='utf-8')
    board = pcbnew.LoadBoard(str(pcb))
    ds = board.GetDesignSettings()
    if ds.m_CopperEdgeClearance != rl.nm(COPPER_EDGE_MM):
        raise SystemExit('project rules not loaded: stop')
    ds.m_SolderMaskExpansion = rl.nm(MASK_EXPANSION_MM)
    ds.m_SolderMaskMinWidth = rl.nm(MASK_MIN_WEB_MM)
    move_sense(board)
    rl.save(board, before_text, NAMESPACE, pcb)
    rl.refill(pcb)
    patch_stackup(pcb)
    board = pcbnew.LoadBoard(str(pcb))
    if not (mask_state(board) and sense_segments(board, SENSE_Y_NEW) and pro_state(pro) and dru_state(dru)):
        raise SystemExit('post-check failed: stop')
    print(f'  rules {OSH_RULES}; {dru.name} (slot >= {MIN_SLOT_MM} mm); mask {MASK_EXPANSION_MM} / {MASK_MIN_WEB_MM} mm; '
          f'stackup {BOARD_THICKNESS_MM} mm; sense run y {SENSE_Y_NEW} ({edge_gap_mm(board):.3f} mm from the notch '
          'edge); zones refilled')

if __name__ == '__main__':
    main()
