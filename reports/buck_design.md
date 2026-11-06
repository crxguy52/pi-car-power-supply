# Buck U8 (TPS54336A): design calculations (2026-11-06)

Source: TI **SLVSCD5D** (`ref/datasheets/TI_TPS54336A_SLVSCD5D.pdf`); section / equation numbers are from it. Every number is from `pdm run python -I tools/design_calc.py` (`buck()`, log `build/design_calc.log`). Values: [SPEC 4, 6, 7](../docs/SPEC.md). Reasons: [DECISIONS](../docs/DECISIONS.md) 2026-11-06.

```
VOUT ─┬─ C15, C31 (2 × 10 µF 50 V X7R 1206) ─ C17 100 nF ─ GND     BOOT(1) ─ C18 100 nF ─ PH(3)
      └─ VIN(2)        EN(7) open (internal pull-up)               PH(3) ─ L1 15 µH ─┬─ +5V1 ─ C22–C24, C32 (4 × 47 µF 10 V X7R 1210) ─ GND
SS(8) ─ C19 10 nF ─ AGND                                                              ├─ R16 73.2k ─┬─ VSENSE(5)
COMP(6) ─ R18 7.32k ─ C20 15 nF ─ AGND        GND(4) + PowerPAD(9) ─ GND               │             └─ R17 13.7k ─ AGND
AGND = separate F.Cu return traces to the PowerPAD (10.1)                              └─ J2A / J2B VBUS
```

## Requirements

| Item | Value | Source |
|---|---|---|
| VIN (= `VOUT`) | 9–14.4 V, **16 V** continuous (TVS standoff), 26 V at the clamp | SPEC 4 |
| Output | 3 A for J2A + J2B; USB VBUS **4.75–5.25 V** at the port | USB 2.0 |
| fsw | 340 kHz (272–408 kHz) | 6.7 |
| VREF, gm_ea, gm_ps | 0.8 V, **0.788–0.812 V** over TJ; 1300 µA/V; 8 A/V | 6.5, 7.3.16–17 |
| HS current limit | 4.0 / 4.9 / **6.5 A** | 6.5 |

## Values

| Part | Value | Equation and result |
|---|---|---|
| R16 / R17 | **73.2 k / 13.7 k** 1 % | Eq 15/16: VOUT = 0.8 × (1 + R16/R17) = **5.074 V**; worst **4.915–5.238 V** (ref ±1.5 %, R ±1 %). At the port with a 0.1 V board + connector drop at 3 A (**assumption**): ≥ 4.815 V. Picked by an E96 search for the largest smaller margin with R17 10–20 kΩ (`_fb_search()`); was 53.6 k / 10.0 k (5.252 V worst) |
| L1 | **15 µH**, Bourns SRP1038A-150M | Eq 19: L_min = VOUT (VIN − VOUT) / (VIN K_IND I_OUT fsw) = **11.3 µH** at 16 V, K_IND 0.3 (8.2.2.6.1: "as high as 0.3" with ceramics). Ripple 0.68 A → **K_IND 0.23** at 16 V (0.35 with L −20 % and fsw 272 kHz together). Eq 20/21: I_rms 3.01 A, I_pk 3.42 A. Datasheet table: I_sat **10 A** (L −20 %) > the 6.5 A limit max; I_rms 6.25 A (40 °C rise); DCR 40 / 45 mΩ → 0.36 / 0.41 W. Same 10 × 11 mm footprint |
| C22–C24, C32 (Cout) | **4 × 47 µF** 10 V X7R 1210 | Eq 22: C > 2 ΔI / (fsw ΔV) = **34.8 µF** (1.5 A step, 5 %). Eq 23: C > ΔI_L / (8 fsw V_ripple) = **8.3 µF** (30 mV). Eq 24: ESR < 44 mΩ. Effective 47 / 64 / 113 µF at 25 / 34 / 60 % retention: **margin ≥ 35 %** (eq 22) and 464 % (eq 23) at fsw typ; eq 22 at fsw min 272 kHz needs 43.5 µF (8 % at 25 %): the loop-based step (below) is the criterion used, **assumption**. Eq 25: 49 mA rms per capacitor |
| C15, C31 (Cin) | **2 × 10 µF** 50 V X7R 1206 | Eq 17: ΔVIN = I_OUT × 0.25 / (C fsw) + I_OUT ESR = **227 mV p-p** (282 mV at fsw min) with 10 µF effective (50 % at 9–16 V, **assumption**) and 2 mΩ ESR (8.2.2.5): ≤ 400 mV (TI example limit). Eq 18: I_rms 1.5 A total |
| C17 | 100 nF 50 V X7R 0805 | 8.2.2.5 / 10.1: high-frequency bypass, closest to VIN / GND |
| C18 (BOOT) | 100 nF 50 V X7R 0805 | 8.2.2.8: "must be 0.1 µF", X7R / X5R |
| C19 (SS) | 10 nF 50 V X7R 0805 | Eq 5: t_ss = C × 0.8 V / 2.3 µA = **3.48 ms** |
| R18 / C20 (COMP, Type 2B) | **7.32 k** / 15 nF | Eq 10: R = 2π fc VOUT Co / (gm_ea VREF gm_ps) = 7.35 k at fc 30 kHz, Co 64 µF. Eq 11/12: C = R_L Co / R = 14.8 nF → 15 nF (zero on the full-load output pole). No C6 / C11 (eq 13/14 optional, ceramics) |
| EN | open | Pin table, 7.3.5: "float the EN pin to enable"; VIN UVLO 4.0–4.5 V rising (6.5) |

