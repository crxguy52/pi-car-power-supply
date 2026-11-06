"""Post-schematic edit 12 (2026-11-05): the delay-off timer simulates from the schematic itself (KiCad 10 / ngspice).

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/12_kicad_sim.py [--dry-run]

What and why (project lead, 2026-11-05, TODO "KiCad-native simulation"): the LTspice decks in ltspice/ are written by
hand and can drift from the schematic. The schematic becomes the sim master: Eeschema -> Inspect -> Simulator runs
it, and `pdm run sim` (tools/run_sim.py) runs it headless with KiCad's ngspice.

Root sheet (pi_power_board.kicad_sch), text-level, nothing moved, no value / footprint / other field changed:
- Sim.* fields (hidden) on the parts the timer needs (SIM_FIELDS): R / C built-in models with the numeric value
  (the Value text "22 kOhm 1 %" is not a SPICE number); R27 / C29 / C8 carry the corner factors RFAC, CFAC, C8_RET;
  diodes, FETs and U5 from lib/spice/ (pipwr_parts.lib, cd4541b.lib);
- exclude_from_sim on U8 and the buck / USB passives, J1, J2, J4, J5 and SW1 (SIM_EXCLUDED): the sim sheet stands
  in for them;
- one hierarchical sheet symbol "simulation" (file simulation.kicad_sch), excluded from the board and the BOM, off to
  the side (bottom middle, left of the title block, below the USB block, clear of the lead's layout), with six sheet pins wired by a
  short stub to a local label each: BATT, ACC_IN, SW1_C, VOUT, ACC_N, +5V1 (the root sheet's own net names).

New sheet simulation.kicad_sch (sim-only; every symbol in_bom no, on_board no): the battery with its harness and
hot-plug step, the ACC key stimulus, an SW1 stand-in switch, the Pi load on VOUT, the Pi GPIO pull-up on ACC_N, a U8
stand-in (+5V1 with soft start, current limit, optional USB overload with hiccup), and the .param / .tran / .meas
directives. The blocks are subcircuits in lib/spice/sim_bench.lib, drawn with two project symbols added to
lib/pi_power_board.kicad_sym: pipwr:SIM_2T (two terminals) and pipwr:SIM_3T (in / out / ground).

Guards: refuses if a KiCad lock file exists. Accepts two states: (1) pre-edit: no sheet symbol, no Sim.* field on any
placed symbol, every part of SIM_FIELDS / SIM_EXCLUDED present with the expected lib_id and exclude_from_sim no,
simulation.kicad_sch absent; (2) applied: the root sheet and simulation.kicad_sch are what this script writes
("already applied"). Anything else stops. Backups to pi_power_board-backups/ first; CRLF kept; uuids are uuid5 of a
fixed namespace (re-runs write the same file). Every existing symbol uuid and position is kept (checked).
"""
import argparse
import datetime
import importlib.util
import pathlib
import re
import shutil
import sys
import uuid

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import sch_lib  # noqa: E402
import sexpr  # noqa: E402

ROOT = TOOLS.parent
SCH = ROOT / 'pi_power_board.kicad_sch'
SIM_SCH = ROOT / 'simulation.kicad_sch'
SYM_LIB = ROOT / 'lib' / 'pi_power_board.kicad_sym'
BACKUPS = ROOT / 'pi_power_board-backups'
LOCKS = (ROOT / '~pi_power_board.kicad_sch.lck', ROOT / '~simulation.kicad_sch.lck')
HERE_13 = TOOLS / 'post_sch' / '13_sim_fast_review.py'   # later edit of the sim sheet texts (guard only)
PROJECT = 'pi_power_board'
NL = '\r\n'
NS = uuid.UUID('6a1f3c2e-12a5-4c1e-9b0d-5ad0c0de0012')     # fixed namespace: seeded uuid5
SPICE_DIR = '${KIPRJMOD}/lib/spice/'
PARTS_LIB = SPICE_DIR + 'pipwr_parts.lib'
U5_LIB = SPICE_DIR + 'cd4541b.lib'
BENCH_LIB = SPICE_DIR + 'sim_bench.lib'
GRID = 1.27

