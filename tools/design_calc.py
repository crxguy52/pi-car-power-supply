"""Design calculations for the Pi power HAT (SPEC 2-4, reports/sim_delay_off_counter.md, reports/buck_design.md):
one record of every computed value.

    pdm run python -I tools/design_calc.py            # console + build/design_calc.log
    pdm run python -I tools/design_calc.py --history  # also the superseded LM2903B RC timer (comparator, timer)

2026-11-05: the delay-off timer is a CD4541B clock + counter (counter_timer()), on VDD_TMR from VOUT (u5_supply()); the LM2903B functions
(comparator(), acc_status_led(), timer(), recharge()) are kept unchanged as the record of the superseded design.

Each block takes its constants from the datasheet section named next to it (PDFs in ref/datasheets/). Pure Python
(complex arithmetic for the buck loop), no numpy. Values are printed, not written into the SPEC: the SPEC quotes them.
The previous (TLC555 / LM397) version: pi_power_board-backups/design_calc_2026-11-04_231351.py.
"""
import cmath
import logging
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / 'build' / 'design_calc.log'
LOG_FORMAT = '%(asctime)s - %(name)-40s - %(levelname)-8s - %(message)s'
log = logging.getLogger('design_calc')

# ---------------------------------------------------------------- operating points (SPEC 4)
VB_MIN, VB_NOM, VB_MAX = 9.0, 12.0, 14.4         # operating battery range
VB_STANDOFF = 16.0                               # TVS working voltage: highest continuous BATT
VB_LIST = (VB_MIN, VB_NOM, VB_MAX)
V_HARNESS_RISE = 0.5                             # BATT rise at the board when the load stops (assumption: full load through the harness)
T_AMB_HOT = 85.0
T_DATASHEET = 25.0

# ---------------------------------------------------------------- TVS1/TVS2: Bourns SMBJ datasheet, SMBJ16A row
TVS_VC_1, TVS_IPP_1 = 26.0, 23.1                 # long-pulse clamp column
TVS_VC_2, TVS_IPP_2 = 33.8, 115.5                # short-pulse clamp column
TVS_IR_MAX = 1e-6
ABS_MAX = {                                      # lowest abs max on each net
    'buck VIN (TPS54336A SLVSCD5D 6.1)': 30.0,
    'Q1 VDS (SQD50P04-13L)': 40.0,
    'Q5 / Q6 VDS (2N7002BK)': 60.0,
    'D4 / D5 VRRM (1N4148W)': 100.0,
}

# ---------------------------------------------------------------- U1 LM2903B (TI SLCS005AH 5.1, 5.2, 5.6)
U1_IQ_TYP_5V = 400e-6                            # both comparators, low-supply row, room temperature
U1_IQ_TYP_36V, U1_IQ_MAX_36V = 550e-6, 800e-6
U1_IQ_V_LO, U1_IQ_V_HI = 5.0, 36.0               # supply voltages of the two quiescent-current rows
U1_IB_MAX = 50e-9                                # out of each input (PNP), full temperature range
U1_VIO_MAX = 4e-3                                # full temperature range
U1_VOL_MAX = 0.55                                # limit at the datasheet sink current, full temperature range (bound)
U1_VOL_TYP = 0.05                                # at the gate-network sink current (sim corner 2 value)
U1_ILKG_MAX = 50e-9                              # output off, datasheet test row
U1_IO_ABS = 25e-3                                # output current abs max, B version
U1_CM_HEADROOM_HOT = 2.0                         # common-mode headroom below VCC over temperature

# ---------------------------------------------------------------- reference divider + hysteresis (SPEC 3)
R4, R5, R23 = 1.8e6, 1.0e6, 4.7e6                # BATT-REF, REF-GND, REF-DRV (hysteresis)
R_TOL = 0.01

# ---------------------------------------------------------------- Q1 SQD50P04-13L (Vishay 65157 rev D) and gate
R14, R15 = 220e3, 180e3                         # gate-source pull-up, gate to U1A output
Q1_VGS_MAX = 20.0
Q1_VTH_MIN, Q1_VTH_MAX = 1.5, 2.5                # magnitude, datasheet static table
Q1_VTH_TC = -4e-3                                # per K (assumption: datasheet graph not digitised)
Q1_RDS_45_MAX, Q1_RDS_HOT_FACTOR = 22e-3, 1.54   # max at the lower VGS test point; hot factor from the datasheet graph (bound)
Q1_RTHJA = 50.0
Q1_QGD_TYP, Q1_CISS_TYP = 14.7e-9, 2.872e-9      # typicals, datasheet dynamic table
Q1_IGSS = 100e-9
Q1_CGD_MAX = 2.2e-9                              # the sim's VDMOS Cgd at low VDS (stand-in, delay_off_lm393.cir)
C30 = 100e-9                                     # Q1 gate-source capacitor (battery hot-plug, 2026-11-05)
Q1_IDSS_25 = 1e-6
VGS_RDS_SPEC = 4.5
SOA_W_1MS_25C, SOA_W_100US_25C = 300.0, 2000.0   # single pulse at the reference case temperature (datasheet SOA graph)
SOA_W_10MS_25C = 130.0                           # 10 ms line read at 40 V (3.3 A), same graph
SOA_W_100MS_25C = 100.0                          # 100 ms line read at 40 V (2.5 A), same graph
P_LOAD_FULL = 42.0                               # Pi + buck at full load (SPEC 4: 3.5 A at 12 V)
Q1_QGD_MAX = 22e-9                               # datasheet dynamic table
I_TURN_OFF = 5.0                                 # load still on at the end of the hold (brief: 5 A, the 9 V case)
# TPS54336A hiccup (SLVSCD5D 6.6 timing, 7.3.13): wait / off in switching cycles, internal fsw range
HICCUP_WAIT_CYC, HICCUP_OFF_CYC = 512, 16384
FSW_RANGE = (272e3, 408e3)
U8_ILIM_RANGE = (3.5, 6.1)                       # SLVSCD5D 6.5 low-side sourcing current limit
U8_OVL_R = (0.5, 0.8, 1.0)                       # overload resistances on +5V1 in the OVL sims
TJ_MAX_Q1 = 175.0
Q1_SELF_HEAT = 40.0                              # junction above ambient for the hot threshold case (assumption)
C_VOUT = 674e-6                                  # VOUT capacitance incl. the Pi regulator (assumption, as before)
V_PLATEAU = (1.5, 3.0)                           # Miller plateau magnitude range used for the gate current
VB_LOW_CRANK = (6.0, 7.0, 8.0)                   # cranking dips below the operating range

# ---------------------------------------------------------------- ACC sense, status, LED
R8 = 47e3                                        # ACC_S pull-down
R24 = 1.0e3                                      # charge series into D6 / C5
SW1_I_SWITCH = 25e-3                             # Nidec CAS catalogue switching rating
BAS116_IF_MAX, BAS116_IFSM = 200e-3, 500e-3
R21 = 1.5e3                                      # J5 series
R_PU_PI, V_PI = 50e3, 3.3                        # Pi GPIO pull-up (assumption: not in ref/)
I_ACC_GHOST = 10e-6                              # leakage an "off" ACC line might still source (assumption)
LED_VF_TYP = 2.0                                 # LTST-C150KRKT
R3 = 5.1e3

# ---------------------------------------------------------------- delay-off timer (SPEC 3)
R9 = 4.7e6
C5_EACH = 10e-6                                  # one timing capacitor, nominal: Cal-Chip GMC31X7R106K50NT
C5_N = 3                                         # C5, C27, C28 in parallel (SPEC 3)
C5_NOM = C5_N * C5_EACH                          # timing capacitance, nominal
DCB_SLOPE = 0.04                                 # retention = 1 - slope x V (assumption: conservative, BOM verifies)
DCB_FLOOR = 0.3
C_TOL, C_TEMP = 0.10, 0.15                       # X7R tolerance (K), X7R temperature limit (GMC datasheet p. 1)
C_AGING_PER_DECADE = 0.02                        # GMC datasheet p. 1: X7R aging below this per decade hour
AGING_DECADES = 5                                # from about an hour after the last soldering heat to about 11
#                                                  years (assumption: the tolerance reference time is not stated)
C_AGING = C_AGING_PER_DECADE * AGING_DECADES     # capacitance loss over the service life
C5_IR_OHM_F = 1000.0                             # GMC datasheet p. 1, X7R: insulation >= this (ohm x farad), 25 and
#                                                  125 C rows (both print the same figure: BOM / bench verifies)
C5_IR_OHM_F_TYPICAL_MIN = 100.0                  # Samsung CL31B106KBHNNNE spec p. 2 (25 C): the common X7R minimum
C5_IR_MIN = C5_IR_OHM_F / C5_NOM                 # network insulation resistance used in the short stack
D6_IR_MAX = 80e-9                                # BAS116LT1G hot reverse-current limit (bound)
VF_UA = (0.67, 0.50, 0.40)                       # diode drop at microamps: max (model fitted to the BAS116
#                                                  datasheet maxima) / nominal / low (assumption)
VF_COLD_ADD = 0.13                               # extra drop when cold (assumption)
DELAY_TARGET = 45.0                              # LM2903B history only (timer(), recharge()); the counter: HOLD_TARGET
T_STEP = 1e-3
T_GIVE_UP = 600.0
IR_SEARCH, IR_ITER = (1e5, 1e12), 40             # C5 network insulation search range for the target, bisection steps
V0_ITER = 30                                     # bisection steps for the C5 voltage needed at key-off
R0805_P = 0.125                                  # 0805 thick-film continuous rating (TODO: pulse curve of the part)

