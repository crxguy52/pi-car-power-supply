"""Delay-off timer sim from the schematic (KiCad 10 netlist, KiCad's ngspice): pdm run sim.

    python -I tools/run_sim.py [--full] [--selftest] [--only NAME ...] [--jobs N] [--list]
    python -I tools/run_sim.py --worker DECK.cir          (internal: one ngspice run, prints JSON)

1. `kicad-cli sch export netlist --format spice` -> build/sim/pi_power_board.cir. The circuit, the models
   (lib/spice/), the sim-only bench (simulation.kicad_sch) and the .param / .tran / .meas directives all come from the
   schematic; this script only rewrites .param values per scenario (every name it overrides must exist exactly once),
   the .tran numbers and the interp option.
2. Each scenario runs in its own process (KiCad's ngspice.dll through ctypes, shared mode), in parallel, under a
   timeout.
3. The .meas results are checked against the limits below (named, with their SPEC section).

Two modes, the same scenarios and checks:
- FAST (default, `pdm run sim`, inside `pdm run verify-sch`): U5 counts 2^15 / TAPDIV clocks (CD4541B model
  parameter TAPDIV) with the real R27 / C29 / R28 and the real oscillator. The sheet measures the oscillator period
  on CTC (t_osc, raw time points: no interp); hold_est = the measured hold + the remaining counts x t_osc. A count
  check proves the counter stopped at 2^15 / TAPDIV. Times inside the count (Pi shutdown, overload start, restart)
  are scaled by 1 / TAPDIV; key-on, blip, hot-plug and turn-off are physical and stay.
  What it cannot see: anything that needs the whole count in real time (a slow drift during the count, the collapse
  seconds after the turn-off): that is --full.
- FULL (`pdm run sim --full`): TAPDIV 1, real time, .options interp (one point per T_STEP), every check at real
  values; the cost is one solver landing per oscillator edge, 2^15 per hold.
--selftest: deliberately broken decks (MUTATIONS), fast mode; each one must FAIL a check, else the selftest fails.
Results: build/sim/results.json and a table on stdout. Exit code 0 only if every scenario passes (and, with
--selftest, every mutation is caught).
"""
import argparse
import concurrent.futures
import ctypes
import json
import os
import pathlib
import re
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import toolchain  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCH = ROOT / 'pi_power_board.kicad_sch'
OUT = ROOT / 'build' / 'sim'
DECK = OUT / 'pi_power_board.cir'
RESULTS = OUT / 'results.json'
EXPORT_TIMEOUT_S = 120.0
RUN_TIMEOUT_S = 3600.0
# real run errors (a failed .meas, e.g. no VOUT fall in a hot-plug run, is a missing value instead)
NGSPICE_ERROR = re.compile(r'circuit not parsed|timestep too small|singular|aborted|error on line|could not find|'
                           r'unknown (?:model|subckt|parameter)', re.I)

# ---------------------------------------------------------------- limits (SPEC sections in brackets)
HOLD_MIN_S = 25.0                    # [3] project lead: >= 25 s after the last key-off, worst case
HOLD_TOL = 0.02                      # regression vs the LTspice deck per corner (same k calibration: not independent)
LTSPICE_HOLD_S = {1: (26.16, 26.20), 2: (29.56, 29.61), 3: (32.56, 32.61)}   # [3] key-off delay per corner
N_CNT = 2 ** 15                      # [3] U5 A = B = 1: the output changes after 2^(16-1) counts
COUNT_TOL = 2.0                      # fast: counts from the key-off to U5 OUT falling = N_CNT / TAPDIV within this
EDGE_TOL_S = 5e-3                    # "the same edge" for two .meas times
VOUT_ON_DROP_V = 1.0                 # VOUT >= VB - this while on / counting (no dip, restart included)
VTMR_MIN_V = 4.40                    # [3] VDD_TMR 4.45-5.71 V while counting (calc), minus model allowance
VTMR_MAX_V = 5.75
HOLDG_CNT_MIN_V = 3.9                # [3] HOLD_G >= 3.94 V while counting (calc)
J5_ON_MAX_V = 0.3                    # [2] J5 low while ACC is on
J5_OFF_MIN_V = 3.0                   # [2] released after key-off (Pi pull-up 3.3 V)
VOUT_END_MAX_V = 2.0                 # full: off at the end of the run (still decaying, no re-latch)
VOUT_END_FAST_FRAC = 0.5             # fast: VOUT below VB x this at the end of the short tail
HOLDG_END_MAX_V = 0.5                # [3] Q5 stays off (hot threshold 0.75 V)
HOTPLUG_VOUT_MAX_V = 0.1             # [3] battery hot-plug with the key off: Q1 stays off
VDD_MIN_V = 3.0                      # [2] U5 operating minimum: VDD_TMR below it at the end (full)