# ---------------------------------------------------------------- root sheet: Sim fields per part
R_PINS = '1=+ 2=-'
SIM_FIELDS = {
    'R3': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=5.1k'), ('Sim.Pins', R_PINS)]),
    'R8': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=22k'), ('Sim.Pins', R_PINS)]),
    'R14': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=220k'), ('Sim.Pins', R_PINS)]),
    'R15': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=180k'), ('Sim.Pins', R_PINS)]),
    'R21': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=1.5k'), ('Sim.Pins', R_PINS)]),
    'R25': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=27k'), ('Sim.Pins', R_PINS)]),
    'R26': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=100k'), ('Sim.Pins', R_PINS)]),
    'R27': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r={39.2k*RFAC}'), ('Sim.Pins', R_PINS)]),
    'R28': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=78.7k'), ('Sim.Pins', R_PINS)]),
    'R29': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=47k'), ('Sim.Pins', R_PINS)]),
    'R30': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=1.3k'), ('Sim.Pins', R_PINS)]),
    'R31': ('Device:R_US', [('Sim.Device', 'R'), ('Sim.Params', 'r=10k'), ('Sim.Pins', R_PINS)]),
    'C8': ('Device:C', [('Sim.Device', 'C'), ('Sim.Params', 'c={1u*C8_RET}'), ('Sim.Pins', R_PINS)]),
    'C29': ('Device:C', [('Sim.Device', 'C'), ('Sim.Params', 'c={10n*CFAC}'), ('Sim.Pins', R_PINS)]),
    'C30': ('Device:C', [('Sim.Device', 'C'), ('Sim.Params', 'c=100n'), ('Sim.Pins', R_PINS)]),
    'D3': ('Device:LED', [('Sim.Library', PARTS_LIB), ('Sim.Name', 'LTST_C150KRKT_PIPWR'), ('Sim.Pins', '1=K 2=A')]),
    'D4': ('Diode:1N4148W', [('Sim.Library', PARTS_LIB), ('Sim.Name', 'D1N4148W_PIPWR'), ('Sim.Pins', '1=K 2=A')]),
    'D5': ('Diode:1N4148W', [('Sim.Library', PARTS_LIB), ('Sim.Name', 'D1N4148W_PIPWR'), ('Sim.Pins', '1=K 2=A')]),
    'D6': ('Diode:BAS21', [('Sim.Library', PARTS_LIB), ('Sim.Name', 'BAS116_PIPWR'), ('Sim.Pins', '1=A 3=K')]),
    'D7': ('Device:D_Zener', [('Sim.Library', PARTS_LIB), ('Sim.Name', 'BZT52C5V1_PIPWR'), ('Sim.Pins', '1=K 2=A')]),
    'TVS1': ('Device:D_Zener', [('Sim.Library', PARTS_LIB), ('Sim.Name', 'SMBJ16A_PIPWR'), ('Sim.Pins', '1=K 2=A')]),
    'TVS2': ('Device:D_Zener', [('Sim.Library', PARTS_LIB), ('Sim.Name', 'SMBJ16A_PIPWR'), ('Sim.Pins', '1=K 2=A')]),
    'Q1': ('Transistor_FET:Q_PMOS_GDS', [('Sim.Library', PARTS_LIB), ('Sim.Name', 'SQD50P04_PIPWR'),
                                          ('Sim.Pins', '1=G 2=D 3=S')]),
    'Q5': ('Transistor_FET:2N7002', [('Sim.Library', PARTS_LIB), ('Sim.Name', 'Q2N7002BK_PIPWR'),
                                     ('Sim.Pins', '1=G 2=S 3=D')]),
    'Q6': ('Transistor_FET:2N7002', [('Sim.Library', PARTS_LIB), ('Sim.Name', 'Q2N7002BK_PIPWR'),
                                     ('Sim.Pins', '1=G 2=S 3=D')]),
    'U5': ('Timer:CD4541BM', [('Sim.Library', U5_LIB), ('Sim.Name', 'CD4541B'),
                              ('Sim.Pins', '1=RTC 2=CTC 3=RS 5=AR 6=MR 7=VSS 8=OUT 9=QSEL 10=MODE 12=A 13=B 14=VDD'),
                              ('Sim.Params', 'HYS={U5_HYS} RDRV={U5_RDRV} IDD={U5_IDD}')]),
}
SIM_EXCLUDED = ('U8', 'C15', 'C17', 'C18', 'C19', 'C20', 'C22', 'C23', 'C24', 'L1', 'R16', 'R17', 'R18',
                'J1', 'J2', 'J4', 'J5', 'SW1')

# ---------------------------------------------------------------- root sheet: the sheet symbol (A4, mm)
SHEET_NAME = 'simulation'
SHEET_AT = (142.24, 172.72)
SHEET_SIZE = (22.86, 17.78)
SHEET_PINS = ('BATT', 'ACC_IN', 'SW1_C', 'VOUT', 'ACC_N', '+5V1')
PIN_Y0 = 175.26
PIN_PITCH = 2.54
STUB = 5.08
SHEET_PAGE = '2'
# free area the sheet symbol, stubs and labels must stay inside (nothing of the lead's layout in it)
KEEP_CLEAR = (121.92, 170.18, 170.18, 194.31)

