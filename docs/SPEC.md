# Pi power HAT: specification

The contract for every later phase: the current design only. Reasons go in [DECISIONS.md](DECISIONS.md), open work in [TODO.md](TODO.md). An agent interpretation not yet confirmed by the project lead is marked **(assumption)**. Tools parse the **Parts** table (`tools/digikey_lookup.py`): keep its heading and column names. The schematic phase implements section 7 (**Netlist**) verbatim. Calculations: `tools/design_calc.py`, [reports/buck_design.md](../reports/buck_design.md), [reports/sim_delay_off_counter.md](../reports/sim_delay_off_counter.md), [reports/timer_survey.md](../reports/timer_survey.md).

**2026-11-06 (latest): buck U8 datasheet fixes (`reports/ic_review.md` flags; implemented by A22).**

- **L1 15 µH** (SRP1038A-150M, same footprint): K_IND 0.23 at 16 V (≤ 0.3, SLVSCD5D 8.2.2.6.1). **C31** second 10 µF 50 V input capacitor: eq 17 ripple 227 mV (was 441). **C32** fourth 47 µF output capacitor: eq 22 margin 35 % at 25 % DC-bias retention (was 1 %). **R16 / R17 73.2 k / 13.7 k:** VOUT 5.074 V, worst 4.915–5.238 V (was 5.088, up to 5.252). **R18 7.32 k** (C20 15 nF kept): fc 16–42 kHz, PM ≥ 45.8° incl. fsw 272–408 kHz (staff review R22). Parts 39 → **41**.
- Board: the buck power block (U8, C17, C15) moved down below J5 as one rigid block, so the FB divider sits at pin 5 and the COMP / SS parts at pins 6 / 8 on the top layer, with a separate analog ground trace to the PowerPAD (section 5 "Buck layout"). `tools/post_sch/16`, `tools/post_route/16`.

**2026-11-05: U5 from `VOUT` (project lead decision; implemented by A13).**

- U5 now runs from **`VOUT` through R30 1.3 kΩ**, clamped by **D7 = BZT52C5V1** (5.1 V zener, was the BAT43W from `+5V1`), with **R31 10 kΩ** bleed and **C8 1 µF 0805** (was 10 µF 1206) on `VDD_TMR`. `VOUT` exists only while Q1 is on: no `+5V1` fault reaches U5 and the parked drain is unchanged.
- **USB overload closed:** sim OVL (0.5 Ω on `+5V1` mid-count, 24 steps) and the 0.5 / 0.8 / 1.0 Ω sweep: the hold ends on time in **every step** (was 17 of 18 stuck).
- `VDD_TMR` 4.45–5.71 V while counting; delay **26.1 / 29.5 / 32.5 s** (calc), R27 / C29 / R28 unchanged. Parts 37 → **39**. R31 is beyond the lead's brief (parked Q1 leakage, section 2): lead item (TODO).
- Schematic: `tools/post_sch/09_u5_vout_supply.py`; `10_u5_value_field.py` (staff review: U5 value text only, no netlist change). Staff review 2026-11-05: pins, nets and timing re-checked against the datasheets; R31 is needed (DECISIONS), kept.

**2026-11-05: counter timer on paper (project lead: clock + counter on +5V1, no LDO, no Pi HOLD line).**

- The LM2903B RC / comparator timer is replaced by **U5 CD4541B** (RC oscillator + 16-stage counter) powered from `+5V1`. Chip choice: `reports/timer_survey.md`.
- 35 parts → **36**, not counting J1, J2, J4, J5, SW1 and MH1–MH4:
  - out: U1, R4, R5, R9, R23, R24, C5, C27, C28;
  - in: U5, Q5, Q6, R25–R29, C29, C30;
  - R8, D6 and C8 kept with new nets.
- Sections 1–4, 6 and 7 are rewritten.
- The schematic implements section 7 since `tools/post_sch/08_cd4541_timer.py` (2026-11-05); **the board still shows the LM2903B design** (placement phase).

**2026-11-05 (later): hold ≥ 25 s worst case (project lead, was 45 s); timer re-tuned and reviewed (staff review A12).**