# ---------------------------------------------------------------- buck TPS54336A (SLVSCD5D)
# 2026-11-06 (reports/ic_review.md flags): L1 15 uH, Cin 2 x 10 uF, Cout 4 x 47 uF, FB divider and COMP retuned
VREF, VREF_TOL = 0.8, 0.015                      # 6.5: 0.788 - 0.812 V over TJ -40 to 150 C
F_SW = 340e3
GM_EA, GM_PS = 1300e-6, 8.0
I_OUT = 3.0
I_HS_LIMIT_MAX = 6.5                             # 6.5: high-side current limit, max
V_IN_MAX = 16.0                                  # TVS standoff: highest continuous VIN
K_IND_MAX = 0.3                                  # 8.2.2.6.1: "as high as 0.3" with ceramic output capacitors
L1 = 15e-6                                       # Bourns SRP1038A-150M
L_TOL = 0.20
L_ISAT, L_IRMS, L_DCR_MAX = 10.0, 6.25, 45e-3    # SRP1038A datasheet table (Isat: L drops 20 %)
L_DCR_TYP = 40e-3
R_FB_TOP, R_FB_BOT = 73.2e3, 13.7e3
USB_VBUS = (4.75, 5.25)                          # USB 2.0 VBUS at the port
V_DROP_BUDGET = 0.10                             # board + connector drop at 3 A, below the sense point (assumption)
C_OUT_N, C_OUT_NOM = 4, 47e-6
DC_BIAS_RETENTION = (0.25, 0.34, 0.60)           # low / design / high: assumption (reports/buck_design.md)
ESR_CER = 3e-3
DI_STEP, DV_STEP_FRAC = 1.5, 0.05                # eq 22 criterion: 1.5 A step, 5 % (the TI example)
V_RIPPLE_OUT = 30e-3                             # eq 23 / 24 criterion (the TI example)
MARGIN_MIN = 0.20                                # required margin on eq 22 / 23 (project lead)
FC_TARGET = 30e3                                 # 7.3.17 step 1: about fsw / 10
R_COMP = 7.32e3
C_COMP = 15e-9
C_HF = 0.0                                       # Type 2B: no high-frequency pole capacitor (SLVSCD5D 7.3.17)
RO_EA, C_OEA = 3.07e6, 20.7e-12                  # error-amplifier output model, SLVSCD5D 7.3.15 small-signal model
I_OUT_LIGHT = 0.1                                # light-load corner of the loop sweep
SAMPLING_Q = (0.3, 0.64, 1.0)                    # current-mode sampling double-pole Q range (assumption)
PM_MIN = 45.0
ESS_I, C_SS = 2.3e-6, 10e-9
C_IN_N, C_IN_NOM, C_IN_RETENTION = 2, 10e-6, 0.5  # retention at 9-16 V: assumption (no Cal-Chip DC-bias curve)
C_IN_ESR = 2e-3                                  # 8.2.2.5: "approximately 2 mOhm" (TI example capacitor)
V_IN_RIPPLE_MAX = 0.4                            # 8.2.2.5: input ripple limit of the TI example
RDS_HS = (128e-3, 230e-3)
RDS_LS = (84e-3, 170e-3)
RTH_JA_DDA = 42.1
V_IN_BUCK = (9.0, 12.0, 14.4, 16.0)
USB_DEVICE_C = 10e-6                             # USB 2.0 device input capacitance limit (inrush)
E96 = (100, 102, 105, 107, 110, 113, 115, 118, 121, 124, 127, 130, 133, 137, 140, 143, 147, 150, 154, 158, 162, 165,
       169, 174, 178, 182, 187, 191, 196, 200, 205, 210, 215, 221, 226, 232, 237, 243, 249, 255, 261, 267, 274, 280,
       287, 294, 301, 309, 316, 324, 332, 340, 348, 357, 365, 374, 383, 392, 402, 412, 422, 432, 442, 453, 464, 475,
       487, 499, 511, 523, 536, 549, 562, 576, 590, 604, 619, 634, 649, 665, 681, 698, 715, 732, 750, 768, 787, 806,
       825, 845, 866, 887, 909, 931, 953, 976)
R_FB_BOT_RANGE = (10e3, 20e3)                    # FB divider search: bottom resistor range


def _vout(r_top, r_bot, vref_dev=0.0, r_dev=0.0):
    """VOUT with the reference and the resistor ratio moved by the given fractions (eq 15 / 16)."""
    return VREF * (1 + vref_dev) * (1 + r_top * (1 + r_dev) / (r_bot * (1 - r_dev)))


V_OUT_TARGET = _vout(R_FB_TOP, R_FB_BOT)

# ---------------------------------------------------------------- TPS54302 (SLVSDG6C) thermal check (rejected option)
TPS54302_RTHJA_JEDEC, TPS54302_RTHJA_EVM = 118.9, 57.2
TPS54302_TJ_REC_MAX = 125.0
TPS54302_VOUT = 5.0                              # output of the fig. 7-2 curve
TPS54302_EFF = {3.0: 0.925, 2.4: 0.935}          # fig. 7-2, read from the graph
L_DCR_TYP_2026_11_05 = 27e-3                     # SRP1038A-100M typical (the inductor of that comparison)
RDS_HOT_ADD = 0.20                               # extra IC loss when hot vs the room-temperature curve (assumption)


def _par(*z):
    return 1 / sum(1 / x for x in z)


def _ref(vb, r_top=R4, r_bot=R5, r_h=R23, vol=0.0, i_in=0.0):
    """REF in both U1A output states. Low (Q1 on): R23 to VOL. High (Q1 off): R23 to BATT through R15 + R14 (Q1
    gate network). i_in = bias current flowing out of the U1 IN+ pins into REF."""
    lo = (vb / r_top + vol / r_h + i_in) / (1 / r_top + 1 / r_bot + 1 / r_h)
    r_hh = r_h + R14 + R15
    hi = (vb / r_top + vb / r_hh + i_in) / (1 / r_top + 1 / r_bot + 1 / r_hh)
    return lo, hi


def _soa_derate():
    return (TJ_MAX_Q1 - T_AMB_HOT) / (TJ_MAX_Q1 - T_DATASHEET)


def tvs_and_ratings():
    log.info('--- TVS SMBJ16A (BATT and ACC_IN) against the lowest abs max per net')
    r_dyn = (TVS_VC_2 - TVS_VC_1) / (TVS_IPP_2 - TVS_IPP_1)
    for name, v in ABS_MAX.items():
        log.info('%-52s %.0f V: margin %.1f V at the %.1f V clamp, %.1f V at %.1f V', name, v, v - TVS_VC_1,
                 TVS_VC_1, v - TVS_VC_2, TVS_VC_2)
    i_at_30 = TVS_IPP_1 + (ABS_MAX['buck VIN (TPS54336A SLVSCD5D 6.1)'] - TVS_VC_1) / r_dyn
    log.info('TVS clamp reaches the buck 30 V abs max at about %.0f A (linear between the datasheet points)', i_at_30)


def comparator():
    log.info('--- U1 LM2903B on BATT: supply, common mode, parked drain')
    for vb in VB_LIST + (VB_STANDOFF,):
        lo, hi = _ref(vb)
        log.info('VB %.1f V: REF %.2f V (Q1 on) / %.2f V (Q1 off); CM top (hot) %.2f V; C5_T at ACC on <= %.2f V '
                 '(IN- above the CM range is allowed: SLCS005 5.6 note 1, 7.2.2.1 case 2)', vb, lo, hi,
                 vb - U1_CM_HEADROOM_HOT, vb - 2 * VF_UA[2])
    for vb in (VB_NOM, VB_STANDOFF):
        iq_typ = U1_IQ_TYP_5V + (U1_IQ_TYP_36V - U1_IQ_TYP_5V) * (vb - U1_IQ_V_LO) / (U1_IQ_V_HI - U1_IQ_V_LO)
        i_div = vb / (R4 + R5)
        i_other = TVS_IR_MAX + Q1_IDSS_25
        typ, worst = iq_typ + i_div + i_other, U1_IQ_MAX_36V + i_div + i_other
        log.info('parked drain at %.1f V: U1 %.0f uA typ (%.0f uA max bound) + REF divider %.1f uA + TVS1/Q1 '
                 'leakage %.1f uA = %.0f uA typ, %.0f uA max; %.1f mAh/day typ, %.2f Ah/month max', vb, iq_typ * 1e6,
                 U1_IQ_MAX_36V * 1e6, i_div * 1e6, i_other * 1e6, typ * 1e6, worst * 1e6, typ * 24 * 1e3,
                 worst * 24 * 30)


def q1_gate():
    log.info('--- Q1 gate: R14 %.0fk (G-S) / R15 %.0fk (G to U1A out)', R14 * 1e-3, R15 * 1e-3)
    k_min = R14 * (1 - R_TOL) / (R14 * (1 - R_TOL) + R15 * (1 + R_TOL))
    k_max = R14 * (1 + R_TOL) / (R14 * (1 + R_TOL) + R15 * (1 - R_TOL))
    log.info('on at %.1f V: VGS >= %.2f V (VOL %.2f V bound, resistors 1 %%) vs %.1f V where RDS(on) <= %.0f mohm',
             VB_MIN, (VB_MIN - U1_VOL_MAX) * k_min, U1_VOL_MAX, VGS_RDS_SPEC, Q1_RDS_45_MAX * 1e3)
    for v in (VB_STANDOFF, TVS_VC_1, TVS_VC_2):
        log.info('VGS at %.1f V: %.1f V (abs max %.0f V)', v, v * k_max, Q1_VGS_MAX)
    for i_load in (3.5, 5.0):
        p = i_load ** 2 * Q1_RDS_45_MAX * Q1_RDS_HOT_FACTOR
        log.info('Q1 at %.1f A: %.2f W hot, TJ %.0f C at TA %.0f C (RthJA %.0f C/W)', i_load, p,
                 T_AMB_HOT + p * Q1_RTHJA, T_AMB_HOT, Q1_RTHJA)
    tj_hot = T_AMB_HOT + Q1_SELF_HEAT
    vth_hot = Q1_VTH_MIN + Q1_VTH_TC * (tj_hot - T_DATASHEET)
    for v in (VB_STANDOFF, TVS_VC_1, TVS_VC_2):
        _, hi = _ref(v)
        i_h = (v - hi) / (R23 + R14 + R15)
        log.info('off at %.1f V: hysteresis current %.2f uA -> VGS %.2f V (+ IGSS %.2f V, U1 leakage %.3f V) vs '
                 'VGS(th) min %.2f V at TJ %.0f C', v, i_h * 1e6, i_h * R14, Q1_IGSS * R14, U1_ILKG_MAX * R14,
                 vth_hot, tj_hot)
    q1_switching()