# ---------------------------------------------------------------- project symbols
SYM_2T = 'SIM_2T'
SYM_3T = 'SIM_3T'
SYMBOL_TEXT = {SYM_2T: '''	(symbol "SIM_2T"
		(pin_names
			(offset 0.254)
			(hide yes)
		)
		(exclude_from_sim no)
		(in_bom no)
		(on_board no)
		(property "Reference" "S"
			(at 3.81 1.27 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
			)
		)
		(property "Value" "SIM_2T"
			(at 3.81 -1.27 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(justify left)
			)
		)
		(property "Footprint" ""
			(at 0 0 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(hide yes)
			)
		)
		(property "Datasheet" ""
			(at 0 0 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(hide yes)
			)
		)
		(property "Description" "Simulation-only two-terminal block (a subcircuit of lib/spice/sim_bench.lib): not a board part"
			(at 0 0 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(hide yes)
			)
		)
		(property "ki_keywords" "simulation"
			(at 0 0 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(hide yes)
			)
		)
		(symbol "SIM_2T_0_1"
			(rectangle
				(start -2.54 3.81)
				(end 2.54 -3.81)
				(stroke
					(width 0.254)
					(type dash)
				)
				(fill
					(type none)
				)
			)
			(text "SIM"
				(at 0 0 900)
				(effects
					(font
						(size 1.016 1.016)
					)
				)
			)
		)
		(symbol "SIM_2T_1_1"
			(pin passive line
				(at 0 6.35 270)
				(length 2.54)
				(name "1"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
				(number "1"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
			)
			(pin passive line
				(at 0 -6.35 90)
				(length 2.54)
				(name "2"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
				(number "2"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
			)
		)
		(embedded_fonts no)
	)
''', SYM_3T: '''	(symbol "SIM_3T"
		(pin_names
			(offset 0.254)
		)
		(exclude_from_sim no)
		(in_bom no)
		(on_board no)
		(property "Reference" "S"
			(at 0 6.35 0)
			(effects
				(font
					(size 1.27 1.27)
				)
			)
		)
		(property "Value" "SIM_3T"
			(at 0 4.445 0)
			(effects
				(font
					(size 1.27 1.27)
				)
			)
		)
		(property "Footprint" ""
			(at 0 0 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(hide yes)
			)
		)
		(property "Datasheet" ""
			(at 0 0 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(hide yes)
			)
		)
		(property "Description" "Simulation-only in / out / ground block (a subcircuit of lib/spice/sim_bench.lib): not a board part"
			(at 0 0 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(hide yes)
			)
		)
		(property "ki_keywords" "simulation"
			(at 0 0 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(hide yes)
			)
		)
		(symbol "SIM_3T_0_1"
			(rectangle
				(start -5.08 3.81)
				(end 5.08 -3.81)
				(stroke
					(width 0.254)
					(type dash)
				)
				(fill
					(type none)
				)
			)
		)
		(symbol "SIM_3T_1_1"
			(pin passive line
				(at -7.62 0 0)
				(length 2.54)
				(name "IN"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
				(number "1"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
			)
			(pin passive line
				(at 7.62 0 180)
				(length 2.54)
				(name "OUT"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
				(number "2"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
			)
			(pin passive line
				(at 0 -6.35 90)
				(length 2.54)
				(name "GND"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
				(number "3"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
			)
		)
		(embedded_fonts no)
	)
'''}

# ---------------------------------------------------------------- simulation sheet: blocks
# (ref, symbol, value, subckt, pin map, (x, y), {pin: net}); net 'GND' = a GND power symbol, others = hier. labels
BLOCKS = (
    ('SB1', SYM_2T, 'SIM_BATT battery + harness', 'SIM_BATT', '1=BATT 2=GND', (38.1, 63.5),
     {'1': 'BATT', '2': 'GND'}),
    ('SA1', SYM_2T, 'SIM_ACC key (ACC)', 'SIM_ACC', '1=ACC 2=GND', (78.74, 63.5), {'1': 'ACC_IN', '2': 'GND'}),
    ('SS1', SYM_2T, 'SIM_SW1 SW1 stand-in', 'SIM_SW1', '1=BATT 2=SWC', (119.38, 63.5), {'1': 'BATT', '2': 'SW1_C'}),
    ('SL1', SYM_2T, 'SIM_PI_LOAD Pi 12 V input', 'SIM_PI_LOAD', '1=VOUT 2=GND', (160.02, 63.5),
     {'1': 'VOUT', '2': 'GND'}),
    ('SP1', SYM_2T, 'SIM_PI_GPIO Pi pull-up', 'SIM_PI_GPIO', '1=ACC_N 2=GND', (200.66, 63.5),
     {'1': 'ACC_N', '2': 'GND'}),
    ('SU1', SYM_3T, 'SIM_U8 buck stand-in', 'SIM_U8', '1=VIN 2=OUT 3=GND', (243.84, 63.5),
     {'1': 'VOUT', '2': '+5V1', '3': 'GND'}),
)
LABEL_STUB = 2.54
PWR_REF0 = 101

