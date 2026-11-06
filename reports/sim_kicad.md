# Sim: delay-off timer from the schematic (KiCad 10.0.7, ngspice 46)

The timer sim runs from `pi_power_board.kicad_sch` itself ([SPEC](../docs/SPEC.md) sections 2–4). Built by `tools/post_sch/12_kicad_sim.py` (agent A14), staff-reviewed and fixed by `tools/post_sch/13_sim_fast_review.py` + `lib/spice/` + `tools/run_sim.py` (2026-11-05, section "Staff review"). The LTspice decks in `ltspice/` are historical: a regression reference ([sim_delay_off_counter.md](sim_delay_off_counter.md)).

```
pdm run sim                    # all 14 scenarios, FAST mode (about 1.5 min), build/sim/results.json, exit 1 on a failure
pdm run sim --selftest         # + 6 deliberately broken decks that must FAIL (what verify-sch runs)
pdm run sim --full             # real time, TAPDIV 1 (about 25 min wall on 16 threads)
pdm run sim --list / --only NAME / --jobs N
Eeschema -> Inspect -> Simulator   # the sheet's default: FAST nominal key cycle, 12 V, 6 s transient
```

## How it is built

```
pi_power_board.kicad_sch ── Sim.* fields on 26 parts ─────────────┐
   U8, buck/USB passives, J1/J2/J4/J5, SW1: exclude_from_sim       │  kicad-cli sch export netlist --format spice
   sheet "simulation" (off board, off BOM) ── simulation.kicad_sch ┤──> build/sim/pi_power_board.cir
        battery+harness, key, SW1 stand-in, Pi load, Pi GPIO,      │      run_sim.py rewrites .param values per
        U8 stand-in (+ C15/C17), .param / .tran / .meas            │      scenario, the .tran line, interp on/off
lib/spice/pipwr_parts.lib, cd4541b.lib, sim_bench.lib ─────────────┘──> one ngspice.dll process per run (ctypes,
                                                                         in parallel) -> .meas -> limits
```

- **Connectivity (staff review, checked):** the exported SPICE deck's nodes for all 26 sim parts equal their pin nets (through `Sim.Pins`) in the kicadxml netlist, and the 44 board parts' values, footprints, non-Sim fields and pin nets equal `build/placement_netlist_snapshot.xml`. The 6 sim-only symbols are excluded from board and BOM; U8, the buck / USB passives, J1/J2/J4/J5 and SW1 are not in the deck and are replaced by: battery + harness on `BATT`, key on `ACC_IN`, SW1 switch `BATT` → `SW1_C`, Pi load on `VOUT`, Pi pull-up on `ACC_N`, U8 stand-in `VOUT` → `+5V1` (with C15 + C17 as `CIN_U8`, added by the review).

## Fast mode (default) and full mode

```
key-off ─┬─ U5 counts 2^15 / TAPDIV clocks ──┬─ U5 OUT low ─ Q5, Q1 off ─ VOUT < VB/2
         │  (real R27 / C29 / R28, real osc)  │
         │  t_osc = CTC rises 16..80 / 64     │
hold_est = measured hold + (32768 − 32768/TAPDIV) × t_osc        count check: U5 OUT at 128 ± 2 counts
```

- The cost is one solver landing per oscillator edge (≈ 37 s CPU per oscillator-second), so scaling C29 down would not help: the same 32 768 edges. **Fewer counts at the real frequency** keep the oscillator, the supply and every sequence real. FAST: TAPDIV 256 (128 counts, ≈ 0.12 s); times inside the count (Pi shutdown, overload start, restart) scaled by 1/256; key-on, blip, hot-plug, turn-off physical; tail 1 s after the key-off; no `interp` (the period needs the raw points).
- FULL: TAPDIV 1, real time, `interp` (one point per ms), tail 42 s, the end checks at real values; the hold is the measured one.
- The fast hold is only accepted if the count check passes (a wrong tap or Q/Q̅ would otherwise extrapolate to a plausible number).
- Not covered by fast: a slow drift during a 30 s count, the collapse seconds after the turn-off (fast end check: `VOUT` < VB/2 and `HOLD_G` ≤ 0.5 V 1 s after the key-off). That is `--full`.

## Models

