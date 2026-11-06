# Delay-off timer: LTspice sim (2026-11-04, TLC555 + discrete N-FET drivers)

Netlist: [ltspice/delay_off_timer.cir](../ltspice/delay_off_timer.cir) (master; open it directly in LTspice). Plots are from the run before the staff-review re-run (LED, D6 model, R22): the traces shown are unchanged within the plot resolution (assumption: not re-plotted). Logs: `ltspice/delay_off_timer.log` (default run), `ltspice/delay_off_timer_sw1.log` (`FORCE=1`). Plots (12 V, nominal, full load; traces ACC or SW1, VOUT, C5, Q, J5): [key sequence](sim_delay_off_12V_nominal.png), [SW1 run](sim_delay_off_SW1_12V_nominal.png). The old `ltspice/555_monostable.asc` is untouched. The previous report (SE555 + TPL7407LA, R9 1.3 MΩ) is in `pi_power_board-backups/sim_delay_off_2026-11-04_145245.md`, its logs next to it.

Run: copy `ltspice/` to `C:\tmp\pipwr\sim`, then `timeout 600 "C:\Program Files\ADI\LTspice\LTspice.exe" -b delay_off_timer.cir`. Default run ~90 s; the `FORCE=1` run ~150 s. The raw files are 0.5–1 GB: keep them off Google Drive and delete them after. Variants: copy the file and change one `.param` (`FORCE=1`, `CLAMP=0`, `DIS_TIED=1`). `pdm run python -I tools/plot_raw.py <raw> <png> <step> V(acc) V(vout) ...` plots a step (step 5 = 12 V, corner 2, full load).

## What changed (project lead, 2026-11-04)

| Change | Was | Now |
|---|---|---|
| U4 | SE555 (LTspice ideal `NE555`, threshold spread scaled by hand) | **TLC555QDRQ1, behavioural model** with the datasheet threshold window in the corners |
| Drivers | TPL7407LA channels (switch with VIL/VIH hysteresis) | **Q2/Q4 2N7002BK** (Q3 dropped in the re-run; generic VDMOS, V_GS(th) per corner) |
| OR filter | R2 10k / R1 5.1k / C2 1 µF into U2 IN1 | R2 10k / **R1 10k** / C2 1 µF into `DRV_G` (Q2 gate) |
| Status | R6 47k / R7 22k / C3 into U2 IN3, OUT3 → J5 | R6 47k / **R7 47k** / C3 into `STAT_G` → Q4 → **R21 1 kΩ** → J5, Pi pull-up 50 kΩ to 3.3 V **(assumption)** |
| Logic supply | 100 Ω + 15 V zener, `RQ` 2 kΩ (NE555 supply) | **220 Ω + 13 V zener** (DZ1 1SMA5928B), `RQ` 5.1 kΩ (TLC555 + LM397 near their maxima), 1 µF + 2 × 100 nF |
| DCL | BAV116W, 80 nA at 125 °C | **BAS116LT1G, 80 nA at 150 °C** (same corner value) |
| R9 tolerance | added afterwards in `tools/design_calc.py` | **in the sim corners** (−1 % / +1 %) |
| Integration | trapezoidal | **gear** (trap rang on the high-impedance J5 node; delays unchanged within 0.1 ms) |
| LED (staff review re-run, project lead) | D3 + R3 from BATT through Q3 | **D3 + R3 from VOUT to GND**, Q3 removed |
| D6 model (staff review re-run) | 1N4148 | **BAS116 fitted to its V_F maxima** (0.9 V at 1 mA, 1.0 V at 10 mA, 1.25 V at 150 mA) |
| U4 inputs (staff review re-run) | TRIG/THRES directly on C5 | **R22 10 kΩ** from C5 to `U4_TR`, plus a generic input clamp diode to VDD **(assumption)** |

## Model