# directives: the defaults are the nominal key cycle at 12 V (tools/run_sim.py rewrites the .param lines per run)
PARAM_TEXT = '''* SIM-ONLY (tools/post_sch/12_kicad_sim.py): defaults = nominal corner, 12 V, one key cycle
* corners (tools/run_sim.py): R27 / C29 factors, U5 oscillator, diodes, FETs, zener, U5 current
.param RFAC=1 CFAC=1 C8_RET=0.7
.param U5_HYS=0.054 U5_RDRV=129 U5_IDD=0.3m
.param IS_D=1.5e-10 BVZ=5.1 VTO_N=1.6 IDSS_N=0 VTO_P=-2.0 IDSS_P=0
* battery, key, SW1
.param VB=12 RHARN=50m LHARN=1u T_PLUG=10m TEDGE=1m
.param ACC_V=12 T_ON1=1 T_OFF1=5 T_ON2=1e3 T_OFF2=1.001e3
.param SW_EN=0 T_SW_ON=1 T_SW_OFF=5
* Pi load (constant power) and GPIO pull-up
.param CVOUT=674u VUV=4.5 P_RUN=27 P_AFTER=2 T_PIOFF=8 T_PISD=3 VPI=3.3 RPI=50k
* U8 stand-in, USB load, overload
.param V5SET=5.09 UV_ON=4.5 UV_OFF=4.32 T_SS=3.5m C5V1=48u RFB=63.6k I_USB=3 ETA=0.91 ILIM=4.7
.param OVL=0 R_OVL=0.5 T_OVL=13 T_HWAIT=1.255m T_HOFF=40.16m
* the last ACC / SW1 falling edge (measurement reference); output grid T_STEP (.options interp); T_END = last point;
* keep T_STEP / T_STOP / T_MAX equal to the numbers on the .tran line (run_sim.py rewrites both)
.param T_LASTOFF=5 T_STOP=50 T_STEP=1m T_MAX=1m T_ENDWIN=5
.param T_END={T_STOP-2*T_STEP}'''
ANALYSIS_TEXT = '''.options method=gear interp
.save V(/BATT) V(/ACC_IN) V(/ACC_G) V(/HOLD_G) V(/VOUT) V(/VDD_TMR) V(/U5_OUT) V(/ACC_N) V(/+5V1) V(/U5_CTC)
.tran 1m 50 0 1m uic
* hold: last ACC / SW1 falling edge to VOUT falling through VB / 2
.meas TRAN vout_fall FIND time WHEN V(/VOUT)={VB/2} TD={T_LASTOFF} FALL=1
.meas TRAN hold PARAM='vout_fall - T_LASTOFF'
.meas TRAN vout_fall_last FIND time WHEN V(/VOUT)={VB/2} FALL=LAST
.meas TRAN vout_rise_last FIND time WHEN V(/VOUT)={VB/2} RISE=LAST
* on / counting: VOUT never dips, VDD_TMR range, HOLD_G, J5
.meas TRAN vout_min_on MIN V(/VOUT) FROM={T_ON1+0.5} TO={T_LASTOFF+20}
.meas TRAN vtmr_cnt_min MIN V(/VDD_TMR) FROM={T_LASTOFF+0.5} TO={T_LASTOFF+20}
.meas TRAN vtmr_cnt_max MAX V(/VDD_TMR) FROM={T_LASTOFF+0.5} TO={T_LASTOFF+20}
.meas TRAN holdg_cnt_min MIN V(/HOLD_G) FROM={T_LASTOFF+0.5} TO={T_LASTOFF+20}
.meas TRAN j5_on_max MAX V(/ACC_N) FROM={T_ON1+0.5} TO={T_OFF1}
.meas TRAN j5_off_min MIN V(/ACC_N) FROM={T_LASTOFF+0.5} TO={T_LASTOFF+20}
* end: VOUT / VDD_TMR / HOLD_G off in the last T_ENDWIN, no re-latch
.meas TRAN vout_end_max MAX V(/VOUT) FROM={T_STOP-T_ENDWIN} TO={T_END}
.meas TRAN vtmr_end_max MAX V(/VDD_TMR) FROM={T_STOP-T_ENDWIN} TO={T_END}
.meas TRAN holdg_end_max MAX V(/HOLD_G) FROM={T_STOP-T_ENDWIN} TO={T_END}
* battery hot-plug, key off: VOUT, VDD_TMR, HOLD_G before the first key-on
.meas TRAN hp_vout_max MAX V(/VOUT) FROM=0 TO={min(min(T_ON1, T_SW_ON)-TEDGE, T_END)}
.meas TRAN hp_vtmr_max MAX V(/VDD_TMR) FROM=0 TO={min(min(T_ON1, T_SW_ON)-TEDGE, T_END)}
.meas TRAN hp_holdg_max MAX V(/HOLD_G) FROM=0 TO={min(min(T_ON1, T_SW_ON)-TEDGE, T_END)}'''
TEXT_AT = ((25.4, 96.52), (152.4, 96.52))
NOTE_TEXT = ('SIM-ONLY SHEET: nothing here is on the board or in the BOM. Run: Inspect > Simulator, or pdm run sim '
             '(tools/run_sim.py: every scenario, reports/sim_kicad.md). Blocks: lib/spice/sim_bench.lib')
NOTE_AT = (25.4, 38.1)


def uid(*key):
    return str(uuid.uuid5(NS, '/'.join(map(str, key))))


def fnum(v):
    return sexpr.fmt_num(round(v, 4))


def q(s):
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


# ---------------------------------------------------------------- text-level helpers

def top_items(text):
    """(start, end) of every depth-1 item of the kicad_sch document (end exclusive, after the ')')."""
    out, depth, i, n, start, in_str = [], 0, 0, len(text), None, False
    while i < n:
        c = text[i]
        if in_str:
            if c == '\\':
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == '(':
            depth += 1
            if depth == 2:
                start = text.rfind('\n', 0, i) + 1
        elif c == ')':
            if depth == 2:
                out.append((start, i + 1))
            depth -= 1
        i += 1
    return out