def q1_switching():
    """Q1 turn-on / turn-off through R14 / R15 (unchanged by the 2026-11-05 counter timer: Q5 replaces U1A on DRV)."""
    log.info('--- Q1 switching through R14 / R15 (Miller plateau, inrush, SOA)')
    r_th = _par(R14, R15)
    k = R14 / (R14 + R15)
    for vb in VB_LIST + (VB_STANDOFF,):
        for v_pl in V_PLATEAU:
            i_g = (vb * k - v_pl) / r_th
            for qf in (1.0, 0.5):
                t_ramp = Q1_QGD_TYP * qf / i_g
                i_in = C_VOUT * vb / t_ramp
                log.info('turn-on VB %.1f V plateau %.1f V Qgd x%.1f: ramp %.0f us, inrush %.0f A, peak %.0f W, '
                         '%.0f mJ; SOA at TC %.0f C: 100 us %.0f W, 1 ms %.0f W', vb, v_pl, qf, t_ramp * 1e6, i_in,
                         vb / 2 * i_in, 0.5 * C_VOUT * vb ** 2 * 1e3, T_AMB_HOT, SOA_W_100US_25C * _soa_derate(),
                         SOA_W_1MS_25C * _soa_derate())
    for vb in VB_LOW_CRANK:
        log.info('BATT %.1f V (cranking, below the operating range): VGS %.2f V typ (VOL typ %.2f V); RDS(on) is '
                 'specified only at %.1f V and up, so Q1 may limit the current (datasheet output curves)', vb,
                 (vb - U1_VOL_TYP) * k, U1_VOL_TYP, VGS_RDS_SPEC)
    t_del = r_th * Q1_CISS_TYP * math.log(VB_NOM * k / (VB_NOM * k - Q1_VTH_MAX))
    log.info('turn-on delay to VGS(th) max at 12 V: %.2f ms (R14||R15 x Ciss)', t_del * 1e3)
    t_del_c30 = r_th * (Q1_CISS_TYP + C30) * math.log(VB_MIN * k / (VB_MIN * k - Q1_VTH_MAX))
    t_off_c30 = R14 * (Q1_CISS_TYP + C30) * math.log(VB_STANDOFF * k / Q1_VTH_MAX)
    log.info('with C30 %.0f nF G-S: turn-on delay to VGS(th) max at %.0f V %.1f ms; turn-off delay from %.0f V '
             'to the threshold %.1f ms; the Miller ramps are unchanged (C30 carries no current on the plateau)',
             C30 * 1e9, VB_MIN, t_del_c30 * 1e3, VB_STANDOFF, t_off_c30 * 1e3)
    for vb in (VB_STANDOFF, TVS_VC_1):
        log.info('battery hot-plug step %.1f V: VGS kick through C_gd max %.1f nF against C30 + Cgs: %.2f V (without '
                 'C30: %.1f V) vs VGS(th) hot min', vb, Q1_CGD_MAX * 1e9, vb * Q1_CGD_MAX / (Q1_CGD_MAX + C30 +
                 Q1_CISS_TYP), vb * Q1_CGD_MAX / Q1_CISS_TYP)
    i_off = V_PLATEAU[1] / R14
    log.info('turn-off: plateau current %.0f uA through R14 -> Miller ramp %.2f ms (Qgd typ)', i_off * 1e6,
             Q1_QGD_TYP / i_off * 1e3)
    # turn-off linear region at the end of the hold, with C30: the Miller ramp (C30 idle, R14 alone charges Cgd),
    # then the current tail from the plateau down to the threshold through R14 x (C30 + Ciss)
    tau_off = R14 * (C30 + Q1_CISS_TYP)
    t_ramp = Q1_QGD_MAX / (V_PLATEAU[0] / R14)
    t_tail = tau_off * math.log(V_PLATEAU[1] / Q1_VTH_MIN)
    t_lin = t_ramp + t_tail
    soa = SOA_W_100MS_25C * _soa_derate()
    for vb, i_load in ((VB_MIN, I_TURN_OFF), (VB_STANDOFF, P_LOAD_FULL / VB_STANDOFF)):
        log.info('turn-off at %.0f V, %.1f A: linear region <= %.1f ms (Miller %.1f ms at Qgd max and a %.1f V '
                 'plateau, tail %.1f ms); rectangle bound %.0f W (VB x I) for that time, %.0f mJ, vs the 100 ms SOA '
                 'line %.0f W at TC %.0f C', vb, i_load, t_lin * 1e3, t_ramp * 1e3, V_PLATEAU[0], t_tail * 1e3,
                 vb * i_load, vb * i_load * t_lin * 1e3, soa, T_AMB_HOT)
    # +5V1 lost during a hold (USB overload -> U8 hiccup): Q5 drops at once, Q1 turns off after the C30 delay;
    # U8 retries after the hiccup off time and, if VOUT is still above its UVLO, U5 restarts (auto reset)
    t_off_min = HICCUP_OFF_CYC / FSW_RANGE[1]
    for vb in (VB_MIN, VB_STANDOFF):
        for vth in (Q1_VTH_MAX, Q1_VTH_MIN + Q1_VTH_TC * (T_HOT - T_DATASHEET)):
            t_q1 = tau_off * math.log(vb * R14 / (R14 + R15) / vth)
            log.info('+5V1 lost at %.0f V: Q1 below VGS(th) %.2f V after %.1f ms vs the hiccup off time >= %.1f ms '
                     '(%d cycles at %.0f kHz)', vb, vth, t_q1 * 1e3, t_off_min * 1e3, HICCUP_OFF_CYC,
                     FSW_RANGE[1] * 1e-3)


def acc_status_led():
    log.info('--- ACC sense, SW1, status output, LED')
    i_sw1 = (VB_STANDOFF - VF_UA[2]) / R24 + VB_STANDOFF / R8
    log.info('SW1 closing at %.0f V: <= %.1f mA (C5 charge through R24 + R8) vs switching rating %.0f mA', VB_STANDOFF,
             i_sw1 * 1e3, SW1_I_SWITCH * 1e3)
    log.info('D6 peak charge current at the %.0f V ACC clamp: %.0f mA (BAS116 IF %.0f mA, surge %.0f mA)', TVS_VC_1,
             (TVS_VC_1 - 2 * VF_UA[2]) / R24 * 1e3, BAS116_IF_MAX * 1e3, BAS116_IFSM * 1e3)
    log.info('ACC_S pull-down R8 %.0fk: %.2f mA at %.1f V; an off ACC line leaking %.0f uA reads %.2f V', R8 * 1e-3,
             VB_NOM / R8 * 1e3, VB_NOM, I_ACC_GHOST * 1e6, I_ACC_GHOST * R8)
    log.info('J5 with ACC on: %.0f mV + U1B VOL (Pi pull-up %.0fk assumed); released: %.2f V less %.3f V leakage drop',
             V_PI * R21 / (R_PU_PI + R21) * 1e3, R_PU_PI * 1e-3, V_PI, U1_ILKG_MAX * R_PU_PI)
    for v in (VB_STANDOFF, TVS_VC_1):
        log.info('J5 wired to %.0f V by mistake: %.1f mA into U1B (abs max %.0f mA), %.0f mW in R21', v, v / R21 * 1e3,
                 U1_IO_ABS * 1e3, v ** 2 / R21 * 1e3)
    for vb in VB_LIST + (VB_STANDOFF,):
        log.info('LED VB %.1f V: %.2f mA', vb, (vb - LED_VF_TYP) / R3 * 1e3)


def _decay(r, c_scale, v0, v_off, i_leak, i_src, r_ir):
    """Time for C5_T to fall from v0 to v_off: dV/dt = -(V/R + V/R_IR + I_leak - I_src) / C(V)."""
    v, t = v0, 0.0
    while v > v_off:
        c = C5_NOM * c_scale * max(DCB_FLOOR, 1 - DCB_SLOPE * v)
        i = v / r + v / r_ir + i_leak - i_src
        if i <= 0 or t > T_GIVE_UP:
            return math.inf
        v -= i / c * T_STEP
        t += T_STEP
    return t


def _charge(r, c_scale, v_src, v_target):
    """Time for C5_T to rise from 0 to v_target through r from v_src: dV/dt = (v_src - V) / r / C(V)."""
    if v_target >= v_src:
        return math.inf
    v, t = 0.0, 0.0
    while v < v_target:
        c = C5_NOM * c_scale * max(DCB_FLOOR, 1 - DCB_SLOPE * v)
        v += (v_src - v) / r / c * T_STEP
        t += T_STEP
    return t


def _short_stack(vb):
    """Short-delay corner at VB: (v0, trip, C scale) and the decay function of (C scale, v0, insulation)."""
    lo_s, _ = _ref(vb + V_HARNESS_RISE, R4 * (1 - R_TOL), R5 * (1 + R_TOL), R23 * (1 + R_TOL), U1_VOL_MAX,
                   2 * U1_IB_MAX)
    v_off = lo_s + U1_VIO_MAX
    v0 = vb - 2 * (VF_UA[0] + VF_COLD_ADD)
    cs = (1 - C_TOL) * (1 - C_TEMP) * (1 - C_AGING)
    return v0, v_off, cs, lambda c_scale, v_start, r_ir: _decay(R9 * (1 - R_TOL), c_scale, v_start, v_off,
                                                                 D6_IR_MAX, 0.0, r_ir)