# ---------------------------------------------------------------- corners (as ltspice/delay_off_counter.cir)
# U5_HYS / U5_RDRV: oscillator calibration (lib/spice/cd4541b.lib, reports/sim_kicad.md): k = period / (RTC CTC) of
# the model at VDD 5.1 V is 2.153 / 2.302 / 2.451 (short / nominal / long settings), against design_calc's bound
# 2.104 / 2.3 / 2.450. These knobs are FITTED to design_calc: the sim reproduces the calc's delay, it does not
# confirm the k bound (reports/sim_kicad.md). The short corner has no hysteresis and no driver resistance (the
# model's fastest); K_ALLOW applies the remaining -2 % model allowance of design_calc as a factor on C29.
# VTO_N / VTO_P are datasheet V_GS(th) at 250 uA (lib/spice/pipwr_parts.lib converts them to the VDMOS V_to).
K_BOUND_SHORT = 2.104
K_MODEL_SHORT = 2.153
K_ALLOW_SHORT = K_BOUND_SHORT / K_MODEL_SHORT
CORNERS = {
    1: {'RFAC': 0.99 * 0.99, 'CFAC': 0.99 * 0.997 * K_ALLOW_SHORT, 'U5_HYS': 0, 'U5_RDRV': 0, 'U5_IDD': 0.16e-3,
        'IS_D': 1e-12, 'BVZ': 5.57, 'VTO_N': 2.35, 'IDSS_N': 0, 'VTO_P': -2.5, 'IDSS_P': 0},
    2: {},
    3: {'RFAC': 1.01 * 1.01, 'CFAC': 1.01 * 1.003, 'U5_HYS': 0.1024, 'U5_RDRV': 370, 'U5_IDD': 0.54e-3,
        'IS_D': 4.6e-10, 'BVZ': 4.70, 'VTO_N': 0.75, 'IDSS_N': 3e-6, 'VTO_P': -1.1, 'IDSS_P': 10.5e-6},
}
CORNER_NAME = {1: 'short', 2: 'nominal', 3: 'long'}
# hot-plug runs: FET C_gd on the maximum curve: the Vishay SQD50P04-13L typical C_rss curve x 440 / 352 (max / typ
# at 25 V) over the model's C_gd is largest near 5 V V_DS; this factor covers it from 1 to 25 V
CGD_FAC_HOTPLUG = 1.8
# loads (LTspice LOAD 1 / 2 / 3): Pi shuts down T_PISD after key-off, USB stays; full throughout; Pi halted, no USB
P_PI_RUN_W = 27
P_PI_HALT_W = 2
P_PI_OFF_W = 0.05
I_USB_A = 3
LOADS = {1: {'P_AFTER': P_PI_HALT_W, 'I_USB': I_USB_A}, 2: {'P_AFTER': P_PI_RUN_W, 'I_USB': I_USB_A},
         3: {'P_AFTER': P_PI_HALT_W, 'I_USB': 0}}
BATTS = (9, 12, 14.4, 16)
T_ON1_S = 1
T_OFF1_S = 5
T_VON_AFTER_ON_S = 0.5               # the VOUT on-window starts this long after the key-on (Q1 and VOUT ramp done)
T_PISD_S = 3                         # in-count times below are scaled by 1 / TAPDIV
T_RESTART_AFTER_S = 12               # key back on this far into the count ...
T_RESTART_ON_S = 2                   # ... for this long (not scaled: U5 is in reset)
T_OVL_AFTER_S = 8                    # overload starts this far into the count
T_BLIP_S = 50e-3
T_BLIP_EDGE_S = 0.1e-3
T_HOTPLUG_STOP_S = 3
T_NEVER_S = 1e3                      # an event time past the end of the run (PWL times must increase)

