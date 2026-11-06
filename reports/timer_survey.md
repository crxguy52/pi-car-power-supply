# Timer survey: clock + counter delay-off on +5V1

2026-11-05, agent A11. Project-lead decision (DECISIONS): replace the RC / comparator timer with a clock + counter timer powered from `+5V1`. ACC (or SW1) turns Q1 on directly; the timer holds Q1 after ACC drops; a key-on during the count restarts the full delay; at the end `VOUT` and `+5V1` collapse, the timer's own supply included. Target **≥ 45 s worst case**, hand-solderable (SOIC / SOT-23-6, nothing smaller than 0805), fewest parts.

**Update 2026-11-05 (later, staff review A12):** the project lead lowered the target to **≥ 25 s** worst case. The survey below is the record at 45 s; its CD4541B figures (468 Hz, 56.5–85.7 s, k bound 2.0–2.6) are superseded by SPEC 3 (1.11 kHz, 26.2–32.5 s, k 2.105–2.449). One rejection changes basis: the **LTC6994's 33.6 s maximum now clears 25 s**. CD4541B stays the pick (datasheet, stock, price, SOIC; the LTC6994 has no PDF here, a 0.95 mm pitch and no tolerance figure read). TPL5110/5111 (no restart) and LTC6995 (no stock) are still out.

Sources:

- datasheets in `ref/datasheets/`: TI CD4541B (SCHS085E), CD4060B, CD4536B, SN74HC4040, TPL5110 (SNAS650A), TPL5111, Microchip ATtiny202/402 auto (DS40002159A), Nexperia 2N7002BK;
- Digi-Key via `pdm run dk-mpn`, 2026-11-05;
- ADI LTspice models (`LTC6994-1.sub`, `LTC6995-1.sub`, encrypted, ADI's own).

**Not obtained:**

- the ADI (LTC6993/6994/6995), onsemi (MC14541B) and Nexperia (74HC4060) PDFs: analog.com reset the connection, onsemi and Nexperia answered "Access Denied";
- CD4060B and CD4536B: the TI PDFs are scanned, so their tables can't be read as text.

Figures for those parts are marked **(no PDF)** and are not used in the design.

## What every option needs anyway

These parts are common to every row, not counted below:

- ACC → logic level: R8 / R25 divider to `ACC_G`;
- J5 status FET Q6;
- the hold FET Q5 on the Q1 gate network, with the ACC OR into its gate (D6, R29);
- decoupling C8.

The "parts" column counts the timer core: the IC, its timing parts, the reset interface and any stop / inverter logic.

## Comparison

| Option | Parts (core) | Worst-case delay accuracy | Supply, +5V1 dip | Restart on key-on | Output into Q5 | Start-up when +5V1 rises | Package | Temp. range | Stock / price at 10 | Main risk |
|---|---|---|---|---|---|---|---|---|---|---|
| **CD4541B** (TI) RC osc + 16-stage counter, tap 2^16, Q̅ select, single-transition | **5**: IC, RTC, CTC (C0G), RS, R26 (MR series) | Period / RC 2.27–2.42 (sim, `cd4541_osc_counter.cir`, input threshold 0.3–0.7·VDD, VDD 4.5–5.5 V; datasheet 2.3). Bound 2.0–2.6 used, plus C0G ±5 %, 1 % R and drift: **56.5–85.7 s** for 70.0 s nominal | 3–18 V operating, 20 V abs max. A dip below 3 V stops the count; the auto reset restarts a full count when VDD comes back | MR is level-active: a high level clears the counter and the output latch | Push-pull, ≥ 1.08 mA at 4.6 V / 0.4 V (125 °C, VDD 5 V) | Auto reset ("timing is initialized … turning power on"; reliable for VDD > 5 V) gives output high = hold. MR is also held high by ACC from the first volt | SOIC-14, 1.27 mm | −55 to 125 °C | CD4541BM96: 7972, $0.51; MC14541BDR2G (onsemi, no PDF): 5145, $0.49 | Oscillator below the formula's stated 1–100 kHz range (468 Hz): bench calibration. No oscillator tolerance in the datasheet |
| 74HC4060 / CD4060B, + stop diode + inverter | 7: IC, RT, CT, RS, stop diode, output inversion (Q14 is high at the end: a FET or an inverter), reset R | Same RC-oscillator class (CD4060B PDF scanned; no figure read) | HC 2–6 V; CD 3–18 V | MR, level ✓ | Push-pull | MR from ACC ✓; no power-on reset; the stop latch is random at power-up | SOIC-16 | CD4060B −55 to 125 °C | CD4060BM96 33337, $0.40; 74HC4060D 12186, $0.28 | Q14 needs 2^13 counts: f ≈ 117 Hz for 70 s. +2 parts vs CD4541B |
| CD4536B, 24-stage programmable | ≈ 7: IC, RC osc (3), reset R, the monostable RC (2) | Same RC class (PDF scanned) | 3–18 V | Reset ✓ | Push-pull | Not read (scanned PDF) | SOIC-16 **wide** (DW) | −55 to 125 °C | CD4536BDWR 968 cut tape, $1.03 | Most pins to tie and the most extra parts; PDF unreadable |
| LTC6994-1/-2 TimerBlox delay | 3 (IC, RSET, DIV divider 2) | **Fails: maximum delay 33.6 s** (ADI LTspice model: RSET 800 kΩ, DIVCODE 7 → 33.61 s) | 2.25–5.5 V (no PDF) | Retriggerable edge delay | Push-pull | (no PDF) | TSOT-23-6 | C, I, H grades (no PDF) | LTC6994CS6-1: 5431, $4.24; -2 I grade 0 | Range < 45 s: out |
| LTC6993 TimerBlox monostable | as LTC6994 | Same divider family: assumed ≤ 33.6 s (not simulated) **(assumption)** | (no PDF) | -1/-2 non-retriggerable | Push-pull | (no PDF) | TSOT-23-6 | (no PDF) | LTC6993IS6-1: 400, $4.59 | Range; -1/-2 do not restart |
| **LTC6995-1** TimerBlox "long time POR / watchdog timer" | 5: IC, RSET, DIV divider (2), RST series R | Not read (no PDF); resistor-set master oscillator | 2.25–5.5 V (no PDF) | **RST: output resets at once, tOUT runs from the last release** (ADI model, 3 RST pulses: 59.7 s after the last) | Push-pull | POR → output low for tOUT (ADI example "60 Second Power On Reset") | TSOT-23-6 0.95 mm | C / I / H (no PDF) | **0 in stock** (C, I and H grades), $4.24–5.77 | Out of stock; no PDF; 5.5 V max supply on a 5.09 V rail |
| TPL5110 / TPL5111 one-shot | 3–4: IC, REXT, M_DRV drive R, DONE tie | ±0.6 % setting + REXT 1 % + 400 ppm/°C + 0.4 %/V: ≈ ±5 % | 1.8–5.5 V | **Fails: "If the DRV is already LOW (MOSFET ON) the manual power ON is ignored"** (7.3.1, 7.5.2): a key-on mid-count does not restart | DRV push-pull (VDD − 0.7 V at 1 mA) | Reads REXT for 100–120 ms after POR; a high M_DRV aborts the reading | SOT-23-6 | −40 to 105 °C | TPL5111DDCR 20174, $0.87 | No restart: out |
| 74HC4040 + separate oscillator | 2 ICs + ≈ 5 | RC class | 2–6 V | MR ✓ | Push-pull | Random | 2 × SOIC | −40 to 125 °C | SN74HC4040DR 8567, $0.51 + osc IC | Two ICs |
| ATtiny402 (MCU, firmware reference) | **2**: IC, input series R (+ 3 UPDI programming pads) | OSC20M ±5 % over the full range (table 32-12); ULP 32 k ±30 % | 1.8 / 2.7–5.5 V, BOD (programmable) | Firmware | Push-pull, 20 mA class | Firmware after POR / BOD | SOIC-8 | −40 to 125 °C (Z / F grade) | ATTINY402-SSFR 7527, $0.54 | Firmware, a programmer and a flashing step per board; code needs review and version control |

## Verdict

Top 3:

1. **CD4541B: the pick.** It holds the whole function in one hand-solderable IC: oscillator, a counter long enough (2^15 counts) at a C0G-friendly frequency, the Q̅ polarity, a one-time transition that stays put, a level reset and a power-on reset. It is stocked from two sources, −55 to 125 °C, and has no firmware.
2. **ATtiny402:** 3 parts fewer and ±5 % timing, but it adds firmware, a UPDI programmer and a flashing step to a two-board hobby build. A defined BOD is its real advantage.
3. **LTC6995-1:** exactly the function in silicon (the ADI model shows a reset that restarts and tOUT from the last release). But it is out of stock in every grade, costs ~$5, has no PDF available, and its 5.5 V supply limit sits close to the rail.

Why CD4541B (justification):

- **Meets ≥ 45 s with margin while staying tolerant:** 56.5 s worst case even with a ±13 % allowance on the oscillator constant that the datasheet doesn't specify. A C0G capacitor removes the X7R insulation / DC-bias problem that killed the RC design.
- **Restart and start-up are built in:** MR (level) from ACC restarts the count; auto reset makes every power-up a bounded hold (output high, then a full count). No stop diode, no inverter, no latch parts (74HC4060 needs 2–3 more).
- **Rejections are on hard criteria, not taste:** LTC6994 / LTC6993 can't reach 45 s (33.6 s max); TPL5110/5111 ignore a re-trigger while the output is active (no restart); LTC6995 is unbuyable today; CD4536B adds parts and a wide package.
- **Robust supply:** a 20 V CMOS part on a 5.1 V rail tolerates any `+5V1` overshoot, and its inputs take clamp current (±10 mA abs max), which the ACC interface uses.
- **Cost and stock:** $0.51 at 10 with 8 k in stock, plus a pin-compatible onsemi second source.

Risks carried into the design (SPEC 3, TODO):

- the 468 Hz oscillator is below the formula's stated 1 kHz range (bench calibration of the delay);
- the auto-reset behaviour on a slowly falling `+5V1` is not described (bench: no second hold after the collapse);
- "reliable" auto reset is specified for VDD > 5 V, while `+5V1` is 5.09 V nominal.
