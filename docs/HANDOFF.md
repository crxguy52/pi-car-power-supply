# Handoff: Pi car power HAT (2026-11-06)

For a new agent picking this up. Read this, then `.claude/CLAUDE.md`, the whole of it: phase table, masters, working rules, verify commands. Don't re-derive what's below; it's checked.

## What the board does
A HAT on standoffs above a Waveshare 2-CH CAN FD HAT, which sits on a Pi 5, in a car.
- **Key on:** ACC switches BATT through Q1 (P-FET) to VOUT. VOUT feeds J4 (the Pi's external 12 V regulator) and U8 (a TPS54336A buck: 5.1 V, 3 A, J2 dual USB-A for the phone and screen).
- **Key off:** J5 tells the Pi straight away (open drain, low = ACC on). U5 (CD4541B counter, powered from VOUT through R30 + 5.1 V zener D7) holds Q1 on for ≥ 25 s worst case, ~29.6 s nominal. Then everything drops, timer included. Parked drain is ~µA.
- **SW1:** acts like the key.
- **Hand-soldered**, 2 boards, OSH Park 2-layer.

## State: every agent phase is done; the project lead's review is pending
| Item | State | Evidence |
|---|---|---|
| Schematic | 41 parts + J1/J2/J4/J5/SW1. Master edits by `tools/post_sch/01`–`16` (16 = U8 datasheet fixes) | `pdm run verify-sch` PASS (ERC 0/0, netlist 0 errors, selftest, sim 14/14) |
| Sim | KiCad-native (`simulation.kicad_sch`, `lib/spice/`, `tools/run_sim.py`); LTspice decks are history | `pdm run sim` (fast, inside verify-sch); `pdm run sim --full` (~24 min, real time) |
| Board | Placed and routed; OSH Park rules; right-edge notch y 85.0–102.0 | `pdm run drc`: 0 errors / 0 unconnected / 0 parity + 1 accepted warning (J4 silk); `check_fixed.py` PASS |
| BOM | 36 MPN rows, $121.32 for 2 boards + spares | `pdm run dk-check` PASS; `bom/` incl. `assembly_checklist.md` |
| IC review for the lead | U8 and U5 against their datasheets, with screenshots | `reports/ic_review.md` |

**Git:** one commit (`e96698a`, the original KiCad 9 baseline). **All agent work is uncommitted.** The lead commits; agents never commit or push.

## Where to start
1. `docs/TODO.md`, section "Lead review": what the lead still has to look at or decide.
2. `docs/TODO.md` "Bench": measurements to make after assembly (U5 oscillator on CTC ≤ 1.31 kHz; cap DC bias; Q1 temperature).
3. `reports/overnight_state.md`: one line per step of the agent runs.

## Open decisions for the lead (also in TODO)
- **Output caps:** U8 Cout margin is 8 % at the minimum switching frequency (272 kHz). A fifth 47 µF would restore 20 %.
- **D3 brightness:** the new Stanley LED is 9–18× brighter. Raise R3?
- **J2 datasheet:** the Molex 48406-0001 PDF couldn't be downloaded (blocked); it needs fetching by hand.
- **CAN HAT fit:** confirm the CAN HAT's back header fits the notch, y 85.0–102.0.
- **Pi software** (not in this repo): read the ACC_N **level** at boot, not just edges, because after a rapid key cycle the Pi boots with ACC already off. Enable the hardware watchdog.

## Rules and gotchas that cost time here
- **Masters change only by KiCad GUI edits (by the lead) or a new numbered script** in `tools/post_sch/` or `tools/post_route/`. Re-run only scripts that their README marks re-runnable; most are applied-once and stop at their guard.
- **The lead edits layouts in a copy** (`C:\git-personal\pi-car-power-supply - Copy`). Adopt them by diffing (netlist, UUIDs, positions) and applying via a recorded script with the positions saved as JSON. Never copy files wholesale. Check the result; the lead says not to take it as gospel.
- **Fixed by the lead:** board outline, MH1–4, J1/J2/J4/J5 positions, keep-outs. `tools/check_fixed.py` enforces them. The only way to change the baseline is a recorded `--accept-lead-change <NAME>`.
- **One writer per KiCad file.** Parallel agents must have explicit file ownership. Sim/BOM fields added in the schematic cause DRC `footprint_symbol_field_mismatch` until they are synced to the board (`tools/post_route/15` pattern: hidden fields).
- **Parts:** nothing smaller than 0805; hand-solderable only; prefer fewer parts. Every reviewer addition needs a named, datasheet-backed failure mode (the design once bloated to 64 parts through reviewer fixes, and the lead rejected it).
- **Machine:** C: is ~99 % full, so keep sim and scratch output small and delete `.raw` files. Never `taskkill /IM python.exe`. Wrap every KiCad/LTspice/ngspice call in `timeout`.
- **Scratch folders the agents couldn't delete** (the lead can): `C:\tmp\pipwr\a15`, `a16`, `a19`, `a22`, `scr12`, `scr12b`, `rend`, `rev`, and the stale `Z:\My Drive\fastboi\pi_power_board\` (the old location, superseded).
- **Lead preferences:** concise, diagrams and bullets, push back, no flattery. Ask before acting unless told to run unattended. When unattended, ask no questions: make the conservative choice and record it in TODO. Staff review after every change, by a separate agent given the primary sources.

## Likely next steps
1. The lead reviews `reports/ic_review.md`, the renders in `reports/` (`routed_*`, `assembly_top.png`), `reports/schematic.pdf`, and the GUI simulator (Eeschema → Inspect → Simulator).
2. Apply any lead feedback through new numbered scripts, then re-run `pdm run verify-sch`, `pdm run drc`, `check_fixed.py` and `pdm run dk-check`.
3. Fab outputs for OSH Park (Gerbers/drill, or upload the `.kicad_pcb`) **only when the lead asks**, then place the order from `bom/PIPWR_BOM_digikey.csv`.
4. Bring-up: follow `bom/assembly_checklist.md` and the TODO "Bench" list.