def placed_symbols(text):
    """{ref: [(start, end), ...]} of the placed symbols (one entry per unit block)."""
    out = {}
    for s, e in top_items(text):
        block = text[s:e]
        if block.lstrip('\t').startswith('(symbol' + NL) or block.lstrip('\t').startswith('(symbol\n'):
            m = re.search(r'\(property "Reference" "([^"]*)"', block)
            if m:
                out.setdefault(m.group(1), []).append((s, e))
    return out


def prop_block(name, value, at):
    return (f'\t\t(property "{name}" "{q(value)}"{NL}\t\t\t(at {fnum(at[0])} {fnum(at[1])} 0){NL}\t\t\t(hide yes){NL}'
            f'\t\t\t(show_name no){NL}\t\t\t(do_not_autoplace no){NL}\t\t\t(effects{NL}\t\t\t\t(font{NL}'
            f'\t\t\t\t\t(size 1.27 1.27){NL}\t\t\t\t){NL}\t\t\t){NL}\t\t){NL}')


def symbol_at(block):
    m = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)', block)
    return float(m.group(1)), float(m.group(2)), m.group(3)


def lib_id(block):
    return re.search(r'\(lib_id "([^"]*)"\)', block).group(1)


def edit_root(text):
    """The root sheet with the Sim fields, exclusions and the sheet symbol; raises SystemExit on a surprise."""
    syms = placed_symbols(text)
    edits = []                                      # (start, end, replacement)
    for ref, (want_lib, fields) in SIM_FIELDS.items():
        blocks = syms.get(ref)
        if not blocks or len(blocks) != 1:
            raise SystemExit(f'unexpected state: {ref} placed {len(blocks or [])} times')
        s, e = blocks[0]
        block = text[s:e]
        if lib_id(block) != want_lib:
            raise SystemExit(f'unexpected state: {ref} lib_id {lib_id(block)}, expected {want_lib}')
        x, y, _ = symbol_at(block)
        ins = block.index(NL + '\t\t(pin "') + len(NL)
        new = block[:ins] + ''.join(prop_block(n, v, (x, y)) for n, v in fields) + block[ins:]
        edits.append((s, e, new))
    for ref in SIM_EXCLUDED:
        for s, e in syms.get(ref, []):
            block = text[s:e]
            if block.count('(exclude_from_sim no)') != 1:
                raise SystemExit(f'unexpected state: {ref} exclude_from_sim')
            edits.append((s, e, block.replace('(exclude_from_sim no)', '(exclude_from_sim yes)')))
        if ref not in syms:
            raise SystemExit(f'unexpected state: {ref} missing')
    out = text
    for s, e, new in sorted(edits, reverse=True):
        out = out[:s] + new + out[e:]
    anchor = NL + '\t(sheet_instances'
    if out.count(anchor) != 1:
        raise SystemExit('unexpected state: sheet_instances')
    i = out.index(anchor) + len(NL)
    return out[:i] + sheet_items(root_uuid(text)) + out[i:]


def root_uuid(text):
    return re.search(r'^\t\(uuid "([^"]+)"\)', text, re.M).group(1)


def sheet_items(root):
    x0, y0 = SHEET_AT
    w, h = SHEET_SIZE
    su = uid('sheet', SHEET_NAME)
    pins = ''
    items = ''
    for i, net in enumerate(SHEET_PINS):
        y = PIN_Y0 + i * PIN_PITCH
        pins += (f'\t\t(pin "{q(net)}" bidirectional{NL}\t\t\t(at {fnum(x0)} {fnum(y)} 180){NL}'
                 f'\t\t\t(uuid "{uid("sheetpin", net)}"){NL}\t\t\t(effects{NL}\t\t\t\t(font{NL}'
                 f'\t\t\t\t\t(size 1.27 1.27){NL}\t\t\t\t){NL}\t\t\t\t(justify left){NL}\t\t\t){NL}\t\t){NL}')
        items += (f'\t(wire{NL}\t\t(pts{NL}\t\t\t(xy {fnum(x0 - STUB)} {fnum(y)}) (xy {fnum(x0)} {fnum(y)}){NL}\t\t){NL}'
                  f'\t\t(stroke{NL}\t\t\t(width 0){NL}\t\t\t(type default){NL}\t\t){NL}'
                  f'\t\t(uuid "{uid("stubwire", net)}"){NL}\t){NL}')
        items += (f'\t(label "{q(net)}"{NL}\t\t(at {fnum(x0 - STUB)} {fnum(y)} 180){NL}\t\t(effects{NL}\t\t\t(font{NL}'
                  f'\t\t\t\t(size 1.27 1.27){NL}\t\t\t){NL}\t\t\t(justify right bottom){NL}\t\t){NL}'
                  f'\t\t(uuid "{uid("stublabel", net)}"){NL}\t){NL}')
    sheet = (f'\t(sheet{NL}\t\t(at {fnum(x0)} {fnum(y0)}){NL}\t\t(size {fnum(w)} {fnum(h)}){NL}'
             f'\t\t(exclude_from_sim no){NL}\t\t(in_bom no){NL}\t\t(on_board no){NL}\t\t(dnp no){NL}'
             f'\t\t(stroke{NL}\t\t\t(width 0.1524){NL}\t\t\t(type dash){NL}\t\t){NL}'
             f'\t\t(fill{NL}\t\t\t(color 0 0 0 0.0000){NL}\t\t){NL}\t\t(uuid "{su}"){NL}'
             f'\t\t(property "Sheetname" "{SHEET_NAME}"{NL}\t\t\t(at {fnum(x0)} {fnum(y0 - 0.7116)} 0){NL}'
             f'\t\t\t(effects{NL}\t\t\t\t(font{NL}\t\t\t\t\t(size 1.27 1.27){NL}\t\t\t\t){NL}'
             f'\t\t\t\t(justify left bottom){NL}\t\t\t){NL}\t\t){NL}'
             f'\t\t(property "Sheetfile" "{SIM_SCH.name}"{NL}\t\t\t(at {fnum(x0)} {fnum(y0 + h + 0.5846)} 0){NL}'
             f'\t\t\t(effects{NL}\t\t\t\t(font{NL}\t\t\t\t\t(size 1.27 1.27){NL}\t\t\t\t){NL}'
             f'\t\t\t\t(justify left top){NL}\t\t\t){NL}\t\t){NL}'
             + pins +
             f'\t\t(instances{NL}\t\t\t(project "{PROJECT}"{NL}\t\t\t\t(path "/{root}"{NL}'
             f'\t\t\t\t\t(page "{SHEET_PAGE}"){NL}\t\t\t\t){NL}\t\t\t){NL}\t\t){NL}\t){NL}')
    return sheet + items