- R27 42.2 kΩ → **39.2 kΩ**, C29 22 nF ±5 % → **10 nF C0G ±1 %**, R28 84.5 kΩ → **78.7 kΩ**: 1.11 kHz nominal, **1.25 kHz at the short corner** (inside the datasheet formula's 1–100 kHz range).
- Delay **26.2 s short / 29.5 s nominal / 32.5 s long** (calc and sim). Part count unchanged (36).
- Oscillator constant bound re-derived from the datasheet structure: 2.105–2.449 (A11 assumed 2.0–2.6).
- A persistent USB overload during the key-off count could keep Q1 on with the key off (U8 hiccup re-powers U5, whose auto reset restarts the count): D7 + C8 (next note), then U5 from `VOUT` (latest note).

**2026-11-05 (project lead decisions a–c; implemented and simulated by A12).**

- **(a) superseded by "U5 from `VOUT`" (latest note).** D7 BAT43W (Schottky, SOD-123) from `+5V1` to a new net **`VDD_TMR`** (U5 VDD, A, B, Q/Q̅ SELECT); **C8 100 nF → 10 µF 50 V X7R 1206** on `VDD_TMR`. U5 rides through one U8 hiccup off time at its typical current. Parts 36 → **37**.
  - **Result: the stuck-on is closed only for soft overloads, not for hard ones** (sim OVL, section 2): a retry that lifts `+5V1` above `VDD_TMR` keeps U5 counting and the hold ends on time; a hard overload (0.5 Ω, retry peak ≈ 2.4 V) leaves U5 at 1–2.5 V with its output high, and Q1 stays on in **17 of 18** steps (9 of 18 without D7). **Lead decision (TODO).**
- **(b) C22–C24: 47 µF 10 V X7R 1210** (Cal-Chip GMC32X7R476K10NT). Digi-Key lists no 47 µF 10 V X7R in 1206; one 1210 part per position keeps the count.
- **(c) Hand assembly: nothing smaller than 0805** (section 5). Smallest bodies: 0805 passives, SOT-23, SOD-123.

## 1. What it is

- A Raspberry Pi 5 HAT for a car.
  - While the key is on (ACC), it switches battery 12 V to the Pi's external 12 V regulator (J4).
  - After key-off it holds the power for a delay, so the Pi can shut down.
  - It reports ACC to a Pi GPIO.
- A 5 V USB-A charging port pair (J2A/J2B) from a buck (U8) on the switched rail.
- Hand-soldered, 2 boards. KiCad 10.0.7.

```
J1 BATT ─┬─ TVS1 ─ GND
         ├─ C30 100n ─┐
         ├─ R14 220k ─┴─ Q1_G ─ R15 180k ─ DRV ─ Q5 (D; S = GND; G = HOLD_G)
         ├─ Q1 P-FET (S) ──(D)── VOUT ─┬─ J4 (Pi 12 V regulator)
         │                             ├─ U8 TPS54336A → +5V1 ── J2A / J2B VBUS
         │                             ├─ R30 1.3k → VDD_TMR ─ U5 CD4541B VDD (D7 5.1 V zener, R31 10k, C8 1µ to GND)
         │                             └─ D3 LED → R3 → GND ("Pi power on")
         └─ SW1 ─ D4 ────────┐
J1 ACC ─┬─ TVS2 ─ GND         │
        └─ D5 ───────────────┴─ ACC_S ─ R8 22k ─ ACC_G ─┬─ R25 27k ─ GND
                                                        ├─ Q6 G: D ─ R21 1.5k ─ J5 → Pi GPIO (low = ACC on)
                                                        ├─ D6 ─────────────┐
                                                        └─ R26 100k ─ U5 MR │
                              U5 OUT ─ R29 47k ─────────────────────── HOLD_G ─ Q5 G
                              U5 RC: R27 39.2k (RTC), C29 10n C0G 1 % (CTC), R28 78.7k (RS)
```

Timing (not to scale):

```
ACC      ‾‾‾‾‾‾‾‾‾‾‾‾\____________________________/‾‾‾‾\______________________________________
U5 MR    ‾‾‾‾‾‾‾‾‾‾‾‾\____________________________/‾‾‾‾\______________________________________
counter  0 (reset)    1, 2, … (1.11 kHz) ……… ↺ 0  (reset) 1, 2, … 32768 → output latched low
HOLD_G   ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\________
VOUT     ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\________  (+5V1, VDD_TMR collapse too)
J5       low ‾‾‾‾‾‾‾‾\ released __________________/low \ released ____________________________
                          key on mid-count = full restart          ≥ 25 s worst case (29.5 s nominal)
```

## 2. Blocks and nets

| Block | Function | Nets |
|---|---|---|
| Input | J1: GND (1), ACC (2), BATT (3) screw terminal. TVS1 on `BATT`, TVS2 on `ACC_IN`, both at J1. No onboard fuse: **7.5 A slow-blow inline fuse in the harness** (project lead) | `BATT`, `ACC_IN`, `GND` |
| ACC sense | `ACC_S` = J1 ACC through D5, or `BATT` through SW1 and D4. D5 keeps `BATT` off the car's ACC line; D4 keeps the ACC line off `BATT` (SW1 closed with `BATT` dead would otherwise run the whole load through D5 and SW1). `ACC_S` = `BATT` − V_F in SW1 mode, the same as a key-on. **SW1 acts like the key** | `ACC_S` |
| ACC interface | `ACC_G` = `ACC_S` through R8 22 kΩ / R25 27 kΩ (ratio 0.551; the divider is also the `ACC_S` pull-down, 49 kΩ). `ACC_G` drives three loads: the Q6 gate (status), D6 into `HOLD_G` (direct Q1 turn-on), R26 100 kΩ into U5 MR (reset). R26 and R29 keep the U5 input / output clamps from pulling `ACC_G` down while `VDD_TMR` is still 0 V (section 3) | `ACC_G`, `U5_MR` |
| Timer U5 | **CD4541BM96** (TI, SOIC-14, −55 to 125 °C) on **`VDD_TMR`** = `VOUT` through **R30** 1.3 kΩ, clamped by **D7** (BZT52C5V1, 5.1 V zener), **R31** 10 kΩ bleed and **C8** 1 µF at pins 14/7: 4.45–5.71 V while counting, independent of `+5V1` (section 3). RC oscillator R27 / C29 / R28 (1.11 kHz nominal). A = B = 1 (tap 2^16: the output changes after 2^15 counts), Q/Q̅ SELECT = 1 (output high after reset), MODE = 0 (single transition: the output stays low until the next reset), AR = 0 (auto reset on power-up on). MR high = ACC on: counter held at 0, output high. ACC off: counts 32 768 clocks, then the output goes low and stays. Section 3 | `VDD_TMR`, `U5_RTC`, `U5_CTC`, `U5_RS`, `U5_TJ`, `U5_OUT` |
| Hold OR | `HOLD_G` (Q5 gate) = U5 OUT through R29 47 kΩ, or `ACC_G` through D6 (BAS116, low leakage). One FET on `DRV`, not two in parallel, so the Q1 off-state leakage stays inside its margin (section 4) | `HOLD_G` |
| High-side switch | Q1 P-FET, source `BATT`, drain `VOUT`. Gate: R14 220 kΩ to source, R15 180 kΩ to `DRV`, **C30 100 nF gate-source** (battery hot-plug: section 4). Q5 2N7002BK pulls `DRV` to GND while `HOLD_G` is high | `Q1_G`, `DRV` |
| ACC status to the Pi | Q6 2N7002BK, gate `ACC_G`, drain `STAT_O` → R21 1.5 kΩ → J5 pin 2; J5 pin 1 GND. The Pi's pull-up sets the level (≤ 3.3 V). **Low = ACC on** (key or SW1); released = ACC off → Pi shuts down. It follows ACC directly, not the timer | `STAT_O`, `ACC_N` |
| USB charging | U8 TPS54336A from `VOUT` → `+5V1` (5.07 V), 3 A total for J2A + J2B. D+ shorted to D− on each port (BC1.2 dedicated charging port). Ceramic output capacitors only. EN floating (internal pull-up), no UVLO divider. `+5V1` no longer supplies U5 (project lead 2026-11-05: U5 from `VOUT`) | `+5V1` |
| Pi supply | J4: `VOUT`, GND to the Pi 5's 12 V regulator | `VOUT` |
| LED | D3 + R3 from `VOUT` to GND: lit whenever `VOUT` is on ("Pi power on") (project lead) | `D3_K` |

- Ground net: `GND`.
- **Parked current from `BATT`** (key off, hold over): nothing is powered.
  - TVS1 ≤ 1 µA, Q1 I_DSS ≤ 1 µA, Q5 I_DSS ≤ 1 µA (all 25 °C bounds).
  - **≤ 3 µA** (the LM2903B design took ≈ 0.44 mA). The ACC divider (49 kΩ) draws only while ACC is on.
  - **`VOUT` parked:** Q1's off-state leakage (≤ 10.5 µA at 85 °C, 50 µA at 125 °C: log-interpolated I_DSS limits, a 40 V figure) flows into `VOUT`. Without a sink, `VOUT` would rise to the LED D3 knee, where U5 could wake with its output high (auto reset) and turn Q1 on through Q5. **R31** (through R30) holds `VOUT` ≤ 0.12 V and `VDD_TMR` ≤ 0.10 V at 85 °C (0.57 / 0.50 V at 125 °C), below U5's 3 V and Q5's 0.75 V hot threshold (`design_calc.py` `u5_supply()`). Sim (corner 3 with the 85 °C leakage): hot-plug `VDD_TMR` ≤ 13 mV.
- **`+5V1` brownout / USB overload: closed by U5 on `VOUT` (project lead, 2026-11-05).** A USB load that pulls `+5V1` down, or a persistent overload that makes U8 hiccup (above its 3.5–6.1 A current limit: off 16 384 cycles, then a new soft start, SLVSCD5D 6.5, 7.3.13), no longer reaches U5: `VOUT` is `BATT` through Q1, and `VDD_TMR` comes from it.
  - Before (U5 on `+5V1`, then on `+5V1` through D7 + C8): each retry re-powered U5 (auto reset → count restarted), or a hard short left U5 below 3 V with its output high; Q1 stayed on with the key off in 9 of 18 / 17 of 18 OVL steps (DECISIONS).
  - **Now: sim OVL (0.5 Ω on `+5V1` from 8 s into the count, LOAD 3, Pi halted 2 W and in deep power-off 0.05 W, 9 / 12 / 14.4 / 16 V, three corners): the hold ends at the count in 24 of 24 steps** (26.17–33.04 s after key-off; `VDD_TMR` never dips: 4.53–5.70 V). Sweep 0.5 / 0.8 / 1.0 Ω at 12 V: 9 of 9 end on time, independent of the overload. The 0.05 W cases cross VB / 2 up to 0.45 s later than the 2 W ones: `VOUT` decays slowly with almost no load once Q1 is off.
  - While ACC is on, nothing changes: D6 holds Q5 on from `ACC_G`; a USB fault only affects the USB ports.
- **Pi-side configuration (assumption: verify on Pi OS):**
  - GPIO input with the internal pull-up; shutdown on the rising edge (ACC off).
  - Example: `dtoverlay=gpio-shutdown,gpio_pin=<N>,active_low=0,gpio_pull=up`.
  - **The Pi software must also check the `ACC_N` level at boot, not only edges.** A rapid key cycle (key on for a moment, then off) cold-boots the Pi with ACC already off: no edge comes after boot, and `gpio-shutdown` acts on edges **(assumption: verify on the Pi 5)**. The hold (≥ 25 s worst case, section 3) covers a cold boot, that level check and a clean shutdown (project lead, 2026-11-05: 25 s, was 45 s).
  - A missing J5 cable reads as "ACC off" (the Pi shuts down): fail-safe.
  - **No HOLD line from the Pi** (project lead, 2026-11-05): J5 stays 2-pin. The hardware cuts `VOUT` at the end of the count whatever the Pi is doing.
  - **Key back on during the delay after the Pi has started its shutdown:** `VOUT` stays on (the count restarts), so the Pi stays halted with power until the next key-off delay ends. The hardware can't fix this without a power cycle; the Pi side must handle it (wait some seconds of "ACC off" before shutting down, or wake from halt) (lead question, TODO).
  - Q6 off-state leakage ≤ 1 µA (25 °C): 50 mV across a 50 kΩ pull-up.
- **J5 protection (cable to the Pi):** J4 and J5 are the same block, so J5 could be wired to 12 V by mistake.
  - R21 1.5 kΩ limits the current into Q6 to 10.7 mA at 16 V (2N7002BK I_D 350 mA), 0.17 W in R21 (1206).
  - Q6 V_DS is rated 60 V; its gate is ESD-protected (2 kV).
  - Low level with ACC on: 0.10 V (sim, 50 kΩ Pi pull-up).
  - No TVS on J5 **(assumption: the J5 cable stays inside the car with the Pi)**.
- **Back-feed (Pi powered from elsewhere, `VOUT` held up by the Pi regulator):**
  - With a battery, nothing on `VOUT` drives `DRV` or `HOLD_G` directly, so Q1 stays off while U5 is unpowered.
  - A back-fed `VOUT` (≈ 4.3 V, assumption) powers U5 through R30: `VDD_TMR` 3.2–3.7 V (calc). Its auto reset (not reliable below 5 V) can give **one hold**: Q1 on from `BATT` for one count, then off, with U5 latched low while the back-feed lasts. It ends no worse than the Pi already being powered. U8 cycling at its UVLO no longer restarts U5 (bench).

## 3. Delay-off timer

```
VOUT ─ R30 1.3k ─ VDD_TMR ─┬─ U5 14 VDD, 9 Q/Q̅ SELECT, 12 A, 13 B     GND ─ U5 7 VSS, 5 AR, 10 MODE
                            ├─ C8 1µ ─ GND
                            ├─ D7 BZT52C5V1 (K) ─ GND
                            └─ R31 10k ─ GND
U5 1 RTC ─ R27 39.2k ─┐
U5 2 CTC ─ C29 10n ───┼─ U5_TJ                        ACC_G ─ R26 100k ─ U5 6 MR
U5 3 RS  ─ R28 78.7k ─┘                               U5 8 OUT ─ R29 47k ─ HOLD_G ─ Q5 gate;  ACC_G ─ D6 ─ HOLD_G
```

- **U5 = CD4541B** (TI SCHS085E), chosen over CD4060B, CD4536B, LTC6993/6994/6995, TPL5110/5111, 74HC4040 and an ATtiny402: [reports/timer_survey.md](../reports/timer_survey.md).
- **Pin settings (SCHS085E truth table and frequency table):**
  - A = B = 1: 16 stages, and the output changes "after 2^(N−1) counts" = **32 768 counts**;
  - Q/Q̅ SELECT = 1: "output initially high after reset";
  - MODE = 0: single transition, the output stays until the next MASTER RESET;
  - AR = 0: auto reset on;
  - NC pins 4, 11 unconnected.
- **ACC on (key or SW1):**
  - `ACC_G` turns Q6 on (J5 low) and, through D6, Q5 (Q1 on).
  - Neither needs `VDD_TMR`: Q1 turns on 1.9–12 ms after ACC (sim, C30 included).
  - `VDD_TMR` follows `VOUT` (R30 ∥ R31 · C8 = 1.15 ms); U8 brings `+5V1` up at 4.3–13.2 ms after ACC (sim).
  - From its first volt U5 sees MR high (clamped to VDD + V_F through R26), so it starts in reset: counter 0, output high, oscillator stopped. The datasheet asks for VDD > 5 V for a *reliable auto* reset; `VDD_TMR` is 4.45–5.71 V, but every key-on start is an MR reset, so only an ACC-less power-up (hot-plug, back-feed, a sub-start-up blip) relies on the auto reset **(assumption: acceptable; an unreliable auto reset there gives no hold or one bounded hold)**.
- **Key off:**
  - `ACC_G` falls: J5 is released at once (≤ 0.42 ms, sim) and MR goes low. The oscillator starts at 0; D6 blocks; R29 keeps `HOLD_G` high from U5 OUT.
  - After 32 768 clocks the output latches low. Q5 turns off, then Q1 (C30 adds a ≈ 28 ms turn-off delay), and `VOUT` collapses.
  - `VDD_TMR` falls with `VOUT` (R30 / R31 / D3 discharge `VOUT`'s capacitance once the load stops: seconds with the Pi in deep power-off). U8 stops (UVLO) and `+5V1` decays: 0.3 ms to 4.6 s from 4.5 V to 1 V (sim, with and without USB load); `+5V1` no longer feeds U5. The sim shows one turn-off per key-off.
- **Key on mid-count:** MR high clears the counter, and the next key-off counts the full 32 768 again (sim: restart delay = key-off delay in every step; counter at 0 within 0.5 s of the key-on).
- **Short key-on (blip):**
  - A key-on long enough for `+5V1` to start (≤ 13.2 ms, sim worst case) gives the full delay (sim: a 50 ms blip = the key-off delay).
  - Shorter than about 2 ms: Q1 does not turn on (C30 delay).
  - In between: either nothing or a full hold (auto reset). Both are acceptable **(assumption: a key cycle that boots the Pi keeps ACC on far longer)**.
- **Battery hot-plug, key off:** `ACC_G` = 0, U5 unpowered, `HOLD_G` ≤ 1.0 V for microseconds (Q5 C_gd kick; < 2.35 V cold / 1.6 V nominal threshold; 0.56 V in the hot corner against 0.75 V). C30 holds Q1 off, so `VOUT` ≤ 0.5 mV in every corner (sim).
  - **Without C30**, the sim at 16 V with Q1 at its hot threshold turned Q1 on through C_gd: U8 started, U5 auto-reset into a hold, and a full delay ran with the key off. That is why C30 is there (section 4).
- **No re-latch after the time-out:**
  - U5 OUT stays low while `VDD_TMR` falls: the output latch keeps its state, and VOH ≤ VDD anyway. Q5 stays off and `HOLD_G` ≤ 1 nV (sim). Nothing else feeds `DRV` or `HOLD_G`.
  - Sim: exactly one turn-off per key-off in 36 steps, including LOAD 3; `VDD_TMR` ≤ 0.93 V in the off windows while `VOUT` still decays.
  - **Risk:** the datasheet doesn't describe what the auto-reset circuit does on a slowly falling VDD (`VDD_TMR` follows `VOUT`'s slow decay with the Pi in deep power-off). If it fired during the collapse, U5 OUT would go high at a low VDD and could re-latch one more full hold. The model resets only on a rising VDD **(assumption)**. Bench TODO: 10 key-off cycles with no USB load, hot and cold.
- **Delay** = 32 768 / f_osc, f_osc = 1 / (k · RTC · CTC), k = 2.3 in the datasheet, **stated for 1–100 kHz** (and RS ≥ 10 kΩ, ≈ 2·RTC).
  - **Frequency:** 1.11 kHz nominal; **1.25 kHz at the short corner** (26.1 s), the one that sets the guarantee (25 % above the formula's floor); **1.008 kHz at the long corner**.
  - The guarantee caps the short-corner frequency at 32 768 / 25 s = 1.31 kHz. The 2^16 tap is the longest; a shorter tap would need a lower frequency for the same delay.
  - **Oscillator constant k bound 2.104–2.450**, from the datasheet structure, not assumed (`design_calc.py` `_osc_k()`):
    - fig. 2 solved segment by segment: one input threshold at 0.3–0.7·VDD (the VIL / VIH limits), VDD 4.45 / 5.71 V (the `VDD_TMR` range; SCHS085E has no frequency-vs-VDD curve);
    - RS-pin protection diodes (0.3–0.7 V) and input current ±1 µA (the 85 / 125 °C limit);
    - driver resistance 0–370 Ω on each pin (VOL 0.4 V at the 125 °C sink rating);
    - gate-chain delay 0–1 µs per transition **(assumption: no datasheet figure)**.
    - Result 2.147–2.402, plus **±2 % allowance (assumption)** for the LTspice gate model (up to 2 % lower) and silicon beyond fig. 2. The datasheet's 2.3 is inside.
  - **R / C:** RTC 1 % with ±100 ppm/K **(assumption: BOM checks the part)**; C0G ±1 % with 0 ± 30 ppm/K; both over −40 to 125 °C.
  - **Supply `VDD_TMR` 4.45–5.71 V while counting** (zener clamp, `VOUT` ≥ 8.58 V; ≤ 5.72 V while ACC is on at 16 V, 6.18 V at the 26 V clamp; see Supply): the bound is solved over this range **(assumption: the 0.3 / 0.7 VDD fractions, tabulated at 5 and 10 V, hold over 4.4–5.8 V)**. The clamp also keeps VDD off the battery voltage during the count.
  - **C0G tolerance:** ±1 % is needed. With ±5 % the short corner is 25.1 s (no margin) and the long corner 970 Hz; with ±2 %, 25.9 s and 998 Hz.
- **Counter logic sim** (×1000 frequency, the same circuit with CTC and pin capacitance scaled): `reports/sim_delay_off_counter.md`.
- **Inputs:**
  - **MR:** VIH 0.7·VDD (3.5 V at 5 V). At a 9 V battery (cold diode) `ACC_G` ≥ 4.52 V, and MR ≥ 4.42 V after the input current × R26 (≤ 0.10 V): above VIH 4.00 V at `VDD_TMR` 5.71 V (the highest; 5.57 V at 9 V). This sets the zener: VIH ≤ 4.42 V needs VDD ≤ 6.3 V, so `VDD_TMR` can't follow `VOUT`, and the divider can't rise (FET gates, section 4).
  - **Clamp current:** `ACC_G` exceeds VDD + 0.5 V above ACC ≈ 11 V, so the MR protection diode conducts through R26: 29 µA at 16 V, 84 µA at the 26 V clamp, 127 µA at 33.8 V (SCHS085E: DC input current ±10 mA abs max); the U5 OUT clamp adds ≤ 275 µA through D6 / R29. Both flow into `VDD_TMR`, where the zener takes them: `VDD_TMR` ≤ 5.72 / 6.18 / 6.54 V at 16 / 26 / 33.8 V (operating max 18 V). Q5's gate sees ≤ 18.4 V from `ACC_G` (±20 V).
  - **Off:** a leaking "off" ACC line (10 µA, assumption) gives `ACC_G` 0.27 V: below VIL (1.34 V at `VDD_TMR` 4.45 V) and the hot FET threshold (0.75 V).
- **Key-on before Q1 is on (start-up):** `ACC_G` is loaded by R26 into MR and by D6 + R29 into U5 OUT, both clamped near 0 V (`VDD_TMR` empty; R31 and R30 into `VOUT` load it).
  - At 9 V, cold, `ACC_G` ≥ 3.59 V and `HOLD_G` ≥ 2.79 V against the 2N7002BK cold V_GS(th) max 2.35 V, so Q1 turns on without U5 (calc; the injection lifts `VDD_TMR` only to 0.27 V). Sim: 1.66–3.12 V on `ACC_G` 0.5 ms after the edge.
  - This is why R26 and R29 exist. Without them, `ACC_G` would sit at one diode above the unpowered `VDD_TMR` and Q1 might never start.
- **While counting:** `HOLD_G` ≥ 3.94 V at `VDD_TMR` 4.45 V, even with the 2N7002BK IGSS bound (10 µA, a 20 V figure) through R29, against the 2.35 V cold threshold (sim ≥ 4.51 V). D6 hot leakage 80 nA: 4 mV.
- **Supply (R30, D7, R31, C8; project lead 2026-11-05: U5 from `VOUT`; `design_calc.py` `u5_supply()`, `vz()`, `vdd_tmr()`):**
  - **D7 BZT52C5V1-E3-08** (Vishay 86342): V_Z 4.85–5.36 V at 5 mA, Z_Z ≤ 60 Ω at 5 mA, Z_ZK ≤ 480 Ω at 1 mA (knee test point), TC −3 to +4·10⁻⁴/K, I_R ≤ 100 nA at 0.8 V, 300 mW on FR-4 (R_thJA 420 K/W). Below 5 mA the lower bound falls along a power law through both resistance limits **(assumption: no I-V curve in the datasheet)**.
  - **Range:** `VDD_TMR` 4.45 V (9 V battery, 5 A through the harness and Q1: `VOUT` 8.58 V; U5 at its maxima; V_Z low, hot) to 5.71 V (16 V, U5 typical, V_Z high, hot). Nominal 5.1 V. Sim 4.51–5.70 V.
  - **R30 1.3 kΩ 1 % 1206:** keeps the zener ≥ 1 mA at 8.58 V with U5 at 538 µA (datasheet maxima at 5.71 V: IDD 171 µA at 85 °C + auto reset 221 µA + oscillator ≈ 146 µA; typical 156 µA) and R31's 0.57 mA. **98 mW at 16 V continuous** (1206: 250 mW, ≈ 205 mW at 85 °C **(assumption: linear derating from 70 °C)**); **0.35 W during the 26 V clamp pulse** (10/1000 µs): BOM checks the part's pulse curve.
  - **Zener current** 1.2–2.3 mA at 8.58 V, 6.8–7.8 mA at 16 V (46 mW, T_J rise 19 K), 14–15.5 mA at the 26 V clamp (97 mW). Leakage only matters below the knee (parked), where R31 dominates.
  - **R31 10 kΩ 1 % 0805:** parked bleed (section 2); 3.3 mW. **C8 1 µF 50 V X7R 0805** (GMC21X7R105K50NT): decoupling at pins 14 / 7; R30 · C8 = 1.3 ms smooths the 8/20 µs clamp peak.
  - **Power while on:** 31 / 67 / 107 / 139 mW at 9 / 12 / 14.4 / 16 V (2.4–8.7 mA from `VOUT`).
  - U5 works from 3 V (count stops below) and is rated 20 V abs max: `VDD_TMR` ≤ 6.5 V at every clamp level. A `+5V1` fault does not reach `VDD_TMR` (section 2).

| Parameter | Value | Source |
|---|---|---|
| Delay target | **≥ 25 s worst case after the last key-off** (project lead, 2026-11-05, revised from 45 s: enough for a cold Pi 5 boot to detect ACC off); nominal ≈ 30 s; the short corner inside the formula's 1–100 kHz | project lead |
| U5 | **CD4541BM96** (TI), SOIC-14; second source MC14541BDR2G (onsemi, pin-compatible **(assumption: onsemi PDF not obtained)**) | survey |
| R27 (RTC) | 39.2 kΩ 1 % 0805, ≤ 100 ppm/K | `design_calc.py` `counter_timer()` |
| C29 (CTC) | **10 nF 50 V C0G ±1 % 0805** (Murata GCM21B5C2E103FX0AL: 250 V rated, 0 ± 30 ppm/K, −55 to 125 °C, AEC-Q200; BOM staff review 2026-11-05, was KEMET C0805C103F5GACTU). C0G: no DC-bias loss, no aging, insulation not a factor at 39 kΩ | `counter_timer()` |
| R28 (RS) | 78.7 kΩ 1 % 0805 (≥ 10 kΩ, ≈ 2·RTC: SCHS085E) | datasheet |
| R26 (MR series) | 100 kΩ 0805 | section 3 |
| R29 (OUT → HOLD_G) | 47 kΩ 0805 | section 3 |
| R8 / R25 | 22 kΩ / 27 kΩ 1 % 0805 (`ACC_G` ratio 0.551) | section 2 |
| R30 | **1.3 kΩ 1 % 1206**: `VOUT` → `VDD_TMR` | `u5_supply()` |
| D7 | **BZT52C5V1-E3-08** (Vishay, SOD-123, 5.1 V zener): `VDD_TMR` → GND clamp | `u5_supply()` |
| R31 | **10 kΩ 1 % 0805**: `VDD_TMR` → GND bleed (parked) | section 2 |
| C8 | **1 µF 50 V X7R 0805** (GMC21X7R105K50NT) on `VDD_TMR` at U5 pins 14 / 7 | decoupling |
| D6 | **BAS116LT1G** (onsemi, SOT-23), ACC → `HOLD_G` OR diode: I_R ≤ 5 nA (25 °C), ≤ 80 nA (150 °C); pins 1 A, 2 NC, 3 K | existing part |
| Q5, Q6 | 2N7002BK (Nexperia, SOT-23, AEC-Q101): 60 V, V_GS ±20 V, V_GS(th) 1.1–2.1 V (25 °C), ≈ 2.35 V cold max / 0.75 V at 125 °C (graph), I_DSS ≤ 1 µA (25 °C) / 10 µA (150 °C) at 60 V, R_DS(on) ≤ 2 Ω at 5 V | Nexperia datasheet |
| Delay, calc (`counter_timer()`) | **nominal 29.5 s (1109 Hz); short 26.1 s (1253 Hz)** (k 2.104, C0G −1 % and −0.3 % drift, RTC −1 % and −1 % TCR); **long 32.5 s (1008 Hz)** (k 2.450, +1.3 %, +2.0 %) | `tools/design_calc.py` |
| Delay, sim | **short 26.16–26.20 s, nominal 29.56–29.61 s, long 32.56–32.61 s** (9 / 12 / 14.4 / 16 V, three loads, U5 from `VOUT`); restart and 50 ms blip identical; SW1 26.16–32.58 s; USB overload 26.17–33.04 s (ends at the count) | [reports/sim_delay_off_counter.md](../reports/sim_delay_off_counter.md) |

## 4. Power

| Parameter | Requirement / design |
|---|---|
| BATT range | 9–14.4 V operating (sim range), 16 V continuous max (TVS standoff); transients clamped by TVS1 |
| Current | **3.5 A at 12 V** on `BATT`/`VOUT` (Pi ~2.3 A + buck input ~1.4 A). Constant-power loads: **5.0 A at 9 V**: size the copper and the harness fuse for 5 A |
| TVS1, TVS2 | **SMBJ16A** (Bourns SMBJ): V_RWM 16 V, V_BR 17.8–19.7 V, I_R ≤ 1 µA, **V_C 26.0 V at 23.1 A** (10/1000 µs), 33.8 V at 115 A (8/20 µs). Lowest abs max downstream: buck VIN 30 V (reached at ≈ 70 A, as before), Q1 40 V, Q5 / Q6 V_DS 60 V, D4 / D5 100 V. FET gates on `ACC_G`: 14.1 V at the 26 V clamp, 18.4 V at 33.8 V (< 20 V). **TVS2 is needed** (DECISIONS): without it, ISO 7637-2 pulse 2a (≤ 112 V, 2 Ω) reaches `ACC_G` through D5 at 0.55× (≈ 60 V on the Q5 / Q6 gates, 20 V abs max), and pulse 1 (−150 V) exceeds D5's 100 V rating. Load dump and 24 V jump start: as before (project lead): accepted as a rare event that sacrifices the TVS and the fuse |
| U5 supply | From **`VOUT`** through R30 1.3 kΩ, D7 BZT52C5V1 clamp, R31 10 kΩ bleed, C8 1 µF on `VDD_TMR` (project lead, 2026-11-05: section 3 Supply): 4.45–5.71 V while counting, ≤ 6.5 V at the clamps (CD4541B 3–18 V operating, 20 V abs max). No LDO and no supply from `BATT`: U5 is powered only while Q1 is on. **Reverse battery:** `VOUT` at −1 to −3.5 V forward-biases D7 (≤ 2.2 mA through R30): `VDD_TMR` ≈ −0.7 V, past U5's −0.5 V abs max but current-limited, U5's own VSS–VDD diode sharing it **(assumption: survives until the fuse blows, as the other loads; residual risk accepted)** |
| Q1 | **SQD50P04-13L** (Vishay, DPAK, AEC-Q101): V_DS −40 V, V_GS ±20 V, V_GS(th) −1.5 to −2.5 V, **R_DS(on) ≤ 22 mΩ at −4.5 V** (×1.54 at 175 °C), RthJA 50 °C/W (1 in² copper). At 3.5 A hot: 0.42 W, TJ 106 °C at TA 85 °C; at 5 A (9 V): 0.85 W, TJ 127 °C |
| Q1 gate | R14 220 kΩ / R15 180 kΩ (ratio 0.55, 1 %), C30 100 nF G-S. Q5 pulls `DRV` to GND (R_DS(on) ≤ 2 Ω at 22–84 µA: < 0.2 mV).<br>**On at 9 V:** V_GS ≥ 4.91 V (calc, resistors 1 %) ≥ the −4.5 V R_DS(on) point; sim 4.81 V at the board's `BATT` under load.<br>**Abs max:** V_GS 14.4 V at the 26 V clamp (10/1000 µs: the gate follows it), 18.8 V at 33.8 V (< 20 V): no gate zener.<br>**Below the operating range (cranking):** V_GS ≈ 0.55·BATT: 3.3 / 3.8 / 4.4 V at 6 / 7 / 8 V. R_DS(on) is specified only from 4.5 V, so at a 6 V dip Q1 can limit the current and run linear for the length of the dip (typical curves). `HOLD_G` during a 6 V dip: U5 OUT is high (MR held by ACC, or counting if the car drops ACC while cranking) at `VDD_TMR` ≥ 3.98 V from a 6 V `VOUT` (calc); from `ACC_G` alone through D6 it would be only ≈ 2.1 V (`ACC_G` 2.9 V), near the 2N7002BK cold threshold **(assumption: bench, cranking dip)**<br>**Off:** one FET on `DRV`. Q5 I_DSS bound at 85 °C parked, 3.0 µA (log-interpolated between the 1 µA / 25 °C and 10 µA / 150 °C limits at 60 V), × R14 = **0.66 V** (sim 0.66 V) vs Q1 V_GS(th) min 1.26 V at 85 °C (−4 mV/K **assumption**). Two FETs in parallel on `DRV` would give 1.33 V: rejected (section 2).<br>**Turn-on:** no slew capacitor. R14 ∥ R15 = 99 kΩ drives the Miller plateau; C30 adds a ≈ 7 ms delay before it (calc at 9 V) and carries no current on the plateau, so the ramp and inrush figures of the 2026-11-04 design still bound it: calc 0.2–0.75 ms, ≤ 433 W at Qgd typ, 866 W at the half-Qgd bound, against the 1.2 kW derated 100 µs SOA line. Sim with C30: 10–20 A, **33–127 W peak**, `VOUT` 10–90 % in 1.0–3.3 ms (`BATT` dips through the harness, slowing the ramp).<br>**Turn-off:** C30 adds a ≈ 28 ms delay (calc, 16 V). Then the linear region: the Miller ramp (R14 alone charges C_gd; C30 idle) and the current tail through R14 · (C30 + Ciss): **≤ 19 ms** (calc: Qgd max, 1.5 V plateau). At 9 V and 5 A the rectangle bound (VB · I for that whole time) is 45 W against the 100 ms SOA line derated to 60 W at TC 85 °C. Sim (42 W load still on): **≤ 15 ms, ≤ 105 mJ, 20.5 W peak**. C30 makes the edge slower, not unsafe.<br>**Battery hot-plug (key off):** C30 against C_gd holds V_GS ≤ 0.34 V at a 16 V step, 0.54 V at 26 V (calc, C_gd 2.2 nF stand-in). Sim: `VOUT` ≤ 0.5 mV in every corner. **Without C30 the sim latched a full hold at 16 V with Q1 hot** (U8 starts, U5 auto-resets into a hold): the named failure mode for C30 (DECISIONS) |
| Reverse battery | **Not protected (project lead: fuse only, 7.5 A slow-blow inline).** TVS1 conducts forward and Q1's body diode conducts too, so `VOUT` and every load on it see about −1 V to −3.5 V until the fuse blows. D5 blocks a reversed ACC line from `ACC_S`. Residual risk accepted |
| Buck U8 | **TPS54336ADDA (kept)**, **5.074 V** nominal (worst 4.915–5.238 V: ref ±1.5 %, R16 / R17 1 %; ≥ 4.815 V at the port with a 0.1 V board + connector drop budget, **assumption**) / 3 A, fsw 340 kHz. Input **C15 + C31 2 × 10 µF** 50 V X7R 1206 + C17 100 nF (SLVSCD5D 8.2.2.5): eq 17 **227 mV p-p** at 3 A (282 mV at fsw min; 50 % DC-bias retention at 9–16 V, **assumption**: Cal-Chip publishes no curve), I_rms 1.5 A total (eq 18). **L1 15 µH** SRP1038A-150M: L_min 11.3 µH (eq 19, K_IND 0.3 at 16 V); **K_IND 0.23 at 16 V** (0.35 with L −20 % and fsw min); I_rms 3.01 A, I_pk 3.42 A (eq 20 / 21); I_sat 10 A > the 6.5 A current-limit max; DCR 40 / 45 mΩ typ / max: 0.36 / 0.41 W. Output **C22–C24, C32: 4 × 47 µF** 10 V X7R 1210: eq 22 (1.5 A step, 5 %) needs 34.8 µF, eq 23 (30 mV) 8.3 µF; effective 47 / 64 / 113 µF at 25 / 34 / 60 % retention (**assumption**, reports/buck_design.md): **margin ≥ 35 %** at fsw typ (eq 22 at fsw min 272 kHz: 43.5 µF, 8 %; the loop-based step ΔI / (2π fc Co) is ≤ 155 mV vs 254 mV in every corner, **assumption**: that is the transient criterion, TODO). Type 2B compensation (**R18 7.32 kΩ**, C20 15 nF; no C21): eq 10 / 12 at fc 30 kHz with 64 µF; loop fc **16–42 kHz, PM ≥ 45.8°** over retention 25–60 %, 0.1–3 A, sampling Q 0.3–1, fsw 272–408 kHz (worst: 25 %, 0.1 A, Q 0.3, fsw min; ≥ 51° at fsw typ), with the datasheet error-amplifier model (Roea 3.07 MΩ, Coea 20.7 pF: SLVSCD5D 7.3.15) (`design_calc.py` `buck()`). EN floating (internal pull-up: SLVSCD5D pin table and 7.3.5; VIN UVLO 4.0–4.5 V rising, 180 mV hysteresis: 6.5); SS C19 10 nF (3.5 ms). EN floating: a back-fed `VOUT` (Pi powered elsewhere, ≈ 4.3 V through its regulator's body diode, **assumption**) may sit inside the 4.0–4.5 V UVLO band and let U8 run in dropout (TODO). **Thermal at 3 A, TA 85 °C:** 1.0 W typ → TJ ≈ 128 °C (RthJA 42.1 °C/W, JEDEC; 2-layer worse), up to the 160 °C shutdown with max R_DS (hiccups, doesn't fail). **TPS54302 rejected:** TJ ≈ 152 °C at 3 A / 132 °C at 2.4 A with its EVM RthJA 57.2 °C/W (224 / 182 °C JEDEC), above its 125 °C recommended maximum (DECISIONS). Values and footprint: section 7 and `reports/buck_design.md` |
| USB ports | J2 stacked USB-A (Molex 0484060001), both units: VBUS = `+5V1`; D+ shorted to D− per port; SuperSpeed pins NC; GND, DRAIN and shield (SH) to GND. **No bulk electrolytics:** the 4 × 47 µF output ceramics sit between L1 and J2. A phone plugged in (USB device input ≤ 10 µF) steps VBUS by ≤ 0.9 V for microseconds at the lowest Cout retention (charge sharing; the loop restores it); BC1.2 charging is not hurt by it **(assumption: bench)**. No polyfuse (the buck's current limit and hiccup protect a shorted port). Total 3 A for both ports |
| Decoupling | C8 1 µF at U5 pins 14 / 7 (`VDD_TMR`); C15 + C31 10 µF and C17 100 nF at U8 VIN. No `BATT` or `VOUT` bulk: Q1 ties `BATT` to `VOUT` while on, TVS1 clamps any harness ring on both |
| LED | D3 **Stanley VFR1105W-6C9-TR** (red 626 nm, 3216 / 1206 dome lens, 1.85 mm tall; "High Reliability V-Series" for car indicators) + R3 **5.1 kΩ** from `VOUT`: 1.37 / 1.96 / 2.43 / 2.75 mA at 9 / 12 / 14.4 / 16 V (calc with V_F 2.0 V; this LED's V_F is 1.9 V typ / 2.4 V max at 20 mA, so a few % more current: R3 kept). DC rating 30 mA, derated above 75 °C (datasheet chart). **Temperature: −40 to +100 °C operating** (Stanley 1105W V-Series datasheet; BOM staff review 2026-11-05, was LTST-C150KRKT, −30 to +85 °C). Much brighter than the Lite-On part (Digi-Key 985 mcd, series sheet 330–1 200 mcd, vs 54 mcd at 20 mA): ≈ 50–100 mcd at 2 mA (rank window: DECISIONS) **(assumption: luminous intensity ∝ I_F)**. If too bright, raise R3 (lead) |

## 5. Board

| Parameter | Value |
|---|---|
| Layers / thickness | 2 layers, 1.6 mm |
| Fab (project lead, 2026-11-05) | **OSH Park 2-layer**: 1.6 mm FR4 175Tg (core 1.524 mm, Er 4.5), 1 oz (0.0356 mm) both sides, ENIG, purple mask (0.0152 mm). Floors: copper to edge ≥ 0.381 mm (board rule 0.4 mm); trace / space 0.1524 mm; annular ring 0.127 mm; drill 0.254 mm; hole to hole 0.127 mm; mask web 0.1016 mm, mask alignment 0.0762 mm; silk line 0.127 mm (0.0762 mm for text and short lines); slot 0.508 mm; interior milling 1.01 mm (concave corners ≥ r 0.505 mm), outline milling 1.72 mm; no filled or plated via-in-pad (open vias OK), tenting allowed. In `.kicad_pro` / `.kicad_dru` / the stackup (`tools/post_route/12`) |
| Outline | HAT 65 × 56 mm (existing Edge.Cuts), x 127.000–192.024, y 58.420–114.300, plus a **right-edge notch (project lead, 2026-11-05)** for the CAN FD HAT's back header below: x 185.166–192.024, **y 85.000–102.000** (top edge just below J2's courtyard, y 84.55: the board stays under J2; `tools/post_route/13`, `14`); inner fillets r 1.524 mm, mouth corners r 0.762 mm. Necks to the MH2 / MH4 corner tabs ≥ 5 mm (measured 19.17 top / 5.02 bottom mm) |
| Mounting holes | 4 × M2.5 (MountingHole_2.7mm_M2.5) on a 58 × 49 mm rectangle (existing MH1–MH4) |
| Keep-outs (drawn by the project lead: keep) | GPIO HEADER, WAVESHARE IO, PoE, BACK HEADER KEEPOUT: drawings on Dwgs.User; only PoE is a rule area (B.Cu, no footprints). The placement phase treats all four as no-parts areas |
| Fixed positions (project lead) | J1, J2, J4, J5 stay where the lead placed them (board outline, holes and keep-outs too). **J1, J4, J5 are rotated 180° in place at placement (project lead, 2026-11-05)** so their wire entries face outward; the pin order along each row follows the rotation |
| Power copper | `BATT`, `VOUT` and the J1/J4 GND returns sized for ≥ 5 A (9 V case, section 4): **≥ 3 mm wide at 1 oz (35 µm) outer copper** (IPC-2221, about +10 °C at 5 A) or pours; GND pour both layers with stitching. Q1 tab: ≥ 1 in² of copper on `VOUT` where it fits (RthJA basis) |
| Buck layout | SLVSCD5D 10.1 / fig. 55 (2026-11-06): **power block** U8 + C17 (closest) + C15 to the right of VIN/GND, `U8_PH` by vias at pin 3 to a short wide B.Cu trace and back up at L1 pin 1; C31 below C15 on the `VOUT` pour (GND by vias); C18 at BOOT. U8 sits below J5 so the left side is free: **R16 / R17 at pin 5** (`U8_FB` node 5.5 mm, was 18.6 mm; the long run is the low-impedance `+5V1` sense line from the Cout end along the top edge), **R18 / C20 at pin 6 and C19 at pin 8**, all F.Cu, on the side away from `U8_PH`. **Analog ground:** two separate F.Cu traces: R17 to the top end of the PowerPAD, C19 + C20 (joined) to its bottom end. They touch the pour only on pad 9 (U8's ground reference), so no loop; strictly two landing points on the one pad, not the single junction of 10.1 (accepted: µV-level drop across the pad); a keep-out (no pour, F.Cu) around them keeps the GND pour off; B.Cu GND pour under them. GND pour under U8 on both layers. C22–C24, C32 in a row above L1 |
| Timer layout | U5 and its RC parts (R27, R28, C29) close together, the `U5_TJ` / `U5_RS` node short and away from `U8_PH` / L1 (a high-impedance node at 1.1 kHz: switching noise coupling adds or removes counts). C8 at U5 pins 14 / 7, D7 and R31 next to them, R30 between `VOUT` and that group. C30 at Q1 (G-S). The timing no longer depends on board leakage (C0G capacitor, 39–79 kΩ) |
| Parts rule | Hand solder: HandSolder passives, no QFN/BGA, exposed pads only with a bottom solder via. **0805 HandSolder** for small-signal passives; **1206 HandSolder** where the part carries power-path current, takes pulse power, or needs the case for its capacitance at its DC bias: C15, C31 (buck Cin), R30 (U5 supply: TVS clamp pulse), R21 (J5 fault current), D3 (LED part). **1210 HandSolder** for C22–C24, C32 (buck Cout: no 47 µF 10 V X7R in 1206, project lead 2026-11-05). 0805 resistors: ≥ 0.125 W rating (BOM phase). **Hand assembly (project lead, 2026-11-05): nothing smaller than 0805; keep parts spaced out where possible** |
| J2 | Overhangs the right board edge **on purpose (project lead, 2026-11-04)**. The placement phase may still pull it onto the board if there is space |
| Mechanical stack | **Project lead (2026-11-04):** this HAT sits on standoffs above a CAN HAT on the Pi 5, so a J2 overhang clears the Pi's USB / Ethernet jacks (about 16 mm tall) |

## 6. Parts

One row per part (MPN); Ref lists the refs of one board. Every MPN and Digi-Key PN is final (phase 6, 2026-11-05; checked by `pdm run dk-check`). Status: `order` unless noted. **41 parts per board** (2026-11-05 counter timer; U5 from `VOUT`: R30 and R31 added, D7 now the zener; 2026-11-06 buck fixes: C31, C32 added) plus J1, J2, J4, J5, SW1 (and MH1–MH4, no part).

| Ref | Function | Value | Package | Mount | Spares | Manufacturer | MPN | Digi-Key PN | Datasheet | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| J1 | Input terminal GND/ACC/BATT | 3-pos 3.81 mm, 10 A (IEC; 12 A max load), AWG 16–30 (UL) | Phoenix MKDS 1/3-3,81 | THT | +1 | Phoenix Contact | 1727023 | 277-1948-ND | ref/datasheets/Phoenix_MKDS1-3-3.81_1727023.pdf | order |
| J4, J5 | J4: Pi 12 V output VOUT/GND; J5: ACC status to Pi GPIO (ACC_N/GND) | 2-pos 3.81 mm, 10 A (IEC; 12 A max load), AWG 16–30 (UL) | Phoenix MKDS 1/2-3,81 | THT | +1 | Phoenix Contact | 1727010 | 277-1947-ND | ref/datasheets/Phoenix_MKDS1-2-3.81_1727010.pdf | order |
| J2 | USB-A charging ports, stacked | USB3 A stacked, 1.8 A per VBUS contact, −20 to 85 °C | Molex 48406-0001 | THT | +1 | Molex | 0484060001 | 0484060001-ND |  | order |
| SW1 | Force-on switch (acts like the key) | SPDT slide, 24 V / 25 mA switching | Nidec CAS-120A (J-hook, taped) | SMD | +2 | Nidec Components | CAS-120TA | CAS120JCT-ND | ref/datasheets/Nidec_CAS.pdf | order |
| Q1 | High-side P-FET | 40 V, 22 mΩ at −4.5 V, AEC-Q101 | DPAK (TO-252) | SMD | +2 | Vishay Siliconix | SQD50P04-13L_GE3 | SQD50P04-13L_GE3CT-ND | ref/datasheets/Vishay_SQD50P04-13L.pdf | order |
| U5 | Delay-off timer: RC oscillator + 16-stage counter, on VDD_TMR (VOUT through R30, D7 clamp) | CD4541B, 3–18 V, −55 to 125 °C | SOIC-14 | SMD | +2 | Texas Instruments | CD4541BM96 | 296-3536-1-ND | ref/datasheets/TI_CD4541B.pdf | order |
| Q5, Q6 | Q5: hold FET on DRV (Q1 gate network); Q6: ACC status open drain to J5 | 2N7002BK, 60 V, 350 mA, ESD-protected gate | SOT-23 | SMD | yes | Nexperia | 2N7002BK,215 | 1727-4789-1-ND | ref/datasheets/Nexperia_2N7002BK.pdf | order |
| U8 | 5.1 V buck for USB | TPS54336A (tube: the DDAR cut tape has 0 stock) | SO PowerPAD-8 (DDA), project hand-solder footprint | SMD (tube) | +2 | Texas Instruments | TPS54336ADDA | 296-41978-5-ND | ref/datasheets/TI_TPS54336A_SLVSCD5D.pdf | order |
| L1 | Buck inductor | 15 µH ±20 %, I_sat 10 A, I_rms 6.25 A, 45 mΩ max | Bourns SRP1038A (10 × 11 mm) | SMD | +1 | Bourns | SRP1038A-150M | SRP1038A-150MCT-ND | ref/datasheets/Bourns_SRP1038A.pdf | order |
| TVS1, TVS2 | BATT and ACC TVS | SMBJ16A | SMB | SMD | yes | Bourns | SMBJ16A | SMBJ16ABCT-ND | ref/datasheets/Bourns_SMBJ.pdf | order |
| D4, D5 | D5: ACC_IN → ACC_S isolation (keeps BATT/SW1 off the car's ACC line); D4: SW1 → ACC_S (keeps ACC off BATT when BATT is dead) | 1N4148W, 75 V (100 V repetitive peak) | SOD-123 | SMD | yes | Vishay | 1N4148W-E3-08 | 1N4148W-E3-08CT-ND | ref/datasheets/Vishay_1N4148W.pdf | order |
| D6 | ACC_G → HOLD_G OR diode (Q1 on before +5V1 exists), low leakage | BAS116L, 75 V, ≤ 80 nA at 150 °C | SOT-23 | SMD | yes | onsemi | BAS116LT1G | BAS116LT1GOSCT-ND | ref/datasheets/onsemi_BAS116LT1.pdf | order |
| D7 | U5 supply clamp: VDD_TMR → GND | BZT52C5V1 zener, 4.85–5.36 V at 5 mA, 300 mW on FR-4 | SOD-123 | SMD | yes | Vishay | BZT52C5V1-E3-08 | BZT52C5V1-E3-08CT-ND | ref/datasheets/Vishay_BZT52.pdf | order |
| D3 | VOUT-on LED (from VOUT), −40 to 100 °C | red | 1206 | SMD | yes | Stanley Electric | VFR1105W-6C9-TR | 404-1321-1-ND | ref/datasheets/Stanley_1105W_V-series.pdf | order |
| R3 | LED series (D3 to GND) | 5.1 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW08055K10FKEA | 541-5.10KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R8 | ACC_G divider top (ACC_S) | 22 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW080522K0FKEA | 541-22.0KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R25 | ACC_G divider bottom (also the ACC_S pull-down) | 27 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW080527K0FKEA | 541-27.0KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R26 | U5 MR series (clamp current, start-up) | 100 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW0805100KFKEA | 541-100KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R27 | U5 RTC (oscillator timing) | 39.2 kΩ 1 % 0.125 W, ≤ 100 ppm/K | 0805 | SMD | yes | Vishay Dale | CRCW080539K2FKEA | 541-39.2KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R28 | U5 RS (oscillator input) | 78.7 kΩ 1 % 0.125 W, ≤ 100 ppm/K | 0805 | SMD | yes | Vishay Dale | CRCW080578K7FKEA | 541-78.7KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R29 | U5 OUT → HOLD_G | 47 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW080547K0FKEA | 541-47.0KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R30 | U5 supply series: VOUT → VDD_TMR (pulse power at the TVS clamp) | 1.3 kΩ 1 % 0.25 W | 1206 | SMD | yes | Vishay Dale | CRCW12061K30FKEA | 541-1.30KFCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R17 | Buck FB divider bottom | 13.7 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW080513K7FKEA | 541-13.7KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R31 | VDD_TMR bleed to GND (holds U5 unpowered against Q1 off-state leakage) | 10.0 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW080510K0FKEA | 541-10.0KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R14 | Q1 gate pull-up (G-S) | 220 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW0805220KFKEA | 541-220KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R15 | Q1 gate to DRV (Q5) | 180 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW0805180KFKEA | 541-180KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R16 | Buck FB divider top | 73.2 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW080573K2FKEA | 541-73.2KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R18 | Buck COMP | 7.32 kΩ 1 % 0.125 W | 0805 | SMD | yes | Vishay Dale | CRCW08057K32FKEA | 541-7.32KCCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| R21 | J5 series (Q6 drain to the Pi cable: fault current) | 1.5 kΩ 1 % 0.25 W | 1206 | SMD | yes | Vishay Dale | CRCW12061K50FKEA | 541-1.50KFCT-ND | ref/datasheets/Vishay_CRCW_e3.pdf | order |
| C29 | U5 CTC timing capacitor (≥ 50 V needed), AEC-Q200 | 10 nF 250 V C0G ±1 % | 0805 | SMD | yes | Murata Electronics | GCM21B5C2E103FX0AL | 490-GCM21B5C2E103FX0ALCT-ND | ref/datasheets/Murata_GCM21B5C2E103FX0A.pdf | order |
| C17, C18, C30 | C17: buck VIN high-frequency bypass; C18: buck BOOT; C30: Q1 gate-source (battery hot-plug) | 100 nF 50 V X7R ±10 % | 0805 | SMD | yes | KEMET | C0805C104K5RACTU | 399-C0805C104K5RACTUCT-ND | ref/datasheets/KEMET_C1002_X7R.pdf | order |
| C19 | Buck soft start | 10 nF 50 V X7R ±10 % | 0805 | SMD | yes | KEMET | C0805C103K5RACTU | 399-C0805C103K5RACTUCT-ND | ref/datasheets/KEMET_C1002_X7R.pdf | order |
| C20 | Buck COMP | 15 nF 50 V X7R ±10 % | 0805 | SMD | yes | KEMET | C0805C153K5RACTU | 399-C0805C153K5RACTUCT-ND | ref/datasheets/KEMET_C1002_X7R.pdf | order |
| C8 | U5 decoupling on VDD_TMR | 1 µF 50 V X7R ±10 % | 0805 | SMD | yes | Cal-Chip Electronics | GMC21X7R105K50NT | 4713-GMC21X7R105K50NTCT-ND | ref/datasheets/CalChip_GMC_series.pdf | order |
| C15, C31 | Buck input | 10 µF 50 V X7R ±10 % | 1206 | SMD | yes | Cal-Chip Electronics | GMC31X7R106K50NT | 4713-GMC31X7R106K50NTCT-ND | ref/datasheets/CalChip_GMC_series.pdf | order |
| C22, C23, C24, C32 | Buck output, 4 × 47 µF: ≥ 8.7 µF each effective at 5.07 V for eq 22; the only +5V1 capacitance (no USB bulk) | 47 µF 10 V X7R ±10 % | 1210 | SMD | yes | Cal-Chip Electronics | GMC32X7R476K10NT | 4713-GMC32X7R476K10NTCT-ND | ref/datasheets/CalChip_GMC_series.pdf | order |

**BOM notes (phase 6, 2026-11-05; agent A18):**

- **Hand assembly, 2 boards, Digi-Key** (`pdm run dk-check`, `pdm run dk-bom` → [bom/PIPWR_BOM.md](../bom/PIPWR_BOM.md), `bom/PIPWR_BOM_digikey.csv`; hand-assembly order: [bom/assembly_checklist.md](../bom/assembly_checklist.md)). SMD rows order the **cut-tape** packaging; U8 the tube (`SMD (tube)`: TPS54336ADDAR's cut tape has 0 stock); THT rows bulk / tray.
- **Spares** (column `Spares`, `tools/digikey_lookup.py`): `yes` = 10 % of 2 boards rounded up, **at least 5** (cheap passives and small semiconductors); `+N` = N (ICs, Q1, L1, SW1, connectors).
- **Resistors:** Vishay Dale CRCW e3 thick film, all 1 % / ±100 ppm/K / AEC-Q200 (non-1 % SPEC 7 values bought as 1 %: same price); 0805 = 0.125 W, 1206 = 0.25 W. **R30 pulse:** the CRCW1206 single-pulse limit at 1 ms is ≈ 8 W (datasheet "Single Pulse" chart), against the 0.35 W of the 10/1000 µs clamp pulse (section 4). **R21 (J5 miswired to 12 V, Q6 on):** 0.17 W at 16 V continuous against 0.21 W for a 1206 at 85 °C (rated at 70 °C, linear to 0 at the 155 °C film limit: datasheet), 0.45 W for the 26 V clamp pulse (≪ the single-pulse limit): a fault case, kept (BOM staff review 2026-11-05).
- **Capacitors:** Murata GCM 0805 for C29 (C0G ±1 %, 250 V, AEC-Q200: BOM staff review 2026-11-05, $0.68 vs $3.75 for the KEMET C0805C103F5GACTU it replaces, same dielectric and tolerance), KEMET 0805 X7R ±10 % for C17–C20, C30, Cal-Chip GMC X7R (C8, C15, C31, C22–C24, C32). Every capacitor is rated ≥ 50 V except C22–C24, C32 (10 V on `+5V1`).
- **Datasheets:** all in `ref/datasheets/` except J2 (Molex product-page URL in the schematic field; the PDF download timed out, and again on 2026-11-05 evening with `curl.exe` and browser headers: connection reset / timeout on both the product page and the sales-drawing URL). Every PDF's text names its part or its series ordering code (BOM staff review 2026-11-05). The Datasheet column is checked against the schematic by `tools/check_netlist.py` (`${KIPRJMOD}` paths only), so J2's cell is empty.
- **Schematic fields** Manufacturer / MPN / Digi-Key PN / Description / Datasheet: `tools/post_sch/14_bom_fields.py` (its `PARTS` table = this table as of phase 6; it checks the Digi-Key PN, Manufacturer and MPN columns against it); D3 and C29 since `tools/post_sch/15_bom_review.py` (BOM staff review: D3 also its Value).

## 7. Netlist

**The schematic phase implements this table verbatim.**

- **Pins:** numbers are the footprint pad numbers; KiCad `Device:D`, `D_Zener` and `LED` use 1 = K, 2 = A.
- **Q1 symbol:** `Transistor_FET:Q_PMOS_GDS` (1 G, 2 D, 3 S, matching `TO-252-2`, pad 2 = tab), as in the current schematic.
- **U5 symbol:** KiCad 10 `Timer:CD4541BM` (extends `CD4541BE`; footprint `Package_SO:SOIC-14_3.9x8.7mm_P1.27mm`). Its pins match SCHS085E (top view): 1 RTC, 2 CTC, 3 RS, 4 NC, 5 AR, 6 MR, 7 VSS, 8 OUTPUT, 9 Q/Q̅ SELECT, 10 MODE, 11 NC, 12 A, 13 B, 14 VDD. Value CD4541BM96. Draw C8 next to pins 14 / 7. The library types pins 1 RTC and 2 CTC as inputs although they are the oscillator drivers: their nets carry only passive pins (R27, C29), which KiCad's ERC accepts (`tools/post_sch/08`: ERC 0 errors / 0 warnings with the stock symbol); don't change the library pin types. Pins 9, 12, 13, 14 sit on `VDD_TMR` (R30 from `VOUT`, D7 clamp, R31, C8), not `+5V1` or `VOUT`. Draw R30, D7, R31 and C8 as one block on U5's VDD.
- **Q5, Q6 symbol:** KiCad 10 `Transistor_FET:2N7002` (extends `Q_NMOS_GSD`: 1 G, 2 S, 3 D), matching the 2N7002BK pinout (1 G, 2 S, 3 D, Nexperia table 2) and the `SOT-23_Handsoldering` pads 1–3 (as the 2026-11-04 design's Q2/Q4); value 2N7002BK.
- **D6 symbol:** a SOT-23 diode with 1 A, 2 NC, 3 K: KiCad 10 `Diode:BAS21` (extends `BAS16W`) with value BAS116LT1G and the `SOT-23_Handsoldering` footprint, as in the current schematic.
- **TVS1/TVS2:** unidirectional symbol (`Device:D_Zener`-style, 1 K / 2 A). `Device:D_TVS` is bidirectional.
- **J2:** `USB3_A_Stacked` from the KiCad 10 library (shield pin `SH`, 4 footprint pads), as in the current schematic.
- **Footprints:** `R_1206` = `Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder`; `C_1206` = `Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder`; `R_0805` = `Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder`; `C_0805` = `Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder`; `C_1210` = `Capacitor_SMD:C_1210_3225Metric_Pad1.33x2.70mm_HandSolder`. Project library `pipwr` = `lib/pi_power_board.pretty` (footprints U8, L1) and `lib/pi_power_board.kicad_sym` (symbol `pipwr:LM2903`, no longer used: U1 removed).
- **Connectors unchanged** (footprints and pin → net order exactly as before; J1, J2, J4, J5 positions fixed by the lead): J1, J2, J4, J5, SW1 (SW1 pin 1 on `SW1_C` to D4's anode; D4 cathode on `ACC_S`).
- **Kept parts, same ref, symbol and footprint, same nets:** Q1, U8, L1, TVS1, TVS2, D3, D4, D5, R3, R14, R15, R16, R17, R18, R21, C15, C17, C18, C19, C20 (R15 pin 2 stays on `DRV`, R21 pin 1 on `STAT_O`: their drivers change, not their nets).
- **Kept parts with new values or nets:**
  - R8: 47 kΩ → 22 kΩ; pin 2 GND → `ACC_G`.
  - D6: pin 1 `D6_A` → `ACC_G`; pin 3 `C5_T` → `HOLD_G`.
  - C8: pin 1 `BATT` → `VDD_TMR` (U5 decoupling); 100 nF 0805 → 10 µF 50 V 1206 (08) → **1 µF 50 V 0805** (09).
  - C22, C23, C24: 47 µF 10 V X5R 1206 → X7R 1210 (same nets).
- **New:** U5 (CD4541BM96), Q5, Q6 (2N7002BK), R25, R26, R27, R28, R29, C29, C30, D7 (08: BAT43W-E3-08; 09: the zener). Refs unused on the current schematic and board. Q2 / Q4, U2–U4 were 2026-11-04 refs, so they are not reused.
- **U5 from `VOUT` (`tools/post_sch/09_u5_vout_supply.py`, project lead 2026-11-05):** D7 keeps its ref, symbol uuid and `Diode_SMD:D_SOD-123` footprint and becomes the BZT52C5V1 zener: symbol `Device:D_Zener` (1 K, 2 A), value BZT52C5V1, pin 2 `+5V1` → GND. C8 10 µF 1206 → 1 µF 0805. **New:** R30 (`R_1206`, `VOUT` → `VDD_TMR`), R31 (`R_0805`, `VDD_TMR` → GND); refs unused on the schematic and board. `Diode:BAT43W-V` leaves lib_symbols.
- **Removed (by `tools/post_sch/08_cd4541_timer.py`):** U1 (LM2903BIDR), R4, R5, R9, R23, R24, C5, C27, C28. Their nets go too: `REF`, `C5_T`, `D6_A`. `DRV` and `STAT_O` stay. No pin, net or label of a removed part may remain. The project symbol `pipwr:LM2903` becomes unused (keep the library file: history).

| Ref | Value | Footprint | Pins → nets |
|---|---|---|---|
| J1 | Screw terminal 3-pos | TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1-3-3.81_1x03_P3.81mm_Horizontal | 1 → GND; 2 → ACC_IN; 3 → BATT |
| J4 | Screw terminal 2-pos | TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1-2-3.81_1x02_P3.81mm_Horizontal | 1 → VOUT; 2 → GND |
| J5 | Screw terminal 2-pos, value "ACC_N GND" | (as J4) | 1 → GND; 2 → ACC_N. J4 and J5 are the same block with GND on opposite pins: silkscreen each pin name (12 V on a Pi GPIO destroys it). The value reads "ACC_N GND": the pin order after the 180° rotation (project lead, 2026-11-05) |
| J2 (A, B) | USB3_A_Stacked | Connector_USB:USB3_A_Molex_48406-0001_Horizontal_Stacked | 1 VBUS1 → +5V1; 2 D1− → USB1_D; 3 D1+ → USB1_D; 4 GND1 → GND; 7 DRAIN1 → GND; 10 VBUS2 → +5V1; 11 D2− → USB2_D; 12 D2+ → USB2_D; 13 GND2 → GND; 16 DRAIN2 → GND; SH → GND; 5, 6, 8, 9, 14, 15, 17, 18 → no connect (SuperSpeed pairs, unused) |
| SW1 | SW_Nidec_CAS-120A1 | Button_Switch_SMD:Nidec_Copal_CAS-120A | 2 (B, common) → BATT; 1 (C) → SW1_C; 3 (A) → no connect (unused throw). Pad 2 is the common (Nidec CAS catalogue: terminal ② = "C", the catalogue's name for common; the KiCad symbol calls it B) |
| TVS1 | SMBJ16A | Diode_SMD:D_SMB_Handsoldering | 1 K → BATT; 2 A → GND (at J1) |
| TVS2 | SMBJ16A | Diode_SMD:D_SMB_Handsoldering | 1 K → ACC_IN; 2 A → GND (at J1) |
| D5 | 1N4148W | Diode_SMD:D_SOD-123 | 1 K → ACC_S; 2 A → ACC_IN |
| D4 | 1N4148W | Diode_SMD:D_SOD-123 | 1 K → ACC_S; 2 A → SW1_C |
| R8 | 22 kΩ 1 % | R_0805 | 1 → ACC_S; 2 → ACC_G |
| R25 | 27 kΩ 1 % | R_0805 | 1 → ACC_G; 2 → GND |
| Q6 | 2N7002BK | Package_TO_SOT_SMD:SOT-23_Handsoldering | 1 G → ACC_G; 2 S → GND; 3 D → STAT_O |
| R21 | 1.5 kΩ | R_1206 | 1 → STAT_O; 2 → ACC_N (place near J5) |
| D6 | BAS116LT1G | Package_TO_SOT_SMD:SOT-23_Handsoldering | 1 A → ACC_G; 2 NC → no connect (not connected inside, case 318 style 8); 3 K → HOLD_G |
| R26 | 100 kΩ | R_0805 | 1 → ACC_G; 2 → U5_MR |
| U5 | CD4541BM96 | Package_SO:SOIC-14_3.9x8.7mm_P1.27mm | 1 RTC → U5_RTC; 2 CTC → U5_CTC; 3 RS → U5_RS; 4 NC → no connect (internal NC, SCHS085E); 5 AR → GND (auto reset on); 6 MR → U5_MR; 7 VSS → GND; 8 OUTPUT → U5_OUT; 9 Q/Q̅ SELECT → VDD_TMR (output high after reset); 10 MODE → GND (single transition); 11 NC → no connect (internal NC); 12 A → VDD_TMR; 13 B → VDD_TMR (A = B = 1: 2^16 tap); 14 VDD → VDD_TMR |
| C8 | 1 µF 50 V | C_0805 | 1 → VDD_TMR; 2 → GND (at U5 pins 14 / 7, shortest loop) |
| D7 | BZT52C5V1 | Diode_SMD:D_SOD-123 | 1 K → VDD_TMR; 2 A → GND (next to U5) |
| R30 | 1.3 kΩ 1 % | R_1206 | 1 → VOUT; 2 → VDD_TMR |
| R31 | 10 kΩ 1 % | R_0805 | 1 → VDD_TMR; 2 → GND |
| R27 | 39.2 kΩ 1 % | R_0805 | 1 → U5_RTC; 2 → U5_TJ |
| C29 | 10 nF 50 V C0G ±1 % | C_0805 | 1 → U5_CTC; 2 → U5_TJ |
| R28 | 78.7 kΩ 1 % | R_0805 | 1 → U5_RS; 2 → U5_TJ |
| R29 | 47 kΩ | R_0805 | 1 → U5_OUT; 2 → HOLD_G |
| Q5 | 2N7002BK | Package_TO_SOT_SMD:SOT-23_Handsoldering | 1 G → HOLD_G; 2 S → GND; 3 D → DRV |
| R14 | 220 kΩ 1 % | R_0805 | 1 → BATT; 2 → Q1_G |
| C30 | 100 nF 50 V | C_0805 | 1 → BATT; 2 → Q1_G (at Q1, G-S) |
| R15 | 180 kΩ 1 % | R_0805 | 1 → Q1_G; 2 → DRV |
| Q1 | SQD50P04-13L | Package_TO_SOT_SMD:TO-252-2 | 1 G → Q1_G; 2 D (tab) → VOUT; 3 S → BATT |
| D3 | VFR1105W | LED_SMD:LED_1206_3216Metric_Pad1.42x1.75mm_HandSolder | 1 K → D3_K; 2 A → VOUT |
| R3 | 5.1 kΩ | R_0805 | 1 → D3_K; 2 → GND |
| U8 | TPS54336ADDA | pipwr:TI_DDA_PowerPAD-8_HandSolder | 1 BOOT → U8_BOOT; 2 VIN → VOUT; 3 PH → U8_PH; 4 GND → GND; 5 VSENSE → U8_FB; 6 COMP → U8_COMP; 7 EN → no connect (float = enable, internal pull-up: SLVSCD5D pin table, 7.3.5); 8 SS → U8_SS; 9 PowerPAD → GND |
| C15 | 10 µF 50 V | C_1206 | 1 → VOUT; 2 → GND (at U8 pins 2/4) |
| C31 | 10 µF 50 V | C_1206 | 1 → VOUT; 2 → GND (next to C15) |
| C17 | 100 nF 50 V | C_0805 | 1 → VOUT; 2 → GND (closest to U8 pins 2/4) |
| C18 | 100 nF 50 V | C_0805 | 1 → U8_BOOT; 2 → U8_PH |
| L1 | SRP1038A-150M | pipwr:L_Bourns_SRP1038A | 1 → U8_PH; 2 → +5V1 |
| C22 | 47 µF 10 V X7R | C_1210 | 1 → +5V1; 2 → GND |
| C23 | 47 µF 10 V X7R | C_1210 | 1 → +5V1; 2 → GND |
| C24 | 47 µF 10 V X7R | C_1210 | 1 → +5V1; 2 → GND (nearest J2) |
| C32 | 47 µF 10 V X7R | C_1210 | 1 → +5V1; 2 → GND |
| R16 | 73.2 kΩ 1 % | R_0805 | 1 → +5V1; 2 → U8_FB |
| R17 | 13.7 kΩ 1 % | R_0805 | 1 → U8_FB; 2 → GND |
| R18 | 7.32 kΩ 1 % | R_0805 | 1 → U8_COMP; 2 → U8_CRC |
| C20 | 15 nF 50 V | C_0805 | 1 → U8_CRC; 2 → GND |
| C19 | 10 nF 50 V | C_0805 | 1 → U8_SS; 2 → GND |

**Project footprints** (dimensions in `reports/buck_design.md`; unchanged):

- `pipwr:TI_DDA_PowerPAD-8_HandSolder`: TI DDA0008B land.
  - Pins 0.60 × 2.00 mm, extended 0.45 mm outward.
  - Pad 9: 2.95 × 4.90 mm on both layers, mask 2.71 × 3.40 mm on top and fully open on the bottom.
  - **Centre plated hole, drill 1.0 mm** (solder fed from the bottom; keep).
  - Thermal vias, drill 0.3 mm / pad 0.6 mm, pad 9 net: 4 at (±0.65, ±1.30) mm inside the mask opening, plus 6 at (0, ±2.05) and (±0.90, ±2.05) mm under the solder-masked ends of pad 9 (tented on top).
  - Bottom pad 9: 4.0 × 6.0 mm. Top pad 9 joined to pin 4 and to the top GND pour at both ends.
- `pipwr:L_Bourns_SRP1038A`: 2 pads 4.1 × 3.5 mm at ±4.75 mm; courtyard is the 10.0 × 11.0 mm body + 0.5 mm.
