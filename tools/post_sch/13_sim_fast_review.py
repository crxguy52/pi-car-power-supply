"""Post-schematic edit 13 (2026-11-05, staff review of 12): a fast default sim and datasheet-referenced model knobs.

Run from the project root with the PDM python (KiCad must not have the schematic open):

    pdm run python -I tools/post_sch/13_sim_fast_review.py [--dry-run]

What and why (staff review of tools/post_sch/12_kicad_sim.py, reports/sim_kicad.md "Staff review"; SPEC 3, 4):
- Speed (coordinator: the default `pdm run sim` / `verify-sch` sim within minutes, not the quarter hour of two
  real-time holds). The cost is one solver landing per oscillator edge (32 768 counts per hold), so scaling C29 down
  would not help (the same number of edges). Instead U5 counts 2^15 / U5_TAPDIV clocks (new CD4541B model parameter
  TAPDIV, lib/spice/cd4541b.lib) with the real R27 / C29 / R28 and the real oscillator; the sheet measures the
  oscillator period on CTC (osc_t1 / osc_t2) and the end of the count (u5_fall), and hold_est adds the remaining
  counts at the measured period. U5_TAPDIV = 1 is the real part (`pdm run sim --full`).
- Root sheet: U5 Sim.Params gains TAPDIV={U5_TAPDIV} (hidden Sim field only; value, footprint and every other field,
  uuid and position unchanged).
- simulation.kicad_sch: the three text items of 12 (note, .param block, analysis block) are replaced in place (same
  uuid, same position):
  - defaults = the FAST nominal key cycle (U5_TAPDIV 256, run to 1 s after the key-off), so Inspect > Simulator
    opens with a run of about a minute instead of a 50 s real-time transient (assumption: the lead wants a usable
    GUI default; the real-time run is the documented --full override);
  - `.options method=gear` without interp (the period measurement needs the raw time points; --full adds interp
    back to keep 15 M points off memory);
  - measurement windows as parameters (T_CW0 / T_CW1 counting window after the key-off, T_VON0 start of the
    on-window), so the fast and real-time runs share one set of .meas lines;
  - new parameters CGD_FAC (FET gate-drain capacitance factor; the hot-plug runs use the maximum curve) and CIN_U8
    (C15 + C17 on VIN, missing from 12's U8 stand-in), both used by lib/spice/.
- tools/post_sch/12_kicad_sim.py accepts this result as "already applied" (its guard calls expected_sim() here).

Guards: refuses if a KiCad lock file exists. Accepts two states: (1) pre-edit = exactly 12's result (the sim sheet
equals what 12 writes, U5 Sim.Params is 12's); (2) applied = what this script writes ("already applied"). Anything
else stops. Backups to pi_power_board-backups/ first; CRLF kept; text-level; nothing else changes (checked).
"""
import argparse
import datetime
import importlib.util
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCH = ROOT / 'pi_power_board.kicad_sch'
SIM_SCH = ROOT / 'simulation.kicad_sch'
BACKUPS = ROOT / 'pi_power_board-backups'
LOCKS = (ROOT / '~pi_power_board.kicad_sch.lck', ROOT / '~simulation.kicad_sch.lck')
NL = '\r\n'