## Loop

Model (`_loop_gain()`): power stage eq 6–8 (gm_ps · Z_out), current-mode sampling double pole at fsw/2 with Q 0.3–1 (**assumption**), error amplifier gm_ea into R18 + C20 ∥ Coea 20.7 pF ∥ Roea 3.07 MΩ (7.3.15 small-signal model), divider VREF/VOUT.

| Cout retention | fc / PM at 3 A, Q 0.64 |
|---|---|
| 25 % | 39.9 kHz / 68° |
| 34 % (design) | 29.5 kHz / 73° |
| 60 % | 16.9 kHz / 79° |

All cases (retention 25–60 %, 0.1–3 A, Q 0.3–1, fsw 272 / 340 / 408 kHz): **fc 15.9–42.4 kHz, PM ≥ 45.8°** (requirement 45°; worst at 25 %, 0.1 A, Q 0.3, fsw min; ≥ 51° at fsw typ). Load step 1.5 A from the loop, ΔI / (2π fc Co): ≤ 155 mV vs the 254 mV (5 %) of eq 22. Model only: bench a load step.

## DC-bias retention (assumption)

- Cal-Chip GMC publishes no DC-bias curve; Murata / TDK / Samsung reject scripted downloads (2026-11-04). So: Cout **25 / 34 / 60 %** at 5.1 V (34 % back-calculated from the TI power-stage measurement with 47 µF 10 V X5R 1206, 8.2.2.7); Cin **50 %** at 9–16 V.
- The fourth output capacitor makes eq 22 hold with 35 % margin even at 25 %. Bench (TODO): ripple at 3 A, load step.

## Thermal, min on-time

- 8.2.2.9 losses plus the low-side conduction loss: **1.0 W typ** at 3 A (9–14.4 V), 1.84–1.88 W with max R_DS. JEDEC RθJA 42.1 °C/W: TJ ≈ 128 °C typ at TA 85 °C; max R_DS reaches the 160 °C shutdown (hiccup, no damage). A 2-layer board is worse.
- Min on-time: D / fsw_max = 480 ns at 26 V ≫ 145 ns max (6.7).

## Layout (10.1, fig. 55; SPEC 5 "Buck layout")

- **Power block:** U8, C17 (closest), C15 to the right of VIN / GND; PH by 2 vias at pin 3 to a 1.5 mm B.Cu trace (≈ 7 mm) and back up at L1 pin 1 by 4 vias; C31 below C15 on the VOUT pour, GND by 2 vias; C18 at BOOT, its PH side by a B.Cu branch.
- **FB:** R16 / R17 directly above pin 5; the `U8_FB` node is 5.5 mm of 0.25 mm trace (was 18.6 mm). The `+5V1` sense line runs from C24 along the top edge to R16.
- **COMP / SS:** R18 at pin 6, C20 below it, C19 at pin 8, all F.Cu, on the side away from PH.
- **Analog ground:** R17, C19, C20 return by two separate F.Cu traces: R17 to the top end of the PowerPAD, C19 + C20 (joined) to its bottom end. They touch the pour only on pad 9 (U8's ground reference), so no loop; strictly two landing points on the one pad, not the single junction of 10.1 (accepted: µV-level drop across the pad). Rule area `AGND_KEEPOUT` (F.Cu, no zone fill) keeps the GND pour off them; B.Cu GND pour underneath.
- Board script: `tools/post_route/16_buck_layout.py`.

## Footprints (project library `pipwr`, unchanged)

- `pipwr:TI_DDA_PowerPAD-8_HandSolder`: TI DDA0008B land (p52), pins 0.60 × 2.00 mm (+0.45 mm for the iron), pad 9 2.95 × 4.90 mm top / 4.0 × 6.0 mm bottom with mask opening, **1.0 mm centre solder via**, 10 thermal vias 0.3 / 0.6 mm.
- `pipwr:L_Bourns_SRP1038A`: 2 pads 4.1 × 3.5 mm at ±4.75 mm (datasheet p1 layout), courtyard body + 0.5 mm. Fits every SRP1038A value.

## No polyfuse

The HS / LS current limit, hiccup and thermal shutdown (6.5, 7.3.13–14) protect a shorted port; a polyfuse would cost 0.1–0.2 V of VBUS and two parts. Total 3 A for both ports.