def timer():
    log.info('--- delay-off timer: R9 %.2f Mohm, C5 %d x %.0f uF = %.0f uF X7R, DC-bias slope %.3f /V (assumption), '
             'aging %.0f %%, target %.0f s worst case', R9 * 1e-6, C5_N, C5_EACH * 1e6, C5_NOM * 1e6, DCB_SLOPE,
             C_AGING * 100, DELAY_TARGET)
    cl = cl_scale()
    ir_need = 0.0
    for vb in VB_LIST:
        lo_n, _ = _ref(vb)
        t_nom = _decay(R9, 1.0, vb - 2 * VF_UA[1], lo_n, 0.0, 0.0, math.inf)
        # short: C low, R9 low, REF high (resistors, VOL, IN+ bias, offset, BATT rising after the load stops),
        # V0 low (diodes at their max drop, cold), D6 leakage and C5 insulation at their bounds, no IN- bias
        v0_s, v_off_s, cs, short = _short_stack(vb)
        t_short = short(cs, v0_s, C5_IR_MIN)
        # long: the opposite corners, IN- bias into C5
        lo_l, _ = _ref(vb, R4 * (1 + R_TOL), R5 * (1 - R_TOL), R23 * (1 - R_TOL))
        t_long = _decay(R9 * (1 + R_TOL), cl, vb - 2 * VF_UA[2], lo_l - U1_VIO_MAX, 0.0, U1_IB_MAX, math.inf)
        log.info('VB %.1f V: V0 %.2f V, trip %.2f V: nominal %.1f s; short %.1f s (V0 %.2f, trip %.2f, C x%.3f, '
                 'insulation %.0f Mohm); long %.1f s -> short %s %.0f s', vb, vb - 2 * VF_UA[1], lo_n, t_nom,
                 t_short, v0_s, v_off_s, cs, C5_IR_MIN * 1e-6, t_long, '>=' if t_short >= DELAY_TARGET else '<',
                 DELAY_TARGET)
        ir_lo, ir_hi = IR_SEARCH
        for _ in range(IR_ITER):
            ir_mid = math.sqrt(ir_lo * ir_hi)
            if short(cs, v0_s, ir_mid) >= DELAY_TARGET:
                ir_hi = ir_mid
            else:
                ir_lo = ir_mid
        ir_need = max(ir_need, ir_hi)
        log.info('  short stack reaches %.0f s at a C5 network insulation of %.1f Mohm = %.0f ohm.F (each part: '
                 '%.0f Mohm)', DELAY_TARGET, ir_hi * 1e-6, ir_hi * C5_NOM, ir_hi * C5_N * 1e-6)
    log.info('C5 insulation requirement (hot, whole network): >= %.1f Mohm, i.e. >= %.0f ohm.F per part; chosen part '
             '%.0f ohm.F (%.1fx margin); the common X7R minimum %.0f ohm.F would give %.1f Mohm: not enough',
             ir_need * 1e-6, ir_need * C5_NOM, C5_IR_OHM_F, C5_IR_OHM_F / (ir_need * C5_NOM),
             C5_IR_OHM_F_TYPICAL_MIN, C5_IR_OHM_F_TYPICAL_MIN / C5_NOM * 1e-6)
    r_th = _par(R4, R5, R23)
    log.info('REF Thevenin (Q1 on) %.0f kohm: IN+ bias 2 x %.0f nA shifts the trip by %.0f mV', r_th * 1e-3,
             U1_IB_MAX * 1e9, 2 * U1_IB_MAX * r_th * 1e3)
    floor = U1_IB_MAX * R9 * (1 + R_TOL)
    trip_min = _ref(VB_MIN, R4 * (1 + R_TOL), R5 * (1 - R_TOL), R23 * (1 - R_TOL))[0] - U1_VIO_MAX
    log.info('stall check: the only current into C5_T is the IN- bias (<= %.0f nA): floor %.2f V with R9 alone '
             '(lower with any C5 insulation or D6 leakage, which only discharge) vs the lowest trip %.2f V: no stall',
             U1_IB_MAX * 1e9, floor, trip_min)
    recharge()


def recharge():
    log.info('--- key-on recharge of C5 (%.0f uF) through R24 %.0f ohm and D5 / D4 / D6', C5_NOM * 1e6, R24)
    v_in = VB_STANDOFF - VF_UA[2]
    i_pk = v_in / R24 + VB_STANDOFF / R8
    log.info('peak at %.0f V (C5 empty): R24 / D6 %.1f mA, D5 or D4 and SW1 %.1f mA (SW1 switching %.0f mA, '
             'D6 BAS116 IF %.0f mA): independent of C5', VB_STANDOFF, v_in / R24 * 1e3, i_pk * 1e3,
             SW1_I_SWITCH * 1e3, BAS116_IF_MAX * 1e3)
    v_cl = TVS_VC_1 - 2 * VF_UA[2]
    log.info('R24 at key-on: peak %.2f W at %.0f V (%.2f W at the %.0f V ACC clamp) vs %.3f W continuous, decaying '
             'with the charge time constant; energy %.1f mJ (C5 at %.0f V, no DC-bias derating: bound)',
             v_in ** 2 / R24, VB_STANDOFF, v_cl ** 2 / R24, TVS_VC_1, R0805_P,
             0.5 * C5_NOM * (1 + C_TOL) * v_in ** 2 * 1e3, v_in)
    r_hi = R24 * (1 + R_TOL)
    for vb in VB_LIST:
        tau = R24 * C5_NOM * (1 - DCB_SLOPE * vb / 2)
        v0_s, v_off_s, cs, short = _short_stack(vb)
        worst = 0.0
        for c_scale in (cs, 1.0, cl_scale()):
            lo, hi = v_off_s, v0_s
            if short(c_scale, hi, C5_IR_MIN) < DELAY_TARGET:
                worst = math.inf
                break
            for _ in range(V0_ITER):
                mid = 0.5 * (lo + hi)
                if short(c_scale, mid, C5_IR_MIN) >= DELAY_TARGET:
                    hi = mid
                else:
                    lo = mid
            worst = max(worst, _charge(r_hi, c_scale, v0_s, hi))
        t_turn_on = _charge(R24, 1.0, vb - 2 * VF_UA[1], _ref(vb)[1])
        log.info('VB %.1f V: charge time constant %.0f ms nominal; key-on needed from an empty C5 for >= %.0f s '
                 '(short stack, any C corner): %.0f ms; a key-on shorter than about %.0f ms (nominal) does not turn '
                 'Q1 on; between the two, Q1 turns on with a shorter hold', vb, tau * 1e3, DELAY_TARGET, worst * 1e3,
                 t_turn_on * 1e3)


def cl_scale():
    return (1 + C_TOL) * (1 + C_TEMP)


def _loop_gain(f, c_cer, r_load, q, fsw=F_SW):
    s = 2j * math.pi * f
    z_cer = ESR_CER / C_OUT_N + 1 / (s * c_cer)
    z_o = 1 / (1 / r_load + 1 / z_cer)
    wn = math.pi * fsw
    h_s = 1 / (1 + s / (wn * q) + (s / wn) ** 2)
    z_c = 1 / (1 / (R_COMP + 1 / (s * C_COMP)) + s * (C_HF + C_OEA) + 1 / RO_EA)
    return GM_PS * z_o * h_s * (VREF / V_OUT_TARGET) * GM_EA * z_c


def _crossover(c_cer, r_load, q, fsw=F_SW):
    f_lo, f_hi = 100.0, fsw
    for _ in range(80):
        f_mid = math.sqrt(f_lo * f_hi)
        if abs(_loop_gain(f_mid, c_cer, r_load, q, fsw)) > 1:
            f_lo = f_mid
        else:
            f_hi = f_mid
    return f_lo, 180 + math.degrees(cmath.phase(_loop_gain(f_lo, c_cer, r_load, q, fsw)))


def _fb_search():
    """E96 pairs whose worst-case VOUT fits USB with the drop budget, best (largest smaller margin) first."""
    best = []
    for r_bot in sorted({m * 10 ** e for m in E96 for e in (1, 2)}):
        if not R_FB_BOT_RANGE[0] <= r_bot <= R_FB_BOT_RANGE[1]:
            continue
        for r_top in sorted({m * 10 ** e for m in E96 for e in (1, 2, 3)}):
            hi = _vout(r_top, r_bot, VREF_TOL, R_TOL)
            lo = _vout(r_top, r_bot, -VREF_TOL, -R_TOL) - V_DROP_BUDGET
            if hi <= USB_VBUS[1] and lo >= USB_VBUS[0]:
                best.append((min(USB_VBUS[1] - hi, lo - USB_VBUS[0]), r_top, r_bot, _vout(r_top, r_bot), lo, hi))
    return sorted(best, reverse=True)[:5]


def _ripple(vin, l, fsw):
    return V_OUT_TARGET * (vin - V_OUT_TARGET) / (vin * l * fsw)


