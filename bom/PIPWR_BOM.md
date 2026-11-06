# Pi power HAT: bill of materials (Digi-Key)

Generated 2026-11-06 by `pdm run dk-bom` (tools/digikey_lookup.py) from the "Parts" table in [docs/SPEC.md](../docs/SPEC.md). Do not edit: change the spec and re-run. Stock and prices: Digi-Key API on the day.

- 2 boards; spares: Spares 'yes' rows 10% rounded up, at least 5; '+N' rows N; 'no' rows none. Price = unit price at the order quantity.
- `PIPWR_BOM_digikey.csv`: Digi-Key BOM Manager upload; Quantity is the total order quantity (build quantity 1).

**Order total: $121.32**

| Status | Part | Refs | Order | Manufacturer | MPN | Digi-Key PN | Stock | Unit $ | Line $ | dk-check |
|---|---|---|---|---|---|---|---|---|---|---|
| order | Input terminal GND/ACC/BATT 3-pos 3.81 mm, 10 A (IEC; 12 A max load), AWG 16–30 (UL) Phoenix MKDS 1/3-3,81 | J1 | 3 | Phoenix Contact | 1727023 | 277-1948-ND | 4948 | 1.69 | 5.07 | OK |
| order | J4: Pi 12 V output VOUT/GND; J5: ACC status to Pi GPIO (ACC_N/GND) 2-pos 3.81 mm, 10 A (IEC; 12 A max load), AWG 16–30 (UL) Phoenix MKDS 1/2-3,81 | J4 J5 | 5 | Phoenix Contact | 1727010 | 277-1947-ND | 7700 | 1.12 | 5.60 | OK |
| order | USB-A charging ports, stacked USB3 A stacked, 1.8 A per VBUS contact, −20 to 85 °C Molex 48406-0001 | J2 | 3 | Molex | 0484060001 | 0484060001-ND | 2312 | 3.37 | 10.11 | OK |
| order | Force-on switch (acts like the key) SPDT slide, 24 V / 25 mA switching Nidec CAS-120A (J-hook, taped) | SW1 | 4 | Nidec Components | CAS-120TA | CAS120JCT-ND | 47480 | 1.29 | 5.16 | OK |
| order | High-side P-FET 40 V, 22 mΩ at −4.5 V, AEC-Q101 DPAK (TO-252) | Q1 | 4 | Vishay Siliconix | SQD50P04-13L_GE3 | SQD50P04-13L_GE3CT-ND | 2722 | 4.17 | 16.68 | OK |
| order | Delay-off timer: RC oscillator + 16-stage counter, on VDD_TMR (VOUT through R30, D7 clamp) CD4541B, 3–18 V, −55 to 125 °C SOIC-14 | U5 | 4 | Texas Instruments | CD4541BM96 | 296-3536-1-ND | 7972 | 0.72 | 2.88 | OK |
| order | Q5: hold FET on DRV (Q1 gate network); Q6: ACC status open drain to J5 2N7002BK, 60 V, 350 mA, ESD-protected gate SOT-23 | Q5 Q6 | 9 | Nexperia | 2N7002BK,215 | 1727-4789-1-ND | 318603 | 0.19 | 1.71 | OK |
| order | 5.1 V buck for USB TPS54336A (tube: the DDAR cut tape has 0 stock) SO PowerPAD-8 (DDA), project hand-solder footprint | U8 | 4 | Texas Instruments | TPS54336ADDA | 296-41978-5-ND | 6672 | 3.10 | 12.40 | OK |
| order | Buck inductor 15 µH ±20 %, I_sat 10 A, I_rms 6.25 A, 45 mΩ max Bourns SRP1038A (10 × 11 mm) | L1 | 3 | Bourns | SRP1038A-150M | SRP1038A-150MCT-ND | 9422 | 1.09 | 3.27 | OK |
| order | BATT and ACC TVS SMBJ16A SMB | TVS1 TVS2 | 9 | Bourns | SMBJ16A | SMBJ16ABCT-ND | 539794 | 0.56 | 5.04 | OK |
| order | D5: ACC_IN → ACC_S isolation (keeps BATT/SW1 off the car's ACC line); D4: SW1 → ACC_S (keeps ACC off BATT when BATT is dead) 1N4148W, 75 V (100 V repetitive peak) SOD-123 | D4 D5 | 9 | Vishay | 1N4148W-E3-08 | 1N4148W-E3-08CT-ND | 83317 | 0.39 | 3.51 | OK |
| order | ACC_G → HOLD_G OR diode (Q1 on before +5V1 exists), low leakage BAS116L, 75 V, ≤ 80 nA at 150 °C SOT-23 | D6 | 7 | onsemi | BAS116LT1G | BAS116LT1GOSCT-ND | 22709 | 0.16 | 1.12 | OK |
| order | U5 supply clamp: VDD_TMR → GND BZT52C5V1 zener, 4.85–5.36 V at 5 mA, 300 mW on FR-4 SOD-123 | D7 | 7 | Vishay | BZT52C5V1-E3-08 | BZT52C5V1-E3-08CT-ND | 9992 | 0.48 | 3.36 | OK |
| order | VOUT-on LED (from VOUT), −40 to 100 °C red 1206 | D3 | 7 | Stanley Electric | VFR1105W-6C9-TR | 404-1321-1-ND | 1601 | 0.38 | 2.66 | OK |
| order | LED series (D3 to GND) 5.1 kΩ 1 % 0.125 W 0805 | R3 | 7 | Vishay Dale | CRCW08055K10FKEA | 541-5.10KCCT-ND | 79919 | 0.10 | 0.70 | OK |
| order | ACC_G divider top (ACC_S) 22 kΩ 1 % 0.125 W 0805 | R8 | 7 | Vishay Dale | CRCW080522K0FKEA | 541-22.0KCCT-ND | 97298 | 0.10 | 0.70 | OK |
| order | ACC_G divider bottom (also the ACC_S pull-down) 27 kΩ 1 % 0.125 W 0805 | R25 | 7 | Vishay Dale | CRCW080527K0FKEA | 541-27.0KCCT-ND | 48834 | 0.10 | 0.70 | OK |
| order | U5 MR series (clamp current, start-up) 100 kΩ 1 % 0.125 W 0805 | R26 | 7 | Vishay Dale | CRCW0805100KFKEA | 541-100KCCT-ND | 327095 | 0.10 | 0.70 | OK |
| order | U5 RTC (oscillator timing) 39.2 kΩ 1 % 0.125 W, ≤ 100 ppm/K 0805 | R27 | 7 | Vishay Dale | CRCW080539K2FKEA | 541-39.2KCCT-ND | 14963 | 0.10 | 0.70 | OK |
| order | U5 RS (oscillator input) 78.7 kΩ 1 % 0.125 W, ≤ 100 ppm/K 0805 | R28 | 7 | Vishay Dale | CRCW080578K7FKEA | 541-78.7KCCT-ND | 15371 | 0.10 | 0.70 | OK |
| order | U5 OUT → HOLD_G 47 kΩ 1 % 0.125 W 0805 | R29 | 7 | Vishay Dale | CRCW080547K0FKEA | 541-47.0KCCT-ND | 64627 | 0.10 | 0.70 | OK |
| order | U5 supply series: VOUT → VDD_TMR (pulse power at the TVS clamp) 1.3 kΩ 1 % 0.25 W 1206 | R30 | 7 | Vishay Dale | CRCW12061K30FKEA | 541-1.30KFCT-ND | 60423 | 0.11 | 0.77 | OK |
| order | Buck FB divider bottom 13.7 kΩ 1 % 0.125 W 0805 | R17 | 7 | Vishay Dale | CRCW080513K7FKEA | 541-13.7KCCT-ND | 32206 | 0.10 | 0.70 | OK |
| order | VDD_TMR bleed to GND (holds U5 unpowered against Q1 off-state leakage) 10.0 kΩ 1 % 0.125 W 0805 | R31 | 7 | Vishay Dale | CRCW080510K0FKEA | 541-10.0KCCT-ND | 2364311 | 0.10 | 0.70 | OK |
| order | Q1 gate pull-up (G-S) 220 kΩ 1 % 0.125 W 0805 | R14 | 7 | Vishay Dale | CRCW0805220KFKEA | 541-220KCCT-ND | 31888 | 0.10 | 0.70 | OK |
| order | Q1 gate to DRV (Q5) 180 kΩ 1 % 0.125 W 0805 | R15 | 7 | Vishay Dale | CRCW0805180KFKEA | 541-180KCCT-ND | 26232 | 0.10 | 0.70 | OK |
| order | Buck FB divider top 73.2 kΩ 1 % 0.125 W 0805 | R16 | 7 | Vishay Dale | CRCW080573K2FKEA | 541-73.2KCCT-ND | 22999 | 0.10 | 0.70 | OK |
| order | Buck COMP 7.32 kΩ 1 % 0.125 W 0805 | R18 | 7 | Vishay Dale | CRCW08057K32FKEA | 541-7.32KCCT-ND | 19976 | 0.10 | 0.70 | OK |
| order | J5 series (Q6 drain to the Pi cable: fault current) 1.5 kΩ 1 % 0.25 W 1206 | R21 | 7 | Vishay Dale | CRCW12061K50FKEA | 541-1.50KFCT-ND | 54750 | 0.11 | 0.77 | OK |
| order | U5 CTC timing capacitor (≥ 50 V needed), AEC-Q200 10 nF 250 V C0G ±1 % 0805 | C29 | 7 | Murata Electronics | GCM21B5C2E103FX0AL | 490-GCM21B5C2E103FX0ALCT-ND | 2089 | 0.68 | 4.76 | OK |
| order | C17: buck VIN high-frequency bypass; C18: buck BOOT; C30: Q1 gate-source (battery hot-plug) 100 nF 50 V X7R ±10 % 0805 | C17 C18 C30 | 11 | KEMET | C0805C104K5RACTU | 399-C0805C104K5RACTUCT-ND | 7109112 | 0.10 | 1.10 | OK |
| order | Buck soft start 10 nF 50 V X7R ±10 % 0805 | C19 | 7 | KEMET | C0805C103K5RACTU | 399-C0805C103K5RACTUCT-ND | 1069261 | 0.15 | 1.05 | OK |
| order | Buck COMP 15 nF 50 V X7R ±10 % 0805 | C20 | 7 | KEMET | C0805C153K5RACTU | 399-C0805C153K5RACTUCT-ND | 47494 | 0.12 | 0.84 | OK |
| order | U5 decoupling on VDD_TMR 1 µF 50 V X7R ±10 % 0805 | C8 | 7 | Cal-Chip Electronics | GMC21X7R105K50NT | 4713-GMC21X7R105K50NTCT-ND | 15023 | 0.17 | 1.19 | OK |
| order | Buck input 10 µF 50 V X7R ±10 % 1206 | C15 C31 | 9 | Cal-Chip Electronics | GMC31X7R106K50NT | 4713-GMC31X7R106K50NTCT-ND | 101415 | 1.50 | 13.50 | OK |
| order | Buck output, 4 × 47 µF: ≥ 8.7 µF each effective at 5.07 V for eq 22; the only +5V1 capacitance (no USB bulk) 47 µF 10 V X7R ±10 % 1210 | C22 C23 C24 C32 | 13 | Cal-Chip Electronics | GMC32X7R476K10NT | 4713-GMC32X7R476K10NTCT-ND | 2849 | 0.74 | 9.67 | OK |