# ---------------------------------------------------------------- simulation sheet

def lib_symbol_texts():
    """lib_symbols entries (tab-indented, LF) for the sim sheet: pipwr:SIM_2T, pipwr:SIM_3T, power:GND."""
    out = []
    for name in (SYM_2T, SYM_3T):
        node = sexpr.parse(SYMBOL_TEXT[name])
        node[1] = f'pipwr:{name}'
        out.append(sexpr.dump(node, 2))
    out.append(sexpr.dump(sch_lib.flat_symbol('power:GND'), 2))
    return '\n'.join(out)


def field(name, value, at, hide, justify=None):
    j = f'\t\t\t\t(justify {justify}){NL}' if justify else ''
    return (f'\t\t(property "{name}" "{q(value)}"{NL}\t\t\t(at {fnum(at[0])} {fnum(at[1])} 0){NL}'
            + (f'\t\t\t(hide yes){NL}' if hide else '')
            + f'\t\t\t(show_name no){NL}\t\t\t(do_not_autoplace no){NL}\t\t\t(effects{NL}\t\t\t\t(font{NL}'
              f'\t\t\t\t\t(size 1.27 1.27){NL}\t\t\t\t){NL}' + j + f'\t\t\t){NL}\t\t){NL}')


def placed(lib, ref, value, at, fields, pins, path, in_bom=False, key=None):
    key = key or ref
    x, y = at
    s = (f'\t(symbol{NL}\t\t(lib_id "{lib}"){NL}\t\t(at {fnum(x)} {fnum(y)} 0){NL}\t\t(unit 1){NL}'
         f'\t\t(body_style 1){NL}\t\t(exclude_from_sim no){NL}\t\t(in_bom {"yes" if in_bom else "no"}){NL}'
         f'\t\t(on_board no){NL}\t\t(in_pos_files no){NL}\t\t(dnp no){NL}\t\t(uuid "{uid("sym", key)}"){NL}')
    s += ''.join(fields)
    for p in pins:
        s += f'\t\t(pin "{p}"{NL}\t\t\t(uuid "{uid("pin", key, p)}"){NL}\t\t){NL}'
    s += (f'\t\t(instances{NL}\t\t\t(project "{PROJECT}"{NL}\t\t\t\t(path "{path}"{NL}'
          f'\t\t\t\t\t(reference "{ref}"){NL}\t\t\t\t\t(unit 1){NL}\t\t\t\t){NL}\t\t\t){NL}\t\t){NL}\t){NL}')
    return s


def wire(a, b, key):
    return (f'\t(wire{NL}\t\t(pts{NL}\t\t\t(xy {fnum(a[0])} {fnum(a[1])}) (xy {fnum(b[0])} {fnum(b[1])}){NL}\t\t){NL}'
            f'\t\t(stroke{NL}\t\t\t(width 0){NL}\t\t\t(type default){NL}\t\t){NL}\t\t(uuid "{uid("w", key)}"){NL}\t){NL}')


def hlabel(net, at, angle, key):
    justify = 'right' if angle in (180, 270) else 'left'
    return (f'\t(hierarchical_label "{q(net)}"{NL}\t\t(shape bidirectional){NL}'
            f'\t\t(at {fnum(at[0])} {fnum(at[1])} {angle}){NL}\t\t(effects{NL}\t\t\t(font{NL}'
            f'\t\t\t\t(size 1.27 1.27){NL}\t\t\t){NL}\t\t\t(justify {justify}){NL}\t\t){NL}'
            f'\t\t(uuid "{uid("hl", key)}"){NL}\t){NL}')