def buck():
    log.info('--- buck TPS54336A: L1 15 uH, Cin %d x 10 uF, Cout %d x 47 uF, Type 2B, EN floating', C_IN_N, C_OUT_N)
    v_out, hi = V_OUT_TARGET, _vout(R_FB_TOP, R_FB_BOT, VREF_TOL, R_TOL)
    lo = _vout(R_FB_TOP, R_FB_BOT, -VREF_TOL, -R_TOL)
    log.info('FB (eq 15/16) %.1fk / %.1fk: VOUT %.3f V, worst %.3f - %.3f V (ref +-%.1f %%, R +-%.0f %%); at the port '
             'with a %.2f V drop budget: low %.3f V (USB %.2f - %.2f V)', R_FB_TOP * 1e-3, R_FB_BOT * 1e-3, v_out, lo,
             hi, VREF_TOL * 100, R_TOL * 100, V_DROP_BUDGET, lo - V_DROP_BUDGET, *USB_VBUS)
    for m, r_top, r_bot, nom, lo_p, hi_p in _fb_search():
        log.info('  E96 option %.1fk / %.1fk: nominal %.3f V, port low %.3f V, high %.3f V, smaller margin %.0f mV',
                 r_top * 1e-3, r_bot * 1e-3, nom, lo_p, hi_p, m * 1e3)
    l_min = v_out * (V_IN_MAX - v_out) / (V_IN_MAX * K_IND_MAX * I_OUT * F_SW)
    log.info('L (eq 19): L_min %.1f uH at VIN %.0f V, K_IND %.1f; L1 %.0f uH', l_min * 1e6, V_IN_MAX, K_IND_MAX, L1 * 1e6)
    for vin in V_IN_BUCK:
        di = _ripple(vin, L1, F_SW)
        di_w = _ripple(vin, L1 * (1 - L_TOL), FSW_RANGE[0])
        i_rms = math.sqrt(I_OUT ** 2 + di ** 2 / 12)
        log.info('  VIN %.1f: ripple %.2f A, K_IND %.3f (L -%.0f %% and fsw min: %.2f A, %.3f); I_rms %.3f A (eq 20), '
                 'I_pk %.2f A (eq 21)', vin, di, di / I_OUT, L_TOL * 100, di_w, di_w / I_OUT, i_rms,
                 I_OUT + v_out * (vin - v_out) / (1.6 * vin * L1 * F_SW))
    log.info('  L1 I_sat %.1f A vs HS current limit max %.1f A; I_rms rating %.2f A; DCR loss %.2f W typ, %.2f W max',
             L_ISAT, I_HS_LIMIT_MAX, L_IRMS, I_OUT ** 2 * L_DCR_TYP, I_OUT ** 2 * L_DCR_MAX)
    c_tr = 2 * DI_STEP / (F_SW * DV_STEP_FRAC * v_out)
    di_max = _ripple(V_IN_MAX, L1, F_SW)
    c_rip = 1 / (8 * F_SW) / (V_RIPPLE_OUT / di_max)
    worst_margin = 999.0
    for ret in DC_BIAS_RETENTION:
        c_eff = C_OUT_N * C_OUT_NOM * ret
        worst_margin = min(worst_margin, c_eff / c_tr - 1, c_eff / c_rip - 1)
        log.info('  Cout %d x %.0f uF at retention %.2f: %.1f uF; eq 22 needs %.1f uF (margin %.0f %%), eq 23 needs '
                 '%.1f uF (margin %.0f %%)', C_OUT_N, C_OUT_NOM * 1e6, ret, c_eff * 1e6, c_tr * 1e6,
                 (c_eff / c_tr - 1) * 100, c_rip * 1e6, (c_eff / c_rip - 1) * 100)
    c_tr_min_fsw = 2 * DI_STEP / (FSW_RANGE[0] * DV_STEP_FRAC * v_out)
    c_low = C_OUT_N * C_OUT_NOM * DC_BIAS_RETENTION[0]
    log.info('  eq 22 at fsw min %.0f kHz: needs %.1f uF, margin %.0f %% at retention %.2f (below the required %.0f %%: '
             'eq 22 stands in for the loop response time, see the loop-based step below)', FSW_RANGE[0] * 1e-3,
             c_tr_min_fsw * 1e6, (c_low / c_tr_min_fsw - 1) * 100, DC_BIAS_RETENTION[0], MARGIN_MIN * 100)
    log.info('  eq 24: ESR < %.0f mOhm (ceramic %.0f mOhm / %d); eq 25 ripple current %.0f mA per capacitor; '
             'lowest margin %.0f %% (required %.0f %%)', V_RIPPLE_OUT / di_max * 1e3, ESR_CER * 1e3, C_OUT_N,
             di_max / math.sqrt(12) / C_OUT_N * 1e3, worst_margin * 100, MARGIN_MIN * 100)
    c_design = C_OUT_N * C_OUT_NOM * DC_BIAS_RETENTION[1]
    r_l = v_out / I_OUT
    log.info('comp (eq 10/12) at fc %.0f kHz, Cout %.1f uF: R %.2fk, C %.1f nF; used %.2fk / %.0f nF', FC_TARGET * 1e-3,
             c_design * 1e6, 2 * math.pi * FC_TARGET * v_out * c_design / (GM_EA * VREF * GM_PS) * 1e-3,
             r_l * c_design / R_COMP * 1e9, R_COMP * 1e-3, C_COMP * 1e9)
    worst_pm, fc_rng, worst_case, dv_step = 999.0, (1e9, 0.0), None, 0.0
    for ret in DC_BIAS_RETENTION:
        for r_load in (r_l, v_out / I_OUT_LIGHT):
            for q in SAMPLING_Q:
                for fsw in (FSW_RANGE[0], F_SW, FSW_RANGE[1]):
                    fc, pm = _crossover(C_OUT_N * C_OUT_NOM * ret, r_load, q, fsw)
                    if pm < worst_pm:
                        worst_pm, worst_case = pm, (ret, v_out / r_load, q, fsw, fc)
                    fc_rng = (min(fc_rng[0], fc), max(fc_rng[1], fc))
                    if r_load == r_l:
                        dv_step = max(dv_step, DI_STEP / (2 * math.pi * fc * C_OUT_N * C_OUT_NOM * ret))
                    if q == SAMPLING_Q[1] and r_load == r_l and fsw == F_SW:
                        log.info('  retention %.2f, 3 A: fc %.1f kHz, PM %.0f deg', ret, fc * 1e-3, pm)
    log.info('loop, all cases (retention, 0.1-3 A, sampling Q, fsw min-typ-max): fc %.1f-%.1f kHz, PM >= %.1f deg '
             '(required %.0f; worst at retention %.2f, %.1f A, Q %.2f, fsw %.0f kHz, fc %.1f kHz)', fc_rng[0] * 1e-3,
             fc_rng[1] * 1e-3, worst_pm, PM_MIN, worst_case[0], worst_case[1], worst_case[2], worst_case[3] * 1e-3,
             worst_case[4] * 1e-3)
    log.info('load step %.1f A, loop-based (dV = dI / (2 pi fc Co), 3 A cases): <= %.0f mV vs %.0f mV (%.0f %%)',
             DI_STEP, dv_step * 1e3, DV_STEP_FRAC * v_out * 1e3, DV_STEP_FRAC * 100)
    c_eff = C_OUT_N * C_OUT_NOM * DC_BIAS_RETENTION[0]
    log.info('phone plug-in (USB device %.0f uF) on %.1f uF effective: VBUS step %.2f V for a few us (loop restores)',
             USB_DEVICE_C * 1e6, c_eff * 1e6, v_out * USB_DEVICE_C / (USB_DEVICE_C + c_eff))
    log.info('SS (eq 5) %.0f nF: t_ss %.2f ms', C_SS * 1e9, C_SS * VREF / ESS_I * 1e3)
    c_in = C_IN_N * C_IN_NOM * C_IN_RETENTION
    for fsw in (F_SW, FSW_RANGE[0]):
        dv = I_OUT * 0.25 / (c_in * fsw) + I_OUT * C_IN_ESR
        log.info('Cin (eq 17) %d x %.0f uF at %.0f %% retention = %.0f uF, fsw %.0f kHz: %.0f mV p-p (limit %.0f mV, '
                 'margin %.0f %%); I_rms (eq 18) %.2f A total', C_IN_N, C_IN_NOM * 1e6, C_IN_RETENTION * 100, c_in * 1e6,
                 fsw * 1e-3, dv * 1e3, V_IN_RIPPLE_MAX * 1e3, (V_IN_RIPPLE_MAX / dv - 1) * 100, I_OUT / 2)
    for vin in VB_LIST:
        d = v_out / vin
        for tag, hs, ls in (('typ', RDS_HS[0], RDS_LS[0]), ('max', RDS_HS[1], RDS_LS[1])):
            p = I_OUT ** 2 * (hs * d + ls * (1 - d)) + 0.5e-9 * vin ** 2 * I_OUT * F_SW + 22.8e-9 * F_SW + 0.11e-3 * vin
            log.info('TPS54336A VIN %.1f %s RDS: %.2f W, TJ %.0f C at TA %.0f C (RthJA %.1f, JEDEC)', vin, tag, p,
                     T_AMB_HOT + p * RTH_JA_DDA, T_AMB_HOT, RTH_JA_DDA)
    log.info('--- TPS54302 thermal (SLVSDG6C 5.4, fig. 7-2): rejected option')
    for i_out, eff in TPS54302_EFF.items():
        p_out = TPS54302_VOUT * i_out
        p_tot = p_out / eff - p_out
        p_ic = (p_tot - i_out ** 2 * L_DCR_TYP_2026_11_05) * (1 + RDS_HOT_ADD)
        log.info('TPS54302 %.1f A: loss %.2f W (eff %.1f %%), IC %.2f W at TA %.0f C -> TJ %.0f C (EVM %.1f C/W) / '
                 '%.0f C (JEDEC %.1f C/W); recommended max %.0f C', i_out, p_tot, eff * 100, p_ic, T_AMB_HOT,
                 T_AMB_HOT + p_ic * TPS54302_RTHJA_EVM, TPS54302_RTHJA_EVM, T_AMB_HOT + p_ic * TPS54302_RTHJA_JEDEC,
                 TPS54302_RTHJA_JEDEC, TPS54302_TJ_REC_MAX)


# ================================================================ counter timer (2026-11-05, project lead: clock +
# counter replaces the RC / comparator timer; SPEC 2-4, reports/timer_survey.md; U5 on VDD_TMR from VOUT: u5_supply())
# U5 CD4541B (TI SCHS085E): RC oscillator + 16-stage counter, tap 2^16 (A = B = 1), Q-bar select (output high after
# reset), single-transition mode, auto reset on. MASTER RESET from ACC.
U5_STAGES = 16                                   # frequency selection table, A = B = 1
U5_COUNTS = 2 ** (U5_STAGES - 1)                 # "changes ... after 2^(N-1) counts" (p. 1)
K_RC_DATASHEET = 2.3                             # f = 1 / (2.3 RTC CTC), stated for 1 kHz to 100 kHz (p. 1)
F_FORMULA_MIN = 1e3                              # lower end of the datasheet formula range
HOLD_TARGET = 25.0                               # worst case after the last key-off (project lead, 2026-11-05 rev.)
HOLD_NOMINAL = 30.0                              # nominal aimed at (project lead)
# period / (RTC CTC) bound: the fig. 2 oscillator solved segment by segment (_osc_k) over these datasheet limits
U5_VT_FRAC = (0.3, 0.4, 0.5, 0.6, 0.7)           # input switching point between VIL and VIH (0.3 / 0.7 VDD at 5 and
#                                                  10 V); assumption: the same fractions over the VDD_TMR range
# OSC_VDD (the VDD range the bound is solved over) = the VDD_TMR range: set after the U5 supply block below
OSC_IIN = (-1e-6, 0.0, 1e-6)                     # RS-pin input current limit, 85 / 125 C columns (an 18 V figure)
OSC_FAST = dict(r_out=1.0, vf=0.3, t_gate=0.0)   # no driver resistance, hot protection diode (most clamp current),
#                                                  no gate delay (assumption: diode drop)
OSC_SLOW = dict(r_out=370.0, vf=0.7, t_gate=1e-6)  # driver resistance from the 125 C sink rating, cold diode, a gate-
#                                                  chain delay bound per transition (assumption: no datasheet figure)
K_MODEL_ALLOW = 0.02                             # added on both sides: the LTspice gate model reads up to 2 % lower
#                                                  than this solution; silicon beyond fig. 2 (assumption)
OSC_STEPS_PER_RC = 2000
OSC_PERIODS, OSC_SETTLE = 6, 2
U5_VDD_MIN_OP = 3.0                              # operating conditions, full temperature range
U5_VDD_ABS = 20.0
U5_VDD_MAX_OP = 18.0                             # operating conditions (3 V min, 18 V)
U5_VIL_5V, U5_VIH_5V, U5_V_SPEC = 1.5, 3.5, 5.0  # input thresholds at VDD 5 V (scale with VDD)
U5_IIN_MAX_HOT = 1e-6                            # input current limit, 85 / 125 C columns
U5_IIN_ABS = 10e-3                               # DC input current, any one input (abs max)
U5_IOL_HOT, U5_VOL_TEST = 1.08e-3, 0.4           # output sink at VDD 5 V, 125 C, and its test voltage
U5_VOH_MIN = 4.95                                # VDD 5 V, light load
V_CLAMP_CMOS = 0.6                               # CMOS input protection diode drop (assumption)
V5_RANGE = (4.5, 5.09, 5.5)                      # +5V1 range (SPEC 4), nominal from SPEC 4
U5_IDD_TYP_5V = 0.04e-6                          # quiescent, 25 C typical column
U5_IDD_AR_TYP = ((5.0, 7e-6), (10.0, 30e-6))     # auto-reset drain, 25 C typical (note 2)
U5_IDD_MAX_85C = ((5.0, 150e-6), (10.0, 300e-6))  # quiescent, 85 / 125 C columns
U5_IDD_AR_MAX = ((5.0, 200e-6), (10.0, 350e-6))  # auto-reset drain, max (note 2, 25 C)
U5_AR_RELIABLE_VDD = 5.0                         # 'for reliable automatic power-on reset, VDD should be > 5 V' (p. 1)
RTC, CTC, RS_OSC = 39.2e3, 10e-9, 78.7e3         # R27, C29 (C0G), R28 (RS ~ 2 RTC, >= 10k)
C0G_TOL, C0G_TC = 0.01, 30e-6                    # KEMET C0805C103F5GACTU: +-1 %; C0G (EIA) 0 +-30 ppm/K
C0G_TOL_ALT = (0.02, 0.05)                       # the same stack with +-2 % / +-5 % C0G (report only)
R_TCR = 100e-6                                   # 1 % thick film (assumption: BOM checks the part)
T_COLD, T_HOT = -40.0, 125.0