| Part | Model | Source |
|---|---|---|
| R, C | KiCad built-in, numeric value in `Sim.Params`. R27 × `RFAC`, C29 × `CFAC` (corners), C8 × `C8_RET` 0.7 | schematic values |
| D4, D5 (1N4148W), D6 (BAS116) | `D` fitted to the BAS116 VF maxima, I_S per corner | LTspice deck |
| D7 BZT52C5V1 | zener, V_Z at 5 mA per corner (5.57 / 5.1 / 4.70 V); checked: 5.13 V at 5 mA, Z 57 Ω at 5 mA (≤ 60), 264 Ω at 1 mA (≤ 480); knee softer than a typical part (4.69 V at 1 mA): conservative at the low `VDD_TMR` end | Vishay 86342 |
| TVS1, TVS2 SMBJ16A | breakdown 18.8 V | Bourns |
| D3 LED | 2.0 V at 20 mA (datasheet typ 2.0) | LiteOn |
| Q5, Q6 2N7002BK; Q1 SQD50P04-13L | VDMOS stand-ins (**no vendor model**, retried: below). `VTO_N` / `VTO_P` = datasheet V_GS(th) at 250 µA (model converts to V_to); Q1 ksubthres 30 mV, 2N7002BK 0.1 V; `CGD_FAC` 1.8 in the hot-plug runs. Checked: Q1 R_DS(on) 16.4 mΩ at −4.5 V (16 typ / 22 max), 9.2 mΩ at −10 V (10 / 13); 2N7002BK 1.19 Ω at 5 V (1.3 / 2); C_iss 2.85 nF / 34 pF (2.87 nF / 33 pF typ); Q1 C_rss 0.92 / 0.49 / 0.41 / 0.38 nF at 1 / 5 / 12 / 25 V vs the Vishay typ curve ≈ 1.25 / 0.70 / 0.45 / 0.33 nF | datasheets |
| U5 CD4541B | behavioural, `lib/spice/cd4541b.lib`: real RC oscillator on the pins, charge counter (1 mV / count), tap A/B (checked against SCHS085E's frequency select table), MODE 0, Q/Q̅, MR, AR power-on reset (rising VDD only: assumption), output 370 Ω (the 125 °C I_OL at 0.4 V; typ 129 Ω), counts above 3 V. MODE 1 not modelled. **`TAPDIV`** speed knob (1 = the real part) | TI SCHS085E |
| Bench | `lib/spice/sim_bench.lib` (as before; U8 stand-in now with `CIN_U8` 5 µF) | LTspice deck |

**k calibration (unchanged, and circular):** HYS / RDRV / a C29 factor place the model's k = period / (RTC·CTC) on design_calc's 2.104 / 2.3 / 2.450. The sim's delay therefore equals the calc by construction, and the ±2 % "vs LTspice" check compares two models fitted to the same bound. SCHS085E gives k = 2.3 typical only, no limits. **The ≥ 25 s guarantee rests on design_calc's fig. 2 analysis + its 2 % allowance, not on this sim**; the sim proves the sequence, the levels and the turn-off. Bench item in TODO.

## Scenarios and results

Corners as before (1 short, 2 nominal, 3 long; `tools/run_sim.py` `CORNERS`). Loads: 1 = Pi halts 3 s after key-off, USB stays; 2 = full load throughout; 3 = Pi halted (2 W), no USB; overload runs 0.05 W. Every run starts with the battery hot-plug at 10 ms.

| Scenario | Corner | BATT (V) | Load | Hold fast (s) | Hold full, real time (s) | fast − full (ms) | LTspice (s) | Result fast / full |
|---|---|---|---|---|---|---|---|---|
| key_short_9V | short | 9 | 2 | 26.187 | **26.190** | -3 | 26.16–26.20 | PASS / PASS |
| key_short_12V | short | 12 | 2 | 26.177 | **26.178** | -1 | 26.16–26.20 | PASS / PASS |
| key_short_14.4V | short | 14.4 | 2 | 26.181 | **26.175** | +6 | 26.16–26.20 | PASS / PASS |
| key_short_16V | short | 16 | 2 | 26.174 | **26.172** | +2 | 26.16–26.20 | PASS / PASS |
| key_nominal_12V | nominal | 12 | 1 | 29.632 | **29.630** | +2 | 29.56–29.61 | PASS / PASS |
| key_long_12V | long | 12 | 3 | 33.000 | **32.994** | +6 | 32.56–32.61 | PASS / PASS |
| key_long_16V | long | 16 | 3 | 32.878 | **32.873** | +5 | 32.56–32.61 | PASS / PASS |
| restart_short_12V | short | 12 | 1 | 26.183 | **26.180** | +3 | 26.16–26.20 | PASS / PASS |
| blip50ms_short_12V | short | 12 | 1 | 26.181 | **26.179** | +2 | 26.16–26.20 | PASS / PASS |
| sw1_nominal_12V | nominal | 12 | 2 | 29.630 | **29.631** | -1 | 29.56–29.61 | PASS / PASS |
| usb_overload_nominal_12V | nominal | 12 | 3 | 29.654 | **29.649** | +5 | 29.56–29.61 | PASS / PASS |
| usb_overload_long_16V | long | 16 | 3 | 32.911 | **32.926** | -15 | 32.56–32.61 | PASS / PASS |
| hotplug_long_16V | long (C_gd max) | 16 | – | – (key off: `VOUT` 38 mV) | – | – | – | PASS / PASS |
| hotplug_short_9V | short (C_gd max) | 9 | – | – (key off: `VOUT` ≤ 0.5 mV) | – | – | – | PASS / PASS |

Full mode: run twice (2026-11-05); identical holds. The first run flagged `key_long_16V` only because `hold_est` used the aliased period (finding 12); its measured hold was the same 32.873 s.

- **≥ 25 s worst case: met.** Short corner 26.17–26.19 s (9–16 V), nominal 29.63 s, long 32.87–32.99 s; all within ±2 % of the LTspice deck (not independent: above).
- **One turn-off, no re-latch** in every run; full end (37–42 s after the edge): `VOUT` ≤ 1.51 V, `HOLD_G` < 1 nV, `VDD_TMR` ≤ 1.31 V.
- **Restart, 50 ms blip, SW1:** the same hold as a plain key-off (within 3 ms). **USB overload** (0.5 Ω, hiccup) ends on time.
- **Hot-plug, key off:** `VOUT` ≤ 0.02 mV (short / nominal), 38 mV after 3 s at the long corner with the maximum C_gd (Q1 85 °C leakage, not the gate kick). `HOLD_G` kick ≤ 1.04 V (short corner 16 V, threshold 2.35 V); **0.67 V at the long corner against its 0.75 V threshold: small margin**, microseconds, and C30 keeps Q1 off (C30-open selftest: Q1 turns on).
- **Levels:** `VDD_TMR` counting 4.69–5.69 V; `HOLD_G` ≥ 4.69 V; J5 0.096 V on, 3.15–3.30 V off.

**Selftest** (`--selftest`, in `verify-sch`): each broken deck must fail at least one check. All 6 caught: U5 A to GND (count check), Q/Q̅ SELECT to GND, R29 open, R27 −10 % (hold 23.6 s < 25 s), C30 open (hot-plug turns Q1 on, a full hold with the key off), D6 shorted out (no start-up).

## Runtime

- `pdm run verify-sch` (ERC + netlist + its selftest + PDF + sim fast 14 scenarios + sim selftest 6): **91 s** (sim 80 s wall, 16 workers; 13–45 s per run).
- `pdm run sim --full` (14 scenarios, 14 workers): **1408 s (23.5 min)** (1230–1500 s per scenario).
- Eeschema simulator default (fast nominal key cycle): ≈ 17 s of ngspice headless.

## Staff review (2026-11-05)

| # | Finding | Severity | Fixed |
|---|---|---|---|
| 1 | k fitted to design_calc: the sim's delay is not an independent proof of the k bound (above) | high (evidence) | documented; bench TODO |
| 2 | `verify-sch` sim 16 min for 3 scenarios; a scaled C29 would not help (edge count) | high (process) | yes: count scaling, 14 scenarios + selftest in 1.5 min |
| 3 | No sim selftest: a broken netlist was never shown to fail | medium | yes: 6 mutations |
| 4 | CD4541B "done" switch hysteresis 5 mV = 5 counts: output after 32 773 counts (+4.5 ms) | low | yes (0.2 mV) |
| 5 | VDMOS V_to used as V_GS(th): N 0.1 V, P 0.06 V off the 250 µA datasheet point | low | yes |
| 6 | C_rss below the Vishay typical curve at low V_DS (−26 % at 1 V): hot-plug kick underestimated | low | yes: × 1.8 in the hot-plug runs (PASS) |
| 7 | U8's input capacitors C15 / C17 missing from the stand-in | low | yes (`CIN_U8`) |
| 8 | GUI default = 50 s real-time transient (20+ min) | medium (usability) | yes: fast default |
| 9 | ksubthres 30 mV (Q1): physical (69 mV/dec, silicon ≈ 80–100) and its parked sub-threshold current ≪ I_DSS | – | kept; N-FET kept at 0.1 V (30 mV stalls the solver) |
| 10 | Zener knee softer than typical | low | kept (conservative low end) |
| 11 | Vendor models: retried with browser headers (`curl.exe`): Nexperia CDN 403 (Akamai), Vishay 65157 no SPICE document | – | not obtained |
| 12 | Full mode: the CTC period meas aliases under interp (found by the first `--full`) | low | yes: full uses the measured hold |

## Limits of the sim

- No vendor FET / diode models; U5 and U8 behavioural; AR on a rising VDD only (the slow-collapse re-latch risk of SPEC 3 cannot show here); MODE 1 not modelled.
- Not checked (sub-ms, `interp` in full mode): inrush peak, Q1 turn-off energy (LTspice report keeps those).
- The KiCad GUI simulator path was not run by an agent (TODO lead item).