FAST_TAPDIV = 256
MODES = {
    # TAPDIV, counting window T_CW0 / T_CW1 after the key-off (T_CW1 scaled with the count), run length after the
    # last off edge, end window, interp
    'fast': {'tapdiv': FAST_TAPDIV, 't_cw0': 20e-3, 't_cw1': 20 / FAST_TAPDIV, 't_after': 1.0, 't_endwin': 0.3,
             'interp': False},
    'full': {'tapdiv': 1, 't_cw0': 0.5, 't_cw1': 20, 't_after': 42, 't_endwin': 5, 'interp': True},
}


def scenario(name, corner, vb, load, kind='key', mode='fast', **extra):
    md = MODES[mode]
    s = md['tapdiv']
    p = dict(CORNERS[corner])
    p.update(LOADS[load])
    p.update({'VB': vb, 'ACC_V': vb, 'T_ON1': T_ON1_S, 'T_OFF1': T_OFF1_S, 'T_LASTOFF': T_OFF1_S,
              'U5_TAPDIV': s, 'T_CW0': md['t_cw0'], 'T_CW1': md['t_cw1'], 'T_ENDWIN': md['t_endwin']})
    if kind == 'restart':
        on2 = T_OFF1_S + T_RESTART_AFTER_S / s
        p.update({'T_ON2': on2, 'T_OFF2': on2 + T_RESTART_ON_S, 'T_LASTOFF': on2 + T_RESTART_ON_S})
    elif kind == 'blip':
        p.update({'T_OFF1': T_ON1_S + T_BLIP_S, 'T_LASTOFF': T_ON1_S + T_BLIP_S, 'TEDGE': T_BLIP_EDGE_S})
    elif kind == 'sw1':
        p.update({'ACC_V': 0, 'SW_EN': 1, 'T_SW_ON': T_ON1_S, 'T_SW_OFF': T_OFF1_S})
    elif kind == 'ovl':
        p.update({'OVL': 1, 'T_OVL': T_OFF1_S + T_OVL_AFTER_S / s, 'P_AFTER': P_PI_OFF_W, 'I_USB': 0})
    p['T_PIOFF'] = p['T_LASTOFF'] + T_PISD_S / s
    p['T_STOP'] = p['T_LASTOFF'] + md['t_after']
    von = T_ON1_S + T_VON_AFTER_ON_S
    p['T_VON0'] = von if von < p['T_LASTOFF'] else p['T_LASTOFF'] + md['t_cw0']
    if kind == 'hotplug':
        p.update({'ACC_V': 0, 'T_ON1': T_NEVER_S, 'T_OFF1': 2 * T_NEVER_S, 'T_ON2': 3 * T_NEVER_S,
                  'T_OFF2': 4 * T_NEVER_S, 'T_SW_ON': T_NEVER_S, 'T_SW_OFF': 2 * T_NEVER_S, 'T_LASTOFF': 0,
                  'T_STOP': T_HOTPLUG_STOP_S, 'T_ENDWIN': 1, 'T_PIOFF': T_NEVER_S, 'T_VON0': 0,
                  'CGD_FAC': CGD_FAC_HOTPLUG})
    p.update(extra)
    return {'name': name, 'corner': corner, 'vb': vb, 'load': load, 'kind': kind, 'mode': mode, 'params': p}


