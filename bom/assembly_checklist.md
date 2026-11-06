# Pi power HAT: hand-assembly checklist

Generated 2026-11-05 from the schematic netlist and `tools/post_sch/14_bom_fields.py` (PARTS); D3 and C29 updated by the BOM staff review (`tools/post_sch/15_bom_review.py`); L1, R16, R17, R18, C31, C32 updated 2026-11-06 (U8 fixes, `tools/post_sch/16_buck_fixes.py`). One board; parts per [bom/PIPWR_BOM.md](PIPWR_BOM.md). Board picture with refs and pad 1 marked: `reports/assembly_top.png` (pad 1 red = diode cathode / IC pin 1).

- Order: small and flat first, heat-sinked pads after their neighbours are on, tall and THT last.
- Before step 1: inspect the bare board; tin nothing yet. Flux pen, 0.5 mm solder, fine tip for 0805 / SOT-23 / SOIC; a large chisel tip for U8 pad 9, Q1 tab, C22-C24 / C32, L1, the terminals.
- After the last step: clean flux; check for shorts BATT-GND, VOUT-GND, +5V1-GND before the first power-up (current-limited bench supply, 12 V, key off: expect a few µA).

## 1. 0805 resistors (no polarity)

| Done | Value | Refs | Qty | Footprint | Polarity / orientation | MPN |
|---|---|---|---|---|---|---|
| [ ] | 5.1 kΩ | R3 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW08055K10FKEA |
| [ ] | 22 kΩ 1 % | R8 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW080522K0FKEA |
| [ ] | 27 kΩ 1 % | R25 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW080527K0FKEA |
| [ ] | 100 kΩ | R26 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW0805100KFKEA |
| [ ] | 39.2 kΩ 1 % | R27 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW080539K2FKEA |
| [ ] | 78.7 kΩ 1 % | R28 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW080578K7FKEA |
| [ ] | 47 kΩ | R29 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW080547K0FKEA |
| [ ] | 10 kΩ 1 % | R31 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW080510K0FKEA |
| [ ] | 13.7 kΩ 1 % | R17 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW080513K7FKEA |
| [ ] | 220 kΩ 1 % | R14 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW0805220KFKEA |
| [ ] | 180 kΩ 1 % | R15 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW0805180KFKEA |
| [ ] | 73.2 kΩ 1 % | R16 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW080573K2FKEA |
| [ ] | 7.32 kΩ 1 % | R18 | 1 | R_0805_2012Metric_Pad1.20x1.40mm_HandSolder | - | CRCW08057K32FKEA |

## 2. 0805 capacitors (no polarity)