def text_item(body, at, key, size=1.27):
    return (f'\t(text "{q(body)}"{NL}\t\t(exclude_from_sim no){NL}\t\t(at {fnum(at[0])} {fnum(at[1])} 0){NL}'
            f'\t\t(effects{NL}\t\t\t(font{NL}\t\t\t\t(size {size} {size}){NL}\t\t\t){NL}'
            f'\t\t\t(justify left top){NL}\t\t){NL}\t\t(uuid "{uid("text", key)}"){NL}\t){NL}')


def pin_points(sym, at):
    """{pin: ((x, y) connection point, (dx, dy) outward)} on the sheet."""
    node = sexpr.parse(SYMBOL_TEXT[sym])
    out = {}
    for num, (px, py, ang, _length, _name, _t) in sch_lib.lib_pins(node, 1).items():
        out[num] = (sch_lib.to_sheet(at[0], at[1], 0, px, py), sch_lib.outward(0, ang))
    return out


def build_sim_sheet(root):
    su = uid('sheet', SHEET_NAME)
    path = f'/{root}/{su}'
    body = ''
    pwr = PWR_REF0
    for ref, sym, value, subckt, pins, at, nets in BLOCKS:
        x, y = at
        fields = [field('Reference', ref, (x + 3.81, y - 1.27), False, 'left'),
                  field('Value', value, (x + 3.81, y + 1.27), False, 'left'),
                  field('Footprint', '', at, True), field('Datasheet', '', at, True),
                  field('Description', 'Simulation only (not a board part): ' + subckt + ' in lib/spice/sim_bench.lib',
                        at, True),
                  field('Sim.Library', BENCH_LIB, at, True), field('Sim.Name', subckt, at, True),
                  field('Sim.Pins', pins, at, True)]
        if sym == SYM_3T:
            fields[0] = field('Reference', ref, (x, y - 7.62), False)
            fields[1] = field('Value', value, (x, y - 5.08), False)
        body += placed(f'pipwr:{sym}', ref, value, at, fields, sorted(nets), path)
        for pin, net in sorted(nets.items()):
            (px, py), (dx, dy) = pin_points(sym, at)[pin]
            end = (round(px + dx * LABEL_STUB, 4), round(py + dy * LABEL_STUB, 4))
            body += wire((px, py), end, f'{ref}.{pin}')
            if net == 'GND':
                pref = f'#PWR{pwr}'
                pwr += 1
                gfields = [field('Reference', pref, (end[0], end[1] + 6.35), True),
                           field('Value', 'GND', (end[0], end[1] + 3.81), False),
                           field('Footprint', '', end, True), field('Datasheet', '', end, True),
                           field('Description', 'Power symbol creates a global label with name "GND" , ground',
                                 end, True)]
                gs = placed('power:GND', pref, 'GND', end, gfields, ['1'], path, in_bom=False, key=f'gnd.{ref}')
                body += gs.replace(f'(at {fnum(end[0])} {fnum(end[1])} 0){NL}\t\t(unit 1)',
                                   f'(at {fnum(end[0])} {fnum(end[1])} 0){NL}\t\t(unit 1)', 1)
            else:
                angle = 90 if dy < 0 else (270 if dy > 0 else (180 if dx < 0 else 0))
                body += hlabel(net, end, angle, f'{ref}.{pin}')
    body += text_item(NOTE_TEXT, NOTE_AT, 'note', 1.524)
    body += text_item(PARAM_TEXT, TEXT_AT[0], 'params')
    body += text_item(ANALYSIS_TEXT, TEXT_AT[1], 'analysis')
    libs = lib_symbol_texts().replace('\n', NL)
    head = (f'(kicad_sch{NL}\t(version 20260306){NL}\t(generator "eeschema"){NL}\t(generator_version "10.0"){NL}'
            f'\t(uuid "{uid("simsheet-file")}"){NL}\t(paper "A4"){NL}\t(title_block{NL}'
            f'\t\t(title "Pi 5 car power HAT: simulation (sim-only)"){NL}\t){NL}\t(lib_symbols{NL}{libs}{NL}\t){NL}')
    return head + body + f'\t(embedded_fonts no){NL}){NL}'


# ---------------------------------------------------------------- project symbol library

def edit_sym_lib(text):
    out = text
    for name in (SYM_2T, SYM_3T):
        if f'(symbol "{name}"' in out:
            continue
        i = out.rstrip().rfind(')')
        out = out[:i] + SYMBOL_TEXT[name].replace('\n', NL) + out[i:]
    return out


# ---------------------------------------------------------------- checks

def check_pre(text):
    if '\n\t(sheet' + NL in text or re.search(r'\n\t\t\(property "Sim\.', text):
        raise SystemExit('unexpected state: the root sheet already has a sheet symbol or a placed Sim.* field, '
                         'and is not what this script writes')
    if SIM_SCH.exists():
        raise SystemExit(f'unexpected state: {SIM_SCH.name} exists but the root sheet is unedited')