def scenarios(mode):
    """The scenario set: the BATT sweep at the short corner (the >= 25 s guarantee), the long corner with the slow
    collapse (Pi halted, no USB) and the hot-plug margin, restart / blip / SW1 / USB overload."""
    def sc(*a, **k):
        return scenario(*a, mode=mode, **k)
    out = [sc(f'key_short_{vb:g}V', 1, vb, 2) for vb in BATTS]
    out += [sc('key_nominal_12V', 2, 12, 1), sc('key_long_12V', 3, 12, 3), sc('key_long_16V', 3, 16, 3),
            sc('restart_short_12V', 1, 12, 1, 'restart'), sc('blip50ms_short_12V', 1, 12, 1, 'blip'),
            sc('sw1_nominal_12V', 2, 12, 2, 'sw1'),
            sc('usb_overload_nominal_12V', 2, 12, 3, 'ovl'), sc('usb_overload_long_16V', 3, 16, 3, 'ovl'),
            sc('hotplug_long_16V', 3, 16, 3, 'hotplug'), sc('hotplug_short_9V', 1, 9, 3, 'hotplug')]
    return out


# ---------------------------------------------------------------- selftest: broken decks that must FAIL

def _node_sub(ref, index, net):
    """Deck mutation: element line `ref`, node token `index` (1-based after the name) -> net."""
    def f(deck):
        lines = deck.splitlines()
        hits = [i for i, ln in enumerate(lines) if ln.split()[:1] == [ref]]
        if len(hits) != 1:
            raise SystemExit(f'selftest: {ref} not in the deck exactly once')
        t = lines[hits[0]].split(' ')
        t[index] = net
        lines[hits[0]] = ' '.join(t)
        return '\n'.join(lines) + '\n'
    return f


def _line_sub(pattern, repl):
    def f(deck):
        new, n = re.subn(pattern, repl, deck, flags=re.M)
        if n != 1:
            raise SystemExit(f'selftest: pattern {pattern!r} matched {n} times')
        return new
    return f


XU5_A, XU5_QSEL = 10, 8              # XU5 node order: RTC CTC RS AR MR VSS OUT QSEL MODE A B VDD
MUTATIONS = (
    ('U5 A to GND (tap 2^10)', 'key_nominal_12V', _node_sub('XU5', XU5_A, 'GND')),
    ('U5 Q/Q-bar SELECT to GND (output low after reset)', 'key_nominal_12V', _node_sub('XU5', XU5_QSEL, 'GND')),
    ('R29 open (U5 OUT no longer holds HOLD_G)', 'key_nominal_12V', _line_sub(r'^(R29 \S+ \S+) 47k$', r'\1 1e12')),
    ('R27 -10 % (delay below 25 s at the short corner)', 'key_short_9V',
     _line_sub(r'^(R27 \S+ \S+) \{39\.2k\*RFAC\}$', r'\1 {39.2k*0.9*RFAC}')),
    ('C30 open (battery hot-plug)', 'hotplug_long_16V', _line_sub(r'^(C30 \S+ \S+) 100n$', r'\1 1p')),
    ('D6 shorted out (no direct key-on path to HOLD_G)', 'key_short_9V',
     _line_sub(r'^D6 (\S+) (\S+) ', r'D6 \1 \1 ')),
)


# ---------------------------------------------------------------- deck handling

def export_deck():
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = [str(toolchain.Toolchain().kicad_cli), 'sch', 'export', 'netlist', '--format', 'spice', '-o', str(DECK),
           str(SCH)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=EXPORT_TIMEOUT_S)
    if r.returncode != 0 or not DECK.exists():
        raise SystemExit(f'netlist export failed: {(r.stdout + r.stderr).strip()[:400]}')
    return canonical_order(DECK.read_text(encoding='utf-8'))


def canonical_order(deck):
    """Element lines sorted by name at the place of the first one.

    kicad-cli writes the elements in the sheet's item order, and ngspice's convergence depends on the element
    order (2026-11-06: inserting two sim-excluded capacitors reordered the deck and two fast scenarios stopped
    with "timestep too small"). Sorting makes the deck independent of where a symbol sits in the file."""
    lines = deck.splitlines()
    if any(line.startswith('+') for line in lines):
        raise SystemExit('the exported deck has continuation lines: canonical_order() does not handle them')
    if any(line.lower().startswith('.subckt') for line in lines):
        raise SystemExit('the exported deck has an inline .subckt: canonical_order() would move its elements out')
    idx = [i for i, line in enumerate(lines) if line[:1].isalpha()]
    if not idx:
        return deck
    elements = sorted((lines[i] for i in idx), key=lambda line: line.split()[0].upper())
    idx_set = set(idx)
    keep = [line for i, line in enumerate(lines) if i not in idx_set]
    first = idx[0]
    return chr(10).join(keep[:first] + elements + keep[first:]) + chr(10)