# U5 supply VDD_TMR (project lead 2026-11-05: from VOUT, replaces +5V1 through a BAT43W with a 10 uF hold-up):
# VOUT -> R30 -> VDD_TMR; D7 zener VDD_TMR -> GND (clamp); R31 VDD_TMR -> GND (bleed); C8 decoupling at U5.
R30_SUP = 1.3e3                                  # VOUT -> VDD_TMR, 1206
R31_BLEED = 10e3                                 # VDD_TMR -> GND, 0805
C8_NOM = 1e-6                                    # 50 V X7R 0805 decoupling
R1206_P = 0.25                                   # 1206 thick-film continuous rating (BOM checks the part)
R_DERATE_85C = 0.82                              # thick-film load at 85 C (assumption: linear 70 -> 155 C to zero)
VZ_5MA, VZ_TYP = (4.85, 5.36), 5.1               # Vishay 86342 BZT52C5V1: VZ min / max, typ at IZT1 (25 C)
IZT1, IZT2 = 5e-3, 1e-3                          # its two test currents
ZZ_IZT1_MAX, ZZK_IZT2_MAX = 60.0, 480.0          # dynamic resistance limits at IZT1 / IZT2
VZ_TC = (-3e-4, 4e-4)                            # temperature coefficient range, per K
ZD_IR_MAX, ZD_VR_IR = 100e-9, 0.8                # reverse current limit at VR (below the knee)
ZD_PTOT_FR4, ZD_RTHJA = 0.300, 420.0             # on FR-4, recommended footprint
R_HARNESS = 50e-3                                # harness + terminal (assumption, as the sim)
VOUT_MIN_COUNT = VB_MIN - I_TURN_OFF * (R_HARNESS + Q1_RDS_45_MAX * Q1_RDS_HOT_FACTOR)
Q1_IDSS_125 = 50e-6                              # Q1 IDSS limit at TJ 125 C, VDS 40 V


def _lin(v, pts):
    (x1, y1), (x2, y2) = pts
    return y1 + (y2 - y1) * (v - x1) / (x2 - x1)


def u5_current(vdd, worst):
    """U5 supply current: quiescent + auto reset (typical or max rows, interpolated in VDD) + oscillator estimate."""
    if worst:
        idd = _lin(vdd, U5_IDD_MAX_85C) + _lin(vdd, U5_IDD_AR_MAX)
    else:
        idd = U5_IDD_TYP_5V + _lin(vdd, U5_IDD_AR_TYP)
    return idd + vdd / RTC


def vz(i, hi):
    """D7 zener voltage at current i: upper (hi) or lower bound, datasheet limits, -40 to 125 C.

    Above IZT1 the voltage rises by at most ZZ x the extra current. Below IZT1 the upper bound stays at VZ max; the
    lower bound falls along r(i) = ZZK (IZT2 / i)^b through both resistance limits (assumption: no I-V curve in the
    datasheet)."""
    if hi:
        v = VZ_5MA[1] + ZZ_IZT1_MAX * max(i - IZT1, 0.0)
        return v * (1 + max(VZ_TC[1] * (T_HOT - T_DATASHEET), VZ_TC[0] * (T_COLD - T_DATASHEET)))
    b = math.log(ZZK_IZT2_MAX / ZZ_IZT1_MAX) / math.log(IZT1 / IZT2)
    v = VZ_5MA[0]
    if i < IZT1:
        v -= ZZK_IZT2_MAX * IZT2 ** b * (IZT1 ** (1 - b) - i ** (1 - b)) / (1 - b)
    return v * (1 + min(VZ_TC[0] * (T_HOT - T_DATASHEET), VZ_TC[1] * (T_COLD - T_DATASHEET)))


def vdd_tmr(vout, hi, worst, i_inj=0.0):
    """(VDD_TMR, zener current) at a VOUT: R30 feeds R31, U5 and the zener; i_inj = clamp current into VDD_TMR."""
    def res(iz):
        v = vz(iz, hi)
        return (vout - v) / R30_SUP + i_inj - v / R31_BLEED - u5_current(v, worst) - iz, v
    lo, top = 1e-7, 0.2
    if res(lo)[0] < 0:                           # zener off: divider + U5 only
        v = vout
        for _ in range(60):
            v = (vout / R30_SUP + i_inj - u5_current(v, worst)) / (1 / R30_SUP + 1 / R31_BLEED)
        return v, 0.0
    for _ in range(80):
        mid = math.sqrt(lo * top)
        if res(mid)[0] > 0:
            lo = mid
        else:
            top = mid
    return res(lo)[1], lo


VDD_TMR = (vdd_tmr(VOUT_MIN_COUNT, False, True)[0], VZ_TYP, vdd_tmr(VB_STANDOFF, True, False)[0])
OSC_VDD = (VDD_TMR[0], VDD_TMR[2])

# ACC interface: ACC_S -> R8 -> ACC_G -> R25 -> GND; ACC_G -> Q6 gate (J5), -> R26 -> U5 MR, -> D6 -> HOLD_G
R8_TOP, R25_BOT = 22e3, 27e3
R26_MR = 100e3
R29_HOLD = 47e3                                  # U5 OUT -> HOLD_G (Q5 gate)
VF_SIG_COLD_MAX = VF_UA[0] + VF_COLD_ADD         # D4 / D5 / D6 at microamps to a fraction of a mA, cold (assumption)

# 2N7002BK (Nexperia, 17 Oct 2024): Q5 hold, Q6 J5
NFET_VTH_COLD_MAX = 2.35                         # from the VGS(th)-vs-temperature graph (as the 2026-11-04 design)
NFET_VTH_HOT_MIN = 0.75                          # 125 C, same graph
NFET_VGS_ABS = 20.0
NFET_IDSS_25, NFET_IDSS_150 = 1e-6, 10e-6        # VDS 60 V
NFET_IGSS_20V = 10e-6                            # VGS 20 V bound (ESD-protected gate)
NFET_RDS_5V_MAX = 2.0                            # VGS 5 V, 25 C
T_PARKED = T_AMB_HOT                             # parked: nothing on the board dissipates


def _osc_k(vt_frac, vdd, i_in, r_out, vf, t_gate, rtc=None, ctc=None, rs=None):
    """CD4541B RC oscillator (SCHS085E fig. 2): period / (RTC CTC), solved segment by segment.

    Node j joins RTC (driven by the inverted pin-3 level through r_out), CTC (driven in phase through r_out) and RS
    (to pin 3: protection diodes vf above VDD / below VSS, input current i_in out of the pin). Pin 3 switches the
    drivers at vt_frac x VDD, t_gate later. Each step is the exact exponential of the linear segment it is in.
    """
    rtc, ctc, rs = rtc or RTC, ctc or CTC, rs or RS_OSC
    vt, ra, rz = vt_frac * vdd, rtc + r_out, r_out
    dt = rtc * ctc / OSC_STEPS_PER_RC
    hi = False                                   # pin-3 state seen by the drivers
    vc, t, t_flip, prev_p, edges = 0.0, 0.0, None, None, []
    t_end = (OSC_PERIODS + OSC_SETTLE + 1) * 2.6 * rtc * ctc
    while t < t_end and len(edges) < OSC_PERIODS + OSC_SETTLE + 1:
        y, z = (0.0, vdd) if hi else (vdd, 0.0)
        g, num = 1 / rz + 1 / ra, (z - vc) / rz + y / ra - i_in
        j = num / g
        p = j - i_in * rs
        if p > vdd + vf or p < -vf:              # clamped: RS to the clamp level instead of the input current
            v_cl = vdd + vf if p > 0 else -vf
            g, num = 1 / rz + 1 / ra + 1 / rs, (z - vc) / rz + y / ra + v_cl / rs
            j = num / g
            p = v_cl
        beta = (1 / rz) / g                      # j = alpha - beta vc
        alpha = j + beta * vc
        vc_inf, tau = (z - alpha) / (1 - beta), rz * ctc / (1 - beta)
        if prev_p is not None and t_flip is None and ((not hi and prev_p < vt <= p) or (hi and prev_p > vt >= p)):
            t_flip = t - dt * (p - vt) / (p - prev_p) + t_gate
        if t_flip is not None and t >= t_flip:
            hi = not hi
            t_flip = None
            if hi:
                edges.append(t)
            prev_p = None
            continue
        prev_p = p
        vc = vc_inf + (vc - vc_inf) * math.exp(-dt / tau)
        t += dt
    per = (edges[-1] - edges[OSC_SETTLE]) / (len(edges) - 1 - OSC_SETTLE)
    return per / (rtc * ctc)


def _osc_bounds():
    k_fast = [_osc_k(v, vdd, i, **OSC_FAST) for v in U5_VT_FRAC for vdd in OSC_VDD for i in OSC_IIN]
    k_slow = [_osc_k(v, vdd, i, **OSC_SLOW) for v in U5_VT_FRAC for vdd in OSC_VDD for i in OSC_IIN]
    return min(k_fast), max(k_slow), k_fast, k_slow


def _k_threshold(vt_frac):
    """Ideal CMOS RC oscillator with an isolating RS: period / (R C) for an input threshold at vt_frac x VDD."""
    return math.log((1 + vt_frac) / vt_frac) + math.log((2 - vt_frac) / (1 - vt_frac))


def _interp_log(t, t1, y1, t2, y2):
    return y1 * (y2 / y1) ** ((t - t1) / (t2 - t1))