- **U4 (TLC555-Q1, SLFS078D):** no LTspice model, so a behavioural one:
  - THRES level: 2.7–3.9 V at VDD 5 V, 9.35–10.65 V at 15 V (5.5/5.6, full temperature range), linear in VDD between them **(assumption)**, constant ratio outside. Corner 1 = minimum, corners 3/4 = maximum, corner 2 = 2/3·VDD.
  - TRIG level 1/3·VDD (C5 sits near 0.1 V while U3 is on, far below the 1.26 V datasheet minimum).
  - Latch priority RESET > TRIG > THRES (6.1). RESET is on VDD: modelled as a reset below VDD 2 V (the recommended minimum).
  - Output VDD × state through 900 Ω: VOH at its datasheet minimum (VDD − 0.9 V at −1 mA, 5 V row).
  - Input currents: TRIG + THRES 2 × 5 nA, sourced into C5 in corner 1 and sunk in corners 3/4.
  - Supply current: part of `RQ`. DISCH: not connected (`DIS_TIED=1` adds an ideal discharge switch on C5).
- **Q2, Q4 (2N7002BK):** VDMOS, Kp and capacitances near the typicals (R_DS(on) ≈ 1.3 Ω at 5 V). V_GS(th) from the datasheet V_GS(th)-vs-temperature graph: 2.35 V (cold max) in corner 1, 1.6 V nominal, 0.75 V (hot min) in corners 3/4. No sub-threshold conduction (the datasheet shows about 180 mV/decade below threshold), so the sim can't show partial turn-on from a back-fed or leakage-fed VOUT: that is by calc (SPEC 2).
- Comparator: behavioural open collector (45 Ω on), off below a 2 V supply. Q1: generic P VDMOS (unchanged).
- Steps (24 runs): BATT 9 / 12 / 14.4 V × corner 1–4 × load (3.3 Ω full / 1 kΩ light).
  - Corner 1 (short): C5 × 0.765, R9 −1 %, THRES minimum, 555 input currents sourced, DCL leakage 80 nA, N-FET V_GS(th) max.
  - Corner 2: nominal.
  - Corner 3 (long): C5 × 1.265, R9 +1 %, THRES maximum, 555 input currents sunk, N-FET V_GS(th) min.
  - Corner 4 (stall): corner 3 plus LM397 output leakage at its 1 µA limit.
- ACC: on 1 s, off 5 s; on 90, off 94, on 100 (mid-delay), off 102; 50 ms blip at 190 s. `FORCE=1`: ACC stays off; SW1 on from 1 s to 80 s.
- All capacitors start empty at t = 0 with the battery already at VB (`uic`): t = 0 is a **battery hot-plug**.
- Logic VCC while on: 8.57 / 11.43 / 13.01 V at 9 / 12 / 14.4 V BATT (full load).

## Results

Delay = ACC (or SW1) falling through VB/2 to VOUT falling through VB/2. Ranges over BATT 9–14.4 V and both loads. Corner 1 is the worst case directly (no hand scaling any more).