def fmt(v):
    return repr(float(v)) if isinstance(v, float) else str(v)


TRAN_LINE = re.compile(r'^\.tran (\S+) (\S+) 0 (\S+) uic$', re.I | re.M)
TRAN_PARAMS = ('T_STEP', 'T_STOP', 'T_MAX')
OPTIONS_LINE = re.compile(r'^\.options method=gear( interp)?$', re.M)


def deck_param(deck, name):
    m = re.search(r'^\.param .*(?<![A-Za-z0-9_])' + re.escape(name) + r'=(\S+)', deck, re.M)
    return m.group(1) if m else None


def apply_params(deck, params, interp):
    """Rewrite NAME=value on the .param lines (every name must appear exactly once), the .tran line and the interp
    option.

    The sheet's .tran line is numeric (the KiCad simulator reads it); it must equal T_STEP / T_STOP / T_MAX."""
    trans = TRAN_LINE.findall(deck)
    defaults = tuple(deck_param(deck, k) for k in TRAN_PARAMS)
    if len(trans) != 1 or trans[0] != defaults:
        raise SystemExit(f'.tran line {trans} must be ".tran T_STEP T_STOP 0 T_MAX uic" with the .param values '
                         f'{dict(zip(TRAN_PARAMS, defaults))}')
    if len(OPTIONS_LINE.findall(deck)) != 1:
        raise SystemExit('the deck must have exactly one ".options method=gear [interp]" line')
    if deck_param(deck, 'N_CNT') != str(N_CNT):
        raise SystemExit(f'the sheet N_CNT must be {N_CNT} (SPEC 3)')
    deck = OPTIONS_LINE.sub('.options method=gear' + (' interp' if interp else ''), deck)
    tran = [fmt(params[k]) if k in params else d for k, d in zip(TRAN_PARAMS, defaults)]
    deck = TRAN_LINE.sub(f'.tran {tran[0]} {tran[1]} 0 {tran[2]} uic', deck)
    lines = deck.splitlines()
    seen = {k: 0 for k in params}
    for i, line in enumerate(lines):
        if not line.lower().startswith('.param '):
            continue
        for k, v in params.items():
            pat = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(k) + r'=\S+')
            line, n = pat.subn(f'{k}={fmt(v)}', line)
            seen[k] += n
        lines[i] = line
    bad = {k: n for k, n in seen.items() if n != 1}
    if bad:
        raise SystemExit(f'.param names not found exactly once in the exported deck: {bad}')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------- ngspice worker (one process per run)

def ngspice_run(deck_path):
    kdir = toolchain.Toolchain().kicad_cli.parent
    os.add_dll_directory(str(kdir))
    dll = ctypes.CDLL(str(kdir / 'ngspice.dll'))
    out = []
    send = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
    stat = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
    ext = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
    cbs = (send(lambda m, i, u: out.append(m.decode(errors='replace')) or 0), stat(lambda m, i, u: 0),
           ext(lambda a, b, c, d, u: 0))
    dll.ngSpice_Init(cbs[0], cbs[1], cbs[2], None, None, None, None)
    t0 = time.time()
    dll.ngSpice_Command(f'source {pathlib.Path(deck_path).as_posix()}'.encode())
    dll.ngSpice_Command(b'run')
    wall = time.time() - t0
    meas, errors = {}, []
    for line in out:
        m = re.match(r'stdout (\w+)\s+=\s+([-+0-9.eE]+)', line)
        if m:
            meas[m.group(1).lower()] = float(m.group(2))
        elif line.startswith('stderr') and NGSPICE_ERROR.search(line):
            errors.append(line[7:].strip())
    rows = next((int(m.group(1)) for line in out for m in [re.search(r'Data Rows : (\d+)', line)] if m), None)
    if not rows:
        errors.append('no transient data')
    return {'meas': meas, 'errors': errors, 'wall_s': wall, 'rows': rows}