def _bisect(fun, lo, hi, n=60):
    for _ in range(n):
        mid = 0.5 * (lo + hi)
        if fun(mid) > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def counter_timer():
    log.info('--- counter timer U5 CD4541B on VDD_TMR (from VOUT): tap 2^%d, output low after %d counts', U5_STAGES, U5_COUNTS)
    # oscillator: constant bound from the datasheet structure and limits, then R / C tolerance and drift
    r_out = U5_VOL_TEST / U5_IOL_HOT
    k_ideal = (_k_threshold(0.5), _k_threshold(U5_VT_FRAC[0]))
    k_min, k_max, k_fast, k_slow = _osc_bounds()
    k_lo, k_hi = k_min * (1 - K_MODEL_ALLOW), k_max * (1 + K_MODEL_ALLOW)
    log.info('period/(RC): ideal %.3f (threshold 0.5 VDD) .. %.3f (0.3 / 0.7 VDD); fig. 2 solved: fast %.3f .. %.3f '
             '(no driver R, hot clamp diode, input current +-%.0f uA), slow %.3f .. %.3f (driver %.0f ohm each, cold '
             'diode, %.1f us gate delay); datasheet %.1f inside', *k_ideal, min(k_fast), max(k_fast),
             OSC_IIN[-1] * 1e6, min(k_slow), max(k_slow), r_out, OSC_SLOW['t_gate'] * 1e6, K_RC_DATASHEET)
    log.info('bound used %.3f .. %.3f (+-%.0f %% model allowance); the previous design used 2.0 .. 2.6',
             k_lo, k_hi, K_MODEL_ALLOW * 100)
    log.info('RS %.1fk >= 10k and %.2f x RTC (datasheet: RS ~ 2 RTC)', RS_OSC * 1e-3, RS_OSC / RTC)
    dt = max(T_HOT - T_DATASHEET, T_DATASHEET - T_COLD)
    r_lo, r_hi = (1 - R_TOL) * (1 - R_TCR * dt), (1 + R_TOL) * (1 + R_TCR * dt)

    def corners(c_tol):
        c_lo, c_hi = (1 - c_tol) * (1 - C0G_TC * dt), (1 + c_tol) * (1 + C0G_TC * dt)
        f_hi = 1 / (k_lo * RTC * r_lo * CTC * c_lo)
        f_lo = 1 / (k_hi * RTC * r_hi * CTC * c_hi)
        return f_hi, f_lo, c_lo, c_hi
    f_nom = 1 / (K_RC_DATASHEET * RTC * CTC)
    f_hi, f_lo, c_lo, c_hi = corners(C0G_TOL)
    t_nom, t_short, t_long = U5_COUNTS / f_nom, U5_COUNTS / f_hi, U5_COUNTS / f_lo
    log.info('RTC %.1fk, CTC %.0f nF C0G +-%.0f %%, RS %.1fk (R 1 %% %.0f ppm/K, C %.0f ppm/K, %.0f K):',
             RTC * 1e-3, CTC * 1e9, C0G_TOL * 100, RS_OSC * 1e-3, R_TCR * 1e6, C0G_TC * 1e6, dt)
    log.info('  short corner: %.0f Hz -> %.1f s (%s %.0f s; %.0f %% above the %.0f kHz formula floor)', f_hi,
             t_short, '>=' if t_short >= HOLD_TARGET else '< !', HOLD_TARGET, (f_hi / F_FORMULA_MIN - 1) * 100,
             F_FORMULA_MIN * 1e-3)
    log.info('  nominal (k %.1f): %.0f Hz -> %.1f s (aim %.0f s)', K_RC_DATASHEET, f_nom, t_nom, HOLD_NOMINAL)
    log.info('  long corner: %.0f Hz -> %.1f s (%s the formula floor; C x%.4f, R x%.4f)', f_lo, t_long,
             'at or above' if f_lo >= F_FORMULA_MIN else 'below', c_hi, r_hi)
    log.info('  the most a >= %.0f s guarantee allows at the short corner: %.0f Hz (tap 2^%d: the longest; a shorter '
             'tap needs a lower frequency for the same delay)', HOLD_TARGET, U5_COUNTS / HOLD_TARGET, U5_STAGES)
    for tol in C0G_TOL_ALT:
        fh, fl, _, _ = corners(tol)
        log.info('  same values with C0G +-%.0f %%: short %.1f s (%.0f Hz), long %.1f s (%.0f Hz)', tol * 100,
                 U5_COUNTS / fh, fh, U5_COUNTS / fl, fl)
    log.info('supply VDD_TMR %.2f-%.2f V (zener clamp, u5_supply()): the bound above is solved over this range '
             '(SCHS085E gives no frequency-vs-VDD curve; thresholds scale with VDD); the first period after MR '
             'release is shorter (from a rail), %.2f ms of %.0f s', OSC_VDD[0], OSC_VDD[1], 1e3 / f_nom, t_nom)
    i_osc = OSC_VDD[1] * 1.5 / RTC
    log.info('oscillator peak current %.0f uA; RS-pin clamp current <= %.0f uA (abs max %.0f mA)', i_osc * 1e6,
             (OSC_VDD[1] * 0.5 - 0.3) / RS_OSC * 1e6, U5_IIN_ABS * 1e3)

    # ACC interface
    k_div = R25_BOT / (R8_TOP + R25_BOT)
    r_th = _par(R8_TOP, R25_BOT)
    log.info('ACC_G divider R8 %.0fk / R25 %.0fk: ratio %.3f, Thevenin %.1f kohm; ACC_S load %.2f mA at %.1f V',
             R8_TOP * 1e-3, R25_BOT * 1e-3, k_div, r_th * 1e-3, VB_STANDOFF / (R8_TOP + R25_BOT) * 1e3,
             VB_STANDOFF)
    acc_s_min = VB_MIN - VF_SIG_COLD_MAX
    g_min = acc_s_min * k_div
    for vdd in VDD_TMR:
        vih = U5_VIH_5V / U5_V_SPEC * vdd
        log.info('MR at VB %.1f V (ACC_S %.2f V, cold diode), VDD_TMR %.2f V: %.2f V (less %.2f V RS-input current '
                 'drop) vs VIH %.2f V', VB_MIN, acc_s_min, vdd, g_min, U5_IIN_MAX_HOT * R26_MR, vih)
    g_ghost = I_ACC_GHOST * R25_BOT
    log.info('ACC line off but leaking %.0f uA: ACC_S %.2f V, ACC_G %.2f V vs VIL %.2f V and Q5/Q6 VGS(th) hot min '
             '%.2f V', I_ACC_GHOST * 1e6, I_ACC_GHOST * (R8_TOP + R25_BOT), g_ghost,
             U5_VIL_5V / U5_V_SPEC * VDD_TMR[0], NFET_VTH_HOT_MIN)
    for v in (VB_STANDOFF, TVS_VC_1, TVS_VC_2):
        g = (v - VF_UA[2]) * k_div
        i_mr = max(0.0, g - VDD_TMR[1] - V_CLAMP_CMOS) / R26_MR
        i_back = max(0.0, g - VF_UA[2] - VDD_TMR[1]) / R29_HOLD
        log.info('ACC %.1f V: ACC_G %.1f V, HOLD_G %.1f V (FET VGS abs max %.0f V); MR clamp current %.0f uA (abs '
                 'max %.0f mA); R29 current into U5 OUT (high) %.0f uA', v, g, g - VF_UA[2], NFET_VGS_ABS,
                 i_mr * 1e6, U5_IIN_ABS * 1e3, i_back * 1e6)

    # key-on with VDD_TMR still at 0 V (Q1 not on yet): ACC_G loaded through R26 (MR clamp) and D6 + R29 (U5 OUT
    # clamp); v5 below = VDD_TMR
    def node(x, v5=0.0):
        i_src = (acc_s_min * k_div - x) / r_th
        i_mr = max(0.0, x - v5 - V_CLAMP_CMOS) / R26_MR
        i_hold = max(0.0, x - VF_SIG_COLD_MAX - v5 - V_CLAMP_CMOS) / R29_HOLD
        return i_src - i_mr - i_hold
    g0 = _bisect(node, 0.0, acc_s_min)
    log.info('key-on at VB %.1f V before VDD_TMR is up (held at 0 V): ACC_G %.2f V (Q6 gate), HOLD_G %.2f V (Q5 '
             'gate) vs VGS(th) cold max %.2f V: Q1 turns on without U5', VB_MIN, g0, g0 - VF_SIG_COLD_MAX,
             NFET_VTH_COLD_MAX)
    def inj(v5):
        g = _bisect(lambda x: node(x, v5), 0.0, VB_STANDOFF)
        i = max(0.0, g - v5 - V_CLAMP_CMOS) / R26_MR + max(0.0, g - VF_SIG_COLD_MAX - v5 - V_CLAMP_CMOS) / R29_HOLD
        return g, i
    r_load = _par(R31_BLEED, R30_SUP + R3)          # VOUT at 0 V: R31, and R30 into VOUT's LED / load path
    v5 = _bisect(lambda v: inj(v)[1] * r_load - v, 0.0, V5_RANGE[2])
    g, i_inj = inj(v5)
    log.info('  with only R31 (and R30 into VOUT) on VDD_TMR, the injection lifts VDD_TMR to %.2f V (%.0f uA) until '
             'Q1 is on: ACC_G %.2f V, HOLD_G %.2f V; U5 sees MR high from its first volt', v5, i_inj * 1e6, g,
             g - VF_SIG_COLD_MAX)
    v_hold = U5_VOH_MIN / U5_V_SPEC * VDD_TMR[0] - NFET_IGSS_20V * R29_HOLD
    log.info('counting (ACC off): HOLD_G >= %.2f V at VDD_TMR %.2f V with the IGSS bound %.0f uA (a 20 V figure, far '
             'above the real leakage at 5 V) vs %.2f V; D6 hot leakage %.0f nA: %.1f mV', v_hold, VDD_TMR[0],
             NFET_IGSS_20V * 1e6, NFET_VTH_COLD_MAX, D6_IR_MAX * 1e9, D6_IR_MAX * R29_HOLD * 1e3)
    log.info('Q5/Q6 turn-off: HOLD_G through R29 x Ciss max: %.1f us', R29_HOLD * 50e-12 * 1e6)

    # Q1 gate through Q5
    k_g = R14 / (R14 + R15)
    i_drv = VB_STANDOFF / (R14 + R15)
    log.info('Q1 on at %.1f V: VGS %.2f V (Q5 sinks %.0f uA, drop %.2f mV) vs %.1f V', VB_MIN,
             VB_MIN * R14 * (1 - R_TOL) / (R14 * (1 - R_TOL) + R15 * (1 + R_TOL)), VB_MIN / (R14 + R15) * 1e6,
             VB_MIN / (R14 + R15) * NFET_RDS_5V_MAX * 1e3, VGS_RDS_SPEC)
    idss = _interp_log(T_PARKED, T_DATASHEET, NFET_IDSS_25, 150.0, NFET_IDSS_150)
    vth_q1 = Q1_VTH_MIN + Q1_VTH_TC * (T_PARKED - T_DATASHEET)
    for n_fet in (1, 2):
        log.info('Q1 off, parked at %.0f C: %d FET(s) on DRV at the IDSS bound %.1f uA each -> VGS %.2f V (+ Q1 IGSS '
                 '%.2f V) vs Q1 VGS(th) min %.2f V%s', T_PARKED, n_fet, idss * 1e6, n_fet * idss * R14,
                 Q1_IGSS * R14, vth_q1, ': chosen (one FET, ACC ORed at its gate)' if n_fet == 1 else
                 ': rejected (two FETs in parallel)')
    log.info('DRV max %.1f V at the %.1f V clamp vs VDS %.0f V; Q5 current <= %.0f uA', TVS_VC_2, TVS_VC_2, 60.0,
             TVS_VC_2 / (R14 + R15) * 1e6)
    log.info('Q1 ramps: q1_switching() (R14 || R15 drives the gate; Q5 RDS(on) negligible)')
    for v in (VB_STANDOFF, TVS_VC_1, TVS_VC_2):
        log.info('Q1 VGS at %.1f V: %.1f V (abs max %.0f V)', v, v * R14 * (1 + R_TOL) / (R14 * (1 + R_TOL) +
                 R15 * (1 - R_TOL)), Q1_VGS_MAX)

    # J5, SW1, supply
    log.info('J5 with ACC on: %.0f mV (R21 + Q6 RDS(on), Pi pull-up %.0fk assumed); wired to %.0f V by mistake: '
             '%.1f mA into Q6 (350 mA)', V_PI * (R21 + NFET_RDS_5V_MAX) / (R_PU_PI + R21) * 1e3, R_PU_PI * 1e-3,
             VB_STANDOFF, VB_STANDOFF / R21 * 1e3)
    log.info('SW1 closing at %.0f V: %.2f mA (ACC_G divider only) vs %.0f mA switching', VB_STANDOFF,
             VB_STANDOFF / (R8_TOP + R25_BOT) * 1e3, SW1_I_SWITCH * 1e3)
    log.info('U5 supply current at VDD_TMR max %.2f V: %.0f uA worst (85 C IDD + auto reset max + oscillator), '
             '%.0f uA typical: u5_supply()', VDD_TMR[2], u5_current(VDD_TMR[2], True) * 1e6,
             u5_current(VDD_TMR[2], False) * 1e6)
    parked = TVS_IR_MAX + Q1_IDSS_25 + NFET_IDSS_25
    log.info('parked drain from BATT (25 C bounds): TVS1 %.0f uA + Q1 IDSS %.0f uA + Q5 IDSS %.0f uA = %.0f uA '
             '(the LM2903B design: about 440 uA typ); ACC divider draws only while ACC is on', TVS_IR_MAX * 1e6,
             Q1_IDSS_25 * 1e6, NFET_IDSS_25 * 1e6, parked * 1e6)
    log.info('U5 works down to %.1f V; VDD_TMR comes from VOUT, so a +5V1 overload or U8 hiccup no longer reaches '
             'U5: the count completes and Q1 turns off (u5_supply())', U5_VDD_MIN_OP)