def _load_12():
    spec = importlib.util.spec_from_file_location('post_sch_12', HERE / '12_kicad_sim.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- root sheet: U5 Sim.Params
U5_PARAMS_OLD = 'HYS={U5_HYS} RDRV={U5_RDRV} IDD={U5_IDD}'
U5_PARAMS_NEW = 'HYS={U5_HYS} RDRV={U5_RDRV} IDD={U5_IDD} TAPDIV={U5_TAPDIV}'

# ---------------------------------------------------------------- simulation sheet: the three text items
NOTE_TEXT = ('SIM-ONLY SHEET: not on the board or in the BOM. Inspect > Simulator: FAST default (U5 count / U5_TAPDIV). '
             'pdm run sim; --full: real time (tools/run_sim.py, reports/sim_kicad.md)')

PARAM_TEXT = '''* SIM-ONLY (tools/post_sch/12, 13): defaults = the FAST nominal key cycle at 12 V, one key cycle
* FAST: U5 counts 2^15 / U5_TAPDIV clocks on the real R27 / C29 / R28; hold_est adds the rest at the measured period.
* Real time: U5_TAPDIV=1, T_PIOFF / T_CW1 unscaled, T_STOP past the hold, .options interp (pdm run sim --full)
* corners (tools/run_sim.py): R27 / C29 factors, U5 oscillator, diodes, FET V_GS(th) and C_gd, zener, U5 current
.param RFAC=1 CFAC=1 C8_RET=0.7
.param U5_HYS=0.054 U5_RDRV=129 U5_IDD=0.3m U5_TAPDIV=256 N_CNT=32768
.param IS_D=1.5e-10 BVZ=5.1 VTO_N=1.6 IDSS_N=0 VTO_P=-2.0 IDSS_P=0 CGD_FAC=1
* battery, key, SW1
.param VB=12 RHARN=50m LHARN=1u T_PLUG=10m TEDGE=1m
.param ACC_V=12 T_ON1=1 T_OFF1=5 T_ON2=1e3 T_OFF2=1.001e3
.param SW_EN=0 T_SW_ON=1 T_SW_OFF=5
* Pi load (constant power) and GPIO pull-up
.param CVOUT=674u VUV=4.5 P_RUN=27 P_AFTER=2 T_PIOFF=5.0117 T_PISD=3 VPI=3.3 RPI=50k
* U8 stand-in (CIN_U8: C15 + C17 effective), USB load, overload
.param V5SET=5.09 UV_ON=4.5 UV_OFF=4.32 T_SS=3.5m C5V1=48u CIN_U8=5u RFB=63.6k I_USB=3 ETA=0.91 ILIM=4.7
.param OVL=0 R_OVL=0.5 T_OVL=13 T_HWAIT=1.255m T_HOFF=40.16m
* windows after the last ACC / SW1 falling edge T_LASTOFF: counting T_CW0 to T_CW1, VOUT on from T_VON0;
* U5 period between the CTC rising edges N_P1 and N_P2; logic threshold VTH_MEAS
.param T_LASTOFF=5 T_CW0=20m T_CW1=78.1m T_VON0=1.5 N_P1=16 N_P2=80 VTH_MEAS=2.5
* output grid T_STEP (with interp); T_END = last point; keep T_STEP / T_STOP / T_MAX equal to the .tran numbers
.param T_STOP=6 T_STEP=1m T_MAX=1m T_ENDWIN=0.3
.param T_END={T_STOP-2*T_STEP}'''

ANALYSIS_TEXT = '''.options method=gear
.save V(/BATT) V(/ACC_IN) V(/ACC_G) V(/HOLD_G) V(/VOUT) V(/VDD_TMR) V(/U5_OUT) V(/ACC_N) V(/+5V1) V(/U5_CTC)
.tran 1m 6 0 1m uic
* hold: last ACC / SW1 falling edge to VOUT falling through VB / 2
.meas TRAN vout_fall FIND time WHEN V(/VOUT)={VB/2} TD={T_LASTOFF} FALL=1
.meas TRAN hold PARAM='vout_fall - T_LASTOFF'
.meas TRAN vout_fall_last FIND time WHEN V(/VOUT)={VB/2} FALL=LAST
.meas TRAN vout_rise_last FIND time WHEN V(/VOUT)={VB/2} RISE=LAST
* U5: end of the count, oscillator period on CTC (raw points: no interp), the hold with all N_CNT counts
.meas TRAN u5_fall FIND time WHEN V(/U5_OUT)={VTH_MEAS} TD={T_LASTOFF} FALL=1
.meas TRAN osc_t1 FIND time WHEN V(/U5_CTC)={VTH_MEAS} TD={T_LASTOFF} RISE={N_P1}
.meas TRAN osc_t2 FIND time WHEN V(/U5_CTC)={VTH_MEAS} TD={T_LASTOFF} RISE={N_P2}
.meas TRAN t_osc PARAM='(osc_t2 - osc_t1)/(N_P2 - N_P1)'
.meas TRAN hold_est PARAM='hold + (N_CNT - N_CNT/U5_TAPDIV)*t_osc'
* on / counting: VOUT never dips, VDD_TMR range, HOLD_G, J5
.meas TRAN vout_min_on MIN V(/VOUT) FROM={T_VON0} TO={T_LASTOFF+T_CW1}
.meas TRAN vtmr_cnt_min MIN V(/VDD_TMR) FROM={T_LASTOFF+T_CW0} TO={T_LASTOFF+T_CW1}
.meas TRAN vtmr_cnt_max MAX V(/VDD_TMR) FROM={T_LASTOFF+T_CW0} TO={T_LASTOFF+T_CW1}
.meas TRAN holdg_cnt_min MIN V(/HOLD_G) FROM={T_LASTOFF+T_CW0} TO={T_LASTOFF+T_CW1}
.meas TRAN j5_on_max MAX V(/ACC_N) FROM={T_ON1+0.5} TO={T_OFF1}
.meas TRAN j5_off_min MIN V(/ACC_N) FROM={T_LASTOFF+T_CW0} TO={T_LASTOFF+T_CW1}
* end: VOUT / VDD_TMR / HOLD_G off in the last T_ENDWIN, no re-latch
.meas TRAN vout_end_max MAX V(/VOUT) FROM={T_STOP-T_ENDWIN} TO={T_END}
.meas TRAN vtmr_end_max MAX V(/VDD_TMR) FROM={T_STOP-T_ENDWIN} TO={T_END}
.meas TRAN holdg_end_max MAX V(/HOLD_G) FROM={T_STOP-T_ENDWIN} TO={T_END}
* battery hot-plug, key off: VOUT, VDD_TMR, HOLD_G before the first key-on
.meas TRAN hp_vout_max MAX V(/VOUT) FROM=0 TO={min(min(T_ON1, T_SW_ON)-TEDGE, T_END)}
.meas TRAN hp_vtmr_max MAX V(/VDD_TMR) FROM=0 TO={min(min(T_ON1, T_SW_ON)-TEDGE, T_END)}
.meas TRAN hp_holdg_max MAX V(/HOLD_G) FROM=0 TO={min(min(T_ON1, T_SW_ON)-TEDGE, T_END)}'''


def text_head(m12, body):
    return f'\t(text "{m12.q(body)}"{NL}'


def expected_sim(sim_12, m12=None):
    """13's simulation.kicad_sch from 12's (the three text bodies replaced); SystemExit if 12's text is not there."""
    m12 = m12 or _load_12()
    out = sim_12
    for old, new in ((m12.NOTE_TEXT, NOTE_TEXT), (m12.PARAM_TEXT, PARAM_TEXT), (m12.ANALYSIS_TEXT, ANALYSIS_TEXT)):
        a, b = text_head(m12, old), text_head(m12, new)
        if out.count(a) != 1:
            raise SystemExit('unexpected state: a text item of 12 is not on the simulation sheet exactly once')
        out = out.replace(a, b)
    return out


def edit_root(text):
    a = f'(property "Sim.Params" "{U5_PARAMS_OLD}"'
    if text.count(a) != 1:
        raise SystemExit("unexpected state: U5's Sim.Params is not 12's value (exactly once)")
    i = text.index(a)
    block_start = text.rfind('\n\t(symbol' + NL, 0, i)
    if '(property "Reference" "U5"' not in text[block_start:i]:
        raise SystemExit('unexpected state: the Sim.Params value found is not on U5')
    return text.replace(a, f'(property "Sim.Params" "{U5_PARAMS_NEW}"')


def check_result(m12, old_root, new_root, old_sim, new_sim):
    """Only U5's Sim.Params and the three text bodies change; item counts, uuids and positions are kept."""
    if old_root.replace(U5_PARAMS_OLD, U5_PARAMS_NEW) != new_root or old_root.count(U5_PARAMS_OLD) != 1:
        raise SystemExit('check: the root sheet changed beyond U5 Sim.Params')
    a, b = m12.top_items(old_sim), m12.top_items(new_sim)
    if len(a) != len(b):
        raise SystemExit('check: simulation sheet item count changed')
    changed = [(old_sim[s0:e0], new_sim[s1:e1]) for (s0, e0), (s1, e1) in zip(a, b) if old_sim[s0:e0] != new_sim[s1:e1]]
    if len(changed) != 3:
        raise SystemExit(f'check: {len(changed)} simulation sheet items changed, expected 3')
    for x0, x1 in changed:
        tail0 = x0[x0.index(NL):]
        tail1 = x1[x1.index(NL):]
        if not x0.startswith('\t(text "') or tail0 != tail1:
            raise SystemExit('check: a changed item is not a text body (uuid / position / effects must stay)')
    for line in ANALYSIS_TEXT.splitlines() + PARAM_TEXT.splitlines():
        if re.search(r'\{[^}]*$', line):
            raise SystemExit(f'check: unbalanced brace in a directive: {line}')


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
    m12 = _load_12()
    raw = SCH.read_bytes()
    if b'\r\n' not in raw or not SIM_SCH.exists():
        sys.exit('unexpected state: the root sheet is not CRLF, or simulation.kicad_sch is missing (run 12 first)')
    root = raw.decode('utf-8')
    sim_now = SIM_SCH.read_bytes().decode('utf-8')
    sim_12 = m12.build_sim_sheet(m12.root_uuid(root))
    sim_13 = expected_sim(sim_12, m12)
    if sim_now == sim_13 and root.count(f'"Sim.Params" "{U5_PARAMS_NEW}"') == 1 and U5_PARAMS_OLD + '"' not in root:
        print('already applied')
        return 0
    if sim_now != sim_12:
        sys.exit('unexpected state: simulation.kicad_sch is neither 12\'s nor 13\'s result')
    new_root = edit_root(root)
    check_result(m12, root, new_root, sim_now, sim_13)
    if a.dry_run:
        print(f'dry run: root {len(new_root) - len(root):+d} chars, {SIM_SCH.name} {len(sim_13) - len(sim_now):+d} '
              'chars; nothing written')
        return 0
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    backup(SCH, stamp)
    backup(SIM_SCH, stamp)
    SIM_SCH.write_bytes(sim_13.encode('utf-8'))
    SCH.write_bytes(new_root.encode('utf-8'))
    print(f'applied: U5 Sim.Params + TAPDIV, {SIM_SCH.name} note / .param / analysis texts; backups {stamp}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