def check_result(old, new):
    """Every old symbol keeps its uuid, lib_id and position; nothing but the expected changes."""
    a, b = placed_symbols(old), placed_symbols(new)
    if set(a) != set(b):
        raise SystemExit(f'check: placed refs changed: {sorted(set(a) ^ set(b))}')
    for ref in a:
        for (s0, e0), (s1, e1) in zip(a[ref], b[ref]):
            x0, x1 = old[s0:e0], new[s1:e1]
            u0 = re.search(r'\n\t\t\(uuid "([^"]+)"\)', x0).group(1)
            u1 = re.search(r'\n\t\t\(uuid "([^"]+)"\)', x1).group(1)
            if u0 != u1 or symbol_at(x0) != symbol_at(x1) or lib_id(x0) != lib_id(x1):
                raise SystemExit(f'check: {ref} uuid / position / lib_id changed')
            strip = re.sub(r'\t\t\(property "Sim\.[^"]*" "[^"]*"\r\n(?:\t\t\t.*\r\n)*?\t\t\)\r\n', '', x1)
            if strip.replace('(exclude_from_sim yes)', '(exclude_from_sim no)') != x0:
                raise SystemExit(f'check: {ref} changed beyond Sim fields / exclude_from_sim')
    others_old = [old[s:e] for s, e in top_items(old) if not old[s:e].lstrip('\t').startswith('(symbol' + NL)]
    others_new = [new[s:e] for s, e in top_items(new) if not new[s:e].lstrip('\t').startswith('(symbol' + NL)]
    added = [x for x in others_new if x not in others_old]
    if [x for x in others_old if x not in others_new]:
        raise SystemExit('check: a non-symbol item of the root sheet was removed or changed')
    if len(added) != 1 + 2 * len(SHEET_PINS):
        raise SystemExit(f'check: {len(added)} items added, expected {1 + 2 * len(SHEET_PINS)}')
    pts = [tuple(map(float, m)) for x in added for m in re.findall(r'\((?:at|xy) ([-\d.]+) ([-\d.]+)', x)]
    x0, y0, x1, y1 = KEEP_CLEAR
    if not all(x0 <= px <= x1 and y0 <= py <= y1 for px, py in pts):
        raise SystemExit('check: an added item lies outside the free area')
    for px, py in pts:
        if abs(px / GRID - round(px / GRID)) > 1e-6 and abs(py / GRID - round(py / GRID)) > 1e-6:
            raise SystemExit(f'check: off-grid point {px}, {py}')
    # nothing of the lead's layout inside the free area
    for s, e in top_items(old):
        for m in re.findall(r'\n\t\t\((?:at|xy) ([-\d.]+) ([-\d.]+)', old[s:e]):
            px, py = map(float, m)
            if x0 < px < x1 and y0 < py < y1:
                raise SystemExit(f'check: existing item at {px}, {py} inside the free area')


def backup(path, stamp):
    BACKUPS.mkdir(exist_ok=True)
    shutil.copy2(path, BACKUPS / f'{path.stem}_{stamp}{path.suffix}')


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv[1:])
    for lock in LOCKS:
        if lock.exists():
            sys.exit(f'refusing: {lock.name} exists (schematic open in KiCad)')
    raw = SCH.read_bytes()
    if b'\r\n' not in raw:
        sys.exit('unexpected state: the root sheet is not CRLF')
    text = raw.decode('utf-8')
    root = root_uuid(text)
    sim_text = build_sim_sheet(root)
    lib_raw = SYM_LIB.read_bytes().decode('utf-8')
    lib_new = edit_sym_lib(lib_raw)
    if f'(uuid "{uid("sheet", SHEET_NAME)}")' in text:
        if SIM_SCH.exists() and SIM_SCH.read_bytes().decode('utf-8') == sim_text and lib_new == lib_raw:
            print('already applied')
            return 0
        # guard only (staff review, 2026-11-05): 13_sim_fast_review.py later rewrote this sheet's three text items
        if HERE_13.exists() and SIM_SCH.exists() and lib_new == lib_raw:
            spec = importlib.util.spec_from_file_location('post_sch_13', HERE_13)
            m13 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m13)
            if SIM_SCH.read_bytes().decode('utf-8') == m13.expected_sim(sim_text):
                print(f'already applied (texts of {SIM_SCH.name} since updated by {HERE_13.name})')
                return 0
        sys.exit('unexpected state: the sheet symbol exists but simulation.kicad_sch or the symbol library differs '
                 'from what this script writes')
    check_pre(text)
    new = edit_root(text)
    check_result(text, new)
    if a.dry_run:
        print(f'dry run: root +{len(new) - len(text)} chars, {SIM_SCH.name} {len(sim_text)} chars; nothing written')
        return 0
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    backup(SCH, stamp)
    backup(SYM_LIB, stamp)
    SYM_LIB.write_bytes(lib_new.encode('utf-8'))
    SIM_SCH.write_bytes(sim_text.encode('utf-8'))
    SCH.write_bytes(new.encode('utf-8'))
    print(f'applied: {len(SIM_FIELDS)} parts with Sim fields, {len(SIM_EXCLUDED)} excluded from the sim, sheet '
          f'"{SHEET_NAME}" ({SIM_SCH.name}, {len(BLOCKS)} blocks); backups {stamp}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