| Done | Value | Refs | Qty | Footprint | Polarity / orientation | MPN |
|---|---|---|---|---|---|---|
| [ ] | 10 nF 50 V C0G ±1 % | C29 | 1 | C_0805_2012Metric_Pad1.18x1.45mm_HandSolder | - (unmarked: keep it apart from C19's 10 nF X7R strip) | GCM21B5C2E103FX0AL |
| [ ] | 100 nF 50 V | C17, C18, C30 | 3 | C_0805_2012Metric_Pad1.18x1.45mm_HandSolder | - | C0805C104K5RACTU |
| [ ] | 10 nF 50 V | C19 | 1 | C_0805_2012Metric_Pad1.18x1.45mm_HandSolder | - | C0805C103K5RACTU |
| [ ] | 15 nF 50 V | C20 | 1 | C_0805_2012Metric_Pad1.18x1.45mm_HandSolder | - | C0805C153K5RACTU |
| [ ] | 1 µF 50 V | C8 | 1 | C_0805_2012Metric_Pad1.18x1.45mm_HandSolder | - | GMC21X7R105K50NT |

## 3. SOD-123 diodes and SOT-23 parts (polarity!)

| Done | Value | Refs | Qty | Footprint | Polarity / orientation | MPN |
|---|---|---|---|---|---|---|
| [ ] | 1N4148W | D4, D5 | 2 | D_SOD-123 | band = cathode = pad 1 | 1N4148W-E3-08 |
| [ ] | BZT52C5V1 | D7 | 1 | D_SOD-123 | band = cathode = pad 1 (to VDD_TMR) | BZT52C5V1-E3-08 |
| [ ] | BAS116LT1G | D6 | 1 | SOT-23_Handsoldering | SOT-23: fits one way (pin 1 A, pin 3 K, pin 2 NC) | BAS116LT1G |
| [ ] | 2N7002BK | Q5, Q6 | 2 | SOT-23_Handsoldering | SOT-23: fits one way (1 G, 2 S, 3 D) | 2N7002BK,215 |

- Diode band = cathode = pad 1 (red pad in `reports/assembly_top.png`).

## 4. U5 SOIC-14

| Done | Value | Refs | Qty | Footprint | Polarity / orientation | MPN |
|---|---|---|---|---|---|---|
| [ ] | CD4541BM96 | U5 | 1 | SOIC-14_3.9x8.7mm_P1.27mm | pin 1 dot / bevel to pad 1 | CD4541BM96 |

## 5. U8 TPS54336A: top pins, then the PowerPAD from the bottom

| Done | Value | Refs | Qty | Footprint | Polarity / orientation | MPN |
|---|---|---|---|---|---|---|
| [ ] | TPS54336ADDA | U8 | 1 | TI_DDA_PowerPAD-8_HandSolder | pin 1 dot to pad 1; PowerPAD from the bottom (step 5) | TPS54336ADDA |

- Solder pins 1-8 on top first (tack two opposite corners, check alignment, then the rest).
- Flip the board: feed solder into the 1.0 mm centre hole of pad 9 from the bottom pad (large tip, ~10 s, flux) until it wets through; the bottom pad is a heat sink, so pre-heat if the iron struggles.
- Check: pin 4 / pad 9 to GND (continuity), no bridge pin 2-3 (VIN-PH).

## 6. 1206 / 1210 parts

| Done | Value | Refs | Qty | Footprint | Polarity / orientation | MPN |
|---|---|---|---|---|---|---|
| [ ] | 1.3 kΩ 1 % | R30 | 1 | R_1206_3216Metric_Pad1.30x1.75mm_HandSolder | - | CRCW12061K30FKEA |
| [ ] | 1.5 kΩ | R21 | 1 | R_1206_3216Metric_Pad1.30x1.75mm_HandSolder | - | CRCW12061K50FKEA |
| [ ] | VFR1105W | D3 | 1 | LED_1206_3216Metric_Pad1.42x1.75mm_HandSolder | LED: cathode = pad 1 (red pad in `reports/assembly_top.png`). Stanley marks the cathode with a small corner mark on the top face (its pin 2) and a T-shaped mark underneath: confirm with a meter's diode test (it glows) before soldering. Dome lens: hold it by the body, keep the iron off the dome | VFR1105W-6C9-TR |
| [ ] | 10 µF 50 V | C15, C31 | 2 | C_1206_3216Metric_Pad1.33x1.80mm_HandSolder | - | GMC31X7R106K50NT |
| [ ] | 47 µF 10 V X7R | C22, C23, C24, C32 | 4 | C_1210_3225Metric_Pad1.33x2.70mm_HandSolder | - | GMC32X7R476K10NT |

- C22-C24, C32 (1210) and C15, C31 (1206) sit on pours: more heat, keep the tip on the pad, not the part (ceramic cracks).

## 7. SMB TVS diodes (polarity!)

| Done | Value | Refs | Qty | Footprint | Polarity / orientation | MPN |
|---|---|---|---|---|---|---|
| [ ] | SMBJ16A | TVS1, TVS2 | 2 | D_SMB_Handsoldering | unidirectional: band = cathode = pad 1 (to BATT / ACC_IN) | SMBJ16A |

## 8. Q1 DPAK: leads on top, then the tab from the bottom

| Done | Value | Refs | Qty | Footprint | Polarity / orientation | MPN |
|---|---|---|---|---|---|---|
| [ ] | SQD50P04-13L | Q1 | 1 | TO-252-2 | tab = drain (pad 2) on VOUT; tab from the bottom (step 8) | SQD50P04-13L_GE3 |

- Solder the gate and source leads on top (tack one, align, solder the other).
- Tab (drain, VOUT): heat it from the bottom through the B.Mask opening and the two 1.0 mm feed vias, or from the top at the tab edge; it takes a large tip and time (big copper area).
- Check: no short G-S (Q1_G to BATT should read ≈ R14 220 kΩ).

## 9. L1 inductor and SW1

| Done | Value | Refs | Qty | Footprint | Polarity / orientation | MPN |
|---|---|---|---|---|---|---|
| [ ] | SRP1038A-150M | L1 | 1 | L_Bourns_SRP1038A | no polarity | SRP1038A-150M |
| [ ] | SW_Nidec_CAS-120A1 | SW1 | 1 | Nidec_Copal_CAS-120A | match the footprint outline (J-hook leads); washable type with a seal tape over the top: leave it on through soldering and flux cleaning, peel it off afterwards to work the slider **(assumption: the Nidec datasheet does not say)** | CAS-120TA |

## 10. Through-hole connectors last

| Done | Value | Refs | Qty | Footprint | Polarity / orientation | MPN |
|---|---|---|---|---|---|---|
| [ ] | Screw terminal 3-pos | J1 | 1 | TerminalBlock_Phoenix_MKDS-1-3-3.81_1x03_P3.81mm_Horizontal | wire entry faces the board edge | 1727023 |
| [ ] | Screw terminal 2-pos / ACC_N GND | J4, J5 | 2 | TerminalBlock_Phoenix_MKDS-1-2-3.81_1x02_P3.81mm_Horizontal | wire entry faces the board edge | 1727010 |
| [ ] | USB3_A_Stacked | J2 | 1 | USB3_A_Molex_48406-0001_Horizontal_Stacked | board-lock pegs and shield tabs through their holes | 0484060001 |

- J2 last (tallest); keep the board flat so J2 seats square at the board edge.

Total: 46 refs per board (MH1-MH4 are holes, no part).