def u5_supply():
    """U5 supply (project lead 2026-11-05): VOUT -> R30 -> VDD_TMR, D7 zener clamp, R31 bleed, C8 decoupling. VOUT
    exists only while Q1 is on, so U5 is independent of +5V1 (U8 hiccup) and unpowered when parked."""
    log.info('--- U5 supply: VOUT -> R30 %.2fk -> VDD_TMR; D7 BZT52C5V1 to GND; R31 %.0fk bleed; C8 %.0f uF',
             R30_SUP * 1e-3, R31_BLEED * 1e-3, C8_NOM * 1e6)
    log.info('VOUT while counting: >= %.2f V (BATT %.1f V less %.0f A through the harness %.0f mohm and Q1 hot)',
             VOUT_MIN_COUNT, VB_MIN, I_TURN_OFF, R_HARNESS * 1e3)
    for vout in (VOUT_MIN_COUNT,) + VB_LIST + (VB_STANDOFF, TVS_VC_1, TVS_VC_2):
        v_lo, iz_lo = vdd_tmr(vout, False, True)
        v_hi, iz_hi = vdd_tmr(vout, True, False)
        _, iz_min = vdd_tmr(vout, True, True)
        log.info('  VOUT %5.2f V: VDD_TMR %.2f-%.2f V; zener %.2f-%.2f mA (vs the %.0f mA knee test point)', vout,
                 v_lo, v_hi, iz_min * 1e3, iz_lo * 1e3, IZT2 * 1e3)
    log.info('VDD_TMR range while counting %.2f-%.2f V (nominal %.2f V): operating %.0f-%.0f V, abs max %.0f V; the '
             'timing bound is solved over it (counter_timer())', VDD_TMR[0], VDD_TMR[2], VDD_TMR[1], U5_VDD_MIN_OP,
             U5_VDD_MAX_OP, U5_VDD_ABS)
    v_cl = vdd_tmr(TVS_VC_1, True, False)[0]
    log.info('at the %.0f V clamp (10/1000 us): VDD_TMR <= %.2f V (< %.0f V operating max); the %.1f V 8/20 us peak '
             'is filtered by R30 x C8 (%.1f ms)', TVS_VC_1, v_cl, U5_VDD_MAX_OP, TVS_VC_2, R30_SUP * C8_NOM * 1e3)
    for vout, label in ((VB_STANDOFF, 'continuous'), (TVS_VC_1, 'clamp pulse')):
        v_lo, iz_lo = vdd_tmr(vout, False, False)
        v_hi, iz_hi = vdd_tmr(vout, True, False)
        p_r = (vout - v_lo) ** 2 / R30_SUP
        p_z = max(iz_lo, iz_hi) * v_hi
        log.info('  %s %.0f V: R30 %.0f mW (1206 %.0f mW, %.0f mW at 85 C), zener %.0f mW (%.0f mW on FR-4; TJ rise '
                 '%.0f K at %.0f K/W), R31 %.1f mW', label, vout, p_r * 1e3, R1206_P * 1e3,
                 R1206_P * R_DERATE_85C * 1e3, p_z * 1e3, ZD_PTOT_FR4 * 1e3, p_z * ZD_RTHJA, ZD_RTHJA,
                 v_hi ** 2 / R31_BLEED * 1e3)
    for vout in (VB_MIN, VB_NOM, VB_MAX, VB_STANDOFF):
        v = vdd_tmr(vout, False, False)[0]
        i = (vout - v) / R30_SUP
        log.info('  power while on at VOUT %.1f V: %.1f mA from VOUT, %.0f mW (R30 + D7 + R31 + U5)', vout, i * 1e3,
                 vout * i * 1e3)
    log.info('U5 current at VDD_TMR max %.2f V: typical %.0f uA, datasheet maxima %.0f uA (85 C IDD %.0f + auto reset '
             '%.0f + oscillator %.0f)', VDD_TMR[2], u5_current(VDD_TMR[2], False) * 1e6,
             u5_current(VDD_TMR[2], True) * 1e6, _lin(VDD_TMR[2], U5_IDD_MAX_85C) * 1e6,
             _lin(VDD_TMR[2], U5_IDD_AR_MAX) * 1e6, VDD_TMR[2] / RTC * 1e6)
    log.info('zener leakage below the knee <= %.0f nA at %.1f V (25 C): only matters parked, where R31 dominates; '
             'the knee test point %.0f mA (ZZK <= %.0f ohm) is met at every corner above', ZD_IR_MAX * 1e9, ZD_VR_IR,
             IZT2 * 1e3, ZZK_IZT2_MAX)
    for t in (T_PARKED, T_HOT):
        i_l = _interp_log(t, T_DATASHEET, Q1_IDSS_25, T_HOT, Q1_IDSS_125)
        log.info('parked at %.0f C: Q1 IDSS bound %.1f uA (a 40 V figure) through R30 + R31: VOUT %.2f V, VDD_TMR %.2f '
                 'V vs Q5 VGS(th) hot min %.2f V and U5 %.0f V minimum: U5 stays dead, HOLD_G cannot rise', t,
                 i_l * 1e6, i_l * (R30_SUP + R31_BLEED), i_l * R31_BLEED, NFET_VTH_HOT_MIN, U5_VDD_MIN_OP)
    log.info('  without R31: the LED D3 / R3 is the only fixed VOUT sink and holds nothing below its knee; U5 at that '
             'VDD could power up with its output high (auto reset) and turn Q1 on through Q5 (re-latch)')
    tau = _par(R30_SUP, R31_BLEED) * C8_NOM
    log.info('key-on: VDD_TMR follows VOUT (tau %.2f ms, R30 || R31 x C8), MR already high from ACC_G: U5 starts '
             'in reset', tau * 1e3)
    log.info('end of count: Q1 off, VOUT and VDD_TMR collapse together; R31 discharges C8 (tau %.0f ms) once VOUT '
             'is down', R31_BLEED * C8_NOM * 1e3)
    k_div = R25_BOT / (R8_TOP + R25_BOT)
    for v in (VB_STANDOFF, TVS_VC_1, TVS_VC_2):
        g = (v - VF_UA[2]) * k_div
        i_mr = max(0.0, g - VDD_TMR[0] - V_CLAMP_CMOS) / R26_MR
        i_out = max(0.0, g - VF_UA[2] - VDD_TMR[0] - V_CLAMP_CMOS) / R29_HOLD
        log.info('ACC on at %.1f V: MR + OUT clamp currents <= %.0f uA into VDD_TMR (the zener takes them; VDD_TMR '
                 '%.2f V with them)', v, (i_mr + i_out) * 1e6, vdd_tmr(v, True, False, i_mr + i_out)[0])
    log.info('USB overload / U8 hiccup: no path to VDD_TMR (VOUT is BATT through Q1): the count completes on time')


def main():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT,
                        handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')])
    tvs_and_ratings()
    if '--history' in sys.argv:
        # the LM2903B RC / comparator timer (superseded 2026-11-05): kept as the record of its numbers
        comparator()
        q1_gate()
        acc_status_led()
        timer()
    counter_timer()
    u5_supply()
    q1_switching()
    buck()


if __name__ == '__main__':
    main()