def run_one(sc, deck, tag=''):
    path = OUT / f'{sc["name"]}{tag}.cir'
    path.write_text(apply_params(deck, sc['params'], MODES[sc['mode']]['interp']), encoding='utf-8')
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, '-I', __file__, '--worker', str(path)], capture_output=True, text=True,
                           timeout=RUN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {'meas': {}, 'errors': [f'timeout {RUN_TIMEOUT_S:g} s'], 'wall_s': time.time() - t0, 'rows': None}
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {'meas': {}, 'errors': [f'worker failed: {(r.stdout + r.stderr).strip()[-400:]}'],
                'wall_s': time.time() - t0, 'rows': None}


# ---------------------------------------------------------------- checks

def checks(sc, m):
    """[(name, ok, text)] for one scenario."""
    p = sc['params']
    vb = p['VB']
    fast = sc['mode'] == 'fast'
    out = []

    def chk(name, ok, text):
        out.append((name, bool(ok), text))

    def get(k):
        return m.get(k)

    if sc['kind'] == 'hotplug':
        v = get('hp_vout_max')
        chk('hot-plug: Q1 stays off', v is not None and v <= HOTPLUG_VOUT_MAX_V,
            f'VOUT max {v} V (limit {HOTPLUG_VOUT_MAX_V})')
        v = get('vout_end_max')
        chk('hot-plug: VOUT off at the end', v is not None and v <= HOTPLUG_VOUT_MAX_V, f'VOUT {v} V')
        return out
    # fast: the extrapolated hold; full: the measured one (with interp the CTC period measurement aliases)
    hold = get('hold_est') if fast else get('hold')
    if fast:
        # the extrapolation is only valid if U5 OUT fell at the expected count
        u5, t_osc = get('u5_fall'), get('t_osc')
        n_exp = N_CNT / p['U5_TAPDIV']
        n = (u5 - p['T_LASTOFF']) / t_osc if None not in (u5, t_osc) and t_osc > 0 else None
        count_ok = n is not None and abs(n - n_exp) <= COUNT_TOL
        chk('U5 count = 2^15 / TAPDIV', count_ok, f'{n} counts to U5 OUT low, expected {n_exp:g}')
        hold = hold if count_ok else None
    lo, hi = LTSPICE_HOLD_S[sc['corner']]
    chk('hold >= 25 s', hold is not None and hold >= HOLD_MIN_S, f'hold {hold} s')
    chk('hold vs LTspice', hold is not None and lo * (1 - HOLD_TOL) <= hold <= hi * (1 + HOLD_TOL),
        f'{hold} s vs LTspice {lo}-{hi} s (+-{HOLD_TOL:.0%})')
    fall, fall_last, rise_last = get('vout_fall'), get('vout_fall_last'), get('vout_rise_last')
    chk('one turn-off, no re-latch', None not in (fall, fall_last, rise_last)
        and abs(fall_last - fall) <= EDGE_TOL_S and rise_last < fall,
        f'first fall {fall}, last fall {fall_last}, last rise {rise_last}')
    v = get('vout_min_on')
    chk('VOUT on, no dip', v is not None and v >= vb - VOUT_ON_DROP_V, f'VOUT min {v} V')
    a, b = get('vtmr_cnt_min'), get('vtmr_cnt_max')
    chk('VDD_TMR while counting', None not in (a, b) and VTMR_MIN_V <= a and b <= VTMR_MAX_V, f'{a}-{b} V')
    v = get('holdg_cnt_min')
    chk('HOLD_G while counting', v is not None and v >= HOLDG_CNT_MIN_V, f'{v} V')
    if sc['kind'] not in ('sw1', 'blip'):
        v = get('j5_on_max')
        chk('J5 low while ACC on', v is not None and v <= J5_ON_MAX_V, f'{v} V')
    v = get('j5_off_min')
    chk('J5 released after key-off', v is not None and v >= J5_OFF_MIN_V, f'{v} V')
    a, b, c = get('vout_end_max'), get('holdg_end_max'), get('vtmr_end_max')
    if fast:
        chk('off at the end of the tail', None not in (a, b) and a <= vb * VOUT_END_FAST_FRAC
            and b <= HOLDG_END_MAX_V, f'VOUT {a} V, HOLD_G {b} V')
    else:
        chk('off at the end', None not in (a, b, c) and a <= VOUT_END_MAX_V and b <= HOLDG_END_MAX_V
            and c < VDD_MIN_V, f'VOUT {a} V, HOLD_G {b} V, VDD_TMR {c} V')
    v = get('hp_vout_max')
    chk('hot-plug before key-on: Q1 off', v is not None and v <= HOTPLUG_VOUT_MAX_V, f'VOUT {v} V')
    return out