| Case | Expected | Measured (corner 1 / 2 / 3 / 4) | Pass |
|---|---|---|---|
| Key off | ≥ 10 s | **11.10–12.28** / 18.32–18.64 / 26.83–28.73 / 33.91–43.63 s | yes |
| Key on mid-delay, then off | full delay restarts | equal to key-off within 0.2 ms | yes |
| VOUT held through the mid-delay key-on | no dropout | min VOUT 8.94 / 11.93 / 14.32 V at 9 / 12 / 14.4 V (full load) | yes |
| 50 ms ACC blip while off | VOUT on, full delay | 11.09–12.28 / 18.32–18.64 / 26.83–28.72 / 33.95–43.70 s | yes |
| Chatter / re-latch | 3 rising edges of VOUT, Q and DRV_G (DRV_G counted at 0.75 V, the lowest threshold) | no 4th edge in any of the 24 runs (either run) | yes |
| **Stall (corner 4, LM397 leakage at its limit)** | turns off | 33.9–43.6 s | yes |
| VOUT in the 5 s before each next ACC edge | ≈ 0 | \|VOUT\| ≤ 0.05 mV | yes |
| C5 above VCC during the collapse (DCL fitted) | ≤ a diode drop | ≤ 1.01 V (D6 up to 8.2 mA at full load) | yes |
| **U4 TRIG/THRES above VDD** (abs max VDD) | small, current-limited | ≤ 0.57 V, clamp current ≤ 43 µA (R22; without it the pins would share D6's mA) | yes |
| **Battery hot-plug** (t = 0, ACC off) | VOUT and DRV_G stay off | VOUT ≤ 0.55 mV, DRV_G ≤ 0.08 mV | yes |
| **Inrush at key-on** | modest | 2.0–5.4 A (light load the highest); VOUT 10–90 % in 1.5–2.4 ms | yes |
| **Q2 gate drive** | ≥ V_GS(th) max (2.35 V cold) | from ACC ≥ 3.96 V, from the 555 alone (inside the delay) ≥ 3.84 V, both at 9 V (calc worst 3.70 / 3.32 V); Q2 drain ≤ 0.17 mV while on | yes |
| 555 Q high (VOH) | | 8.22 / 10.96 / 12.48 V at 9 / 12 / 14.4 V (VDD − 0.35 to 0.55 V) | |
| LED (from VOUT) | about 2 mA at 12 V | 1.39–2.46 mA (9–14.4 V) | yes |
| **Q4 status, key** | Q4 gate ≥ 2.35 V on; J5 low on, released off | gate ≥ 4.22 V; J5 65 mV on, 3.30 V off | yes |
| **SW1 on, key off** (`FORCE=1`) | VOUT on, Pi sees "ACC on", no timeout while on | VOUT ≥ 8.94 V throughout; J5 ≤ 65 mV; Q stays high (falls only after SW1 opens) | yes |
| **SW1 opened** | Pi warned at once, then the full delay | J5 above 1.65 V 1.8–7.4 ms after SW1 opens; VOUT off 11.10–12.28 / 18.32–18.64 / 26.83–28.73 / 33.91–43.63 s later (same as the key) | yes |

### Worst case and margins

- **Worst-case delay: 11.09 s in the sim** (9 V, corner 1); `tools/design_calc.py` `timer()` gives **10.84 s** (it starts C5 at 0.1 V and uses the worst-case VDD 8.34 V: Q1 hot at 5 A, logic at its maxima; more pessimistic). Target ≥ 10 s: met by 0.9 s. The SE555 design was 10.19 s (TRIG current 0.9 µA gone, thresholds now guaranteed over temperature).
- **Nominal: 18.3–18.7 s** (was 18.3–18.6 s).
- **Stall limit** (calc): 1.67 µA at 9 V (VDD 8.34 V) against 1.01 µA of known sinks → C5 + C6 insulation ≥ 9.4 MΩ hot (was 17.3 MΩ). One 10 µF capacitor with R9 2.6 MΩ would stall (largest R9 without insulation leakage: 2.22 MΩ), so R9 / C5 stay 1.3 MΩ / 2 × 10 µF.
- **Glitch rejection:** the OR filter is now 5 ms on / 10 ms off (R1 ∥ R2·C2, R1·C2), from 3.4 / 5.1 ms. The 50 ms blip still gives a full delay, the restart and re-latch counts are unchanged, and the delays match the key-off delays: the filter change doesn't show in the timing.

## Findings

- **TLC555:** better worst case (no TRIG current, thresholds specified hot), smaller stall sink. Its VOH minimum (VDD − 0.9 V) is the weakest gate drive: 3.84 V at Q2 at 9 V in the sim (calc worst 3.32 V), 0.97–1.5 V above the cold V_GS(th) max.
- **N-FET drivers:** zero quiescent current; Q2 fully on (drain ≤ 0.2 mV) in every corner; no hot-plug turn-on (C2 and R1 hold DRV_G at 0).
- **Staff review re-run (BAS116 model, R22, LED on VOUT):** delays within 0.03 s of the previous run; no 4th edge of VOUT, Q or DRV_G in either run; the input-overdrive check is new (row above).
- **J5:** clean open drain through R21; no back-feed path with the HAT unpowered (by analysis: R7 holds Q4 off; not simulated).
- **Model limits:**
  - behavioural 555 and comparator; generic VDMOS for Q1–Q4, not vendor models;
  - TLC555 THRES limits interpolated between the 5 V and 15 V rows;
  - resistive load (a constant-power Pi regulator collapses faster, the safer direction);
  - C5 constant (no C(V));
  - the Pi regulator's input capacitance (470 µF) and the Pi pull-up (50 kΩ) are assumed;
  - with the trapezoidal method J5 rang by about 0.1 V on the drain capacitance (numerical; gone with gear or with the drain capacitances removed).
- **Bench test:** key-off and SW1-off at 9 V and 14.4 V; scope VOUT, Q, DRV_G and J5. Key-on inrush with the real Pi regulator attached. VCC_LOGIC at 14.4 / 16 V.