def evaluate(sc, r):
    return checks(sc, r['meas']) if not r['errors'] else [('ngspice run', False, '; '.join(r['errors'][:3]))]


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--worker', type=pathlib.Path)
    ap.add_argument('--full', action='store_true', help='real time (TAPDIV 1); default: fast mode')
    ap.add_argument('--selftest', action='store_true', help='also run the broken decks (fast); each must FAIL')
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--jobs', type=int, default=None, help='parallel ngspice workers (default: one per logical core)')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args(argv[1:])
    if a.worker:
        print(json.dumps(ngspice_run(a.worker)))
        return 0
    mode = 'full' if a.full else 'fast'
    scs = scenarios(mode)
    if a.list:
        for sc in scs:
            print(sc['name'])
        return 0
    if a.only:
        scs = [s for s in scs if s['name'] in a.only]
        if not scs:
            raise SystemExit('no such scenario')
    deck = export_deck()
    items = [(sc['name'], sc, deck, '') for sc in scs]
    fast_by_name = {s['name']: s for s in scenarios('fast')}
    muts = []
    if a.selftest:
        for i, (label, name, fn) in enumerate(MUTATIONS, 1):
            key = f'selftest_{i}'
            muts.append((key, label, fast_by_name[name]))
            items.append((key, fast_by_name[name], fn(deck), f'.{key}'))
    jobs = a.jobs or max(1, min(len(items), os.cpu_count() or 1))
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {k: ex.submit(run_one, sc, d, tag) for k, sc, d, tag in items}
        res = {k: f.result() for k, f in futs.items()}
    fails = 0
    report = []
    print(f'mode {mode}: U5 counts 2^15 / {MODES[mode]["tapdiv"]}')
    for sc in scs:
        r = res[sc['name']]
        cs = evaluate(sc, r)
        ok = all(c[1] for c in cs)
        fails += not ok
        h = r['meas'].get('hold_est' if mode == 'fast' else 'hold')
        print(f'{"PASS" if ok else "FAIL"} {sc["name"]:28s} hold {"-" if h is None else f"{h:7.3f} s"}  '
              f'({r["wall_s"]:.0f} s, {r["rows"]} points)')
        for name, cok, text in cs:
            if not cok:
                print(f'     FAIL {name}: {text}')
        report.append({**sc, **r, 'checks': cs, 'pass': ok})
    caught = 0
    for key, label, sc in muts:
        r = res[key]
        cs = evaluate(sc, r)
        failed = [c[0] for c in cs if not c[1]]
        caught += bool(failed)
        print(f'{"caught" if failed else "MISSED"} {key}: {label} ({sc["name"]}): '
              f'{", ".join(failed) if failed else "every check passed"}  ({r["wall_s"]:.0f} s)')
        report.append({**sc, **r, 'name': key, 'mutation': label, 'checks': cs, 'caught': bool(failed)})
    RESULTS.write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(f'sim: {len(scs) - fails} of {len(scs)} scenarios pass'
          + (f'; selftest {caught} of {len(muts)} mutations caught' if muts else '')
          + f'; {time.time() - t0:.0f} s wall ({jobs} jobs); {RESULTS.relative_to(ROOT)}')
    return 1 if fails or caught < len(muts) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
