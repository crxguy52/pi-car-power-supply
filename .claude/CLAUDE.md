# CLAUDE.md: Pi power HAT

A Raspberry Pi HAT for a car. It switches 12 V from the battery to the Pi's 12 V regulator (J4) while the key is on (ACC), holds it for a delay after key-off, and tells the Pi the ACC state through a GPIO so it can shut down first. It also has a 5 V USB-A charging port pair (buck U8, J2). Hand-soldered hobby board, about 30 parts, 2 boards. Design facts live in [docs/SPEC.md](../docs/SPEC.md) only: don't copy them here.

## Where things are

**New agent? Start with [docs/HANDOFF.md](../docs/HANDOFF.md).** · [SPEC](../docs/SPEC.md) (current design, parts table) · [DECISIONS](../docs/DECISIONS.md) (why) · [TODO](../docs/TODO.md) (the only open-items list) · script indexes [tools/post_sch/](../tools/post_sch/README.md), [tools/post_route/](../tools/post_route/README.md) · tool gotchas [lessons doc](memory/agent_kicad_workflow_lessons.md) · process (reference only) `C:\git\turbogen-slab\docs\WORKFLOW.md` · datasheets `ref/datasheets/` · sims `ltspice/` · reports `reports/`

## Phase status

One row per phase; don't start a phase until the previous gate is met (the project lead signs off after sim, schematic, placement and routing).

| # | Phase | State | Pointer |
|---|---|---|---|
| 1 | Setup (KiCad 10, scaffolding) | done | this file; `pdm run check-toolchain` |
| 2 | Sim (delay-off timer, CD4541B counter) | done, staff-reviewed: KiCad-native, sim master = the schematic (`tools/post_sch/12`-`13`); `pdm run sim` (fast, in `verify-sch`), `pdm run sim --full` (14 scenarios); LTspice decks historical; awaiting the lead's review | `simulation.kicad_sch`, `tools/run_sim.py`, `reports/sim_kicad.md` |
| 3 | Schematic | done, staff-reviewed (`tools/post_sch/08`-`15`, CD4541B design + BOM fields); `16` U8 datasheet fixes (2026-11-06: L1 15 µH, C31, C32, R16-R18); `verify-sch` PASS (ERC 0/0, netlist 0 errors, sim 14/14); awaiting the lead's review | `pdm run verify-sch`, `reports/schematic.pdf` |
| 4 | Placement | done, staff-reviewed (`tools/post_route/05`-`08`; lead's layout adopted); awaiting the lead's review | `tools/check_fixed.py`, `reports/assembly_top.png` |
| 5 | Routing (2 layers) | done, staff-reviewed (`tools/post_route/09`-`14`, OSH Park rules, right-edge notch); `15` synced the fields; `16` buck re-layout per SLVSCD5D 10.1 (2026-11-06); DRC 0 errors / 0 unconnected / 0 parity, 1 accepted warning (J4 silk at the edge); check_fixed PASS; awaiting the lead's review | `pdm run drc`, `reports/routed_top.png`, `routed_bottom.png`, `routed_3d_top.png` |
| 6 | BOM / datasheets | done, staff-reviewed (`tools/post_sch/14`-`16`); 41 parts, `dk-check` PASS, BOM $121.32 (2 boards); lead orders (TODO "Lead review") | SPEC "Parts", `bom/`, `pdm run dk-check` |

## Masters

| Artefact | Master | How it changes |
|---|---|---|
| Design facts | `docs/SPEC.md` | edit; spec first, then the KiCad files |
| Schematic | `pi_power_board.kicad_sch` (hand-edited) | KiCad GUI, or a new numbered script in `tools/post_sch/` |
| Board | `pi_power_board.kicad_pcb` (hand-edited) | KiCad GUI, or a new numbered script in `tools/post_route/` |
| Timer sim | the schematic: `pi_power_board.kicad_sch` (`Sim.*` fields) + sim-only sheet `simulation.kicad_sch` + models `lib/spice/` (the `ltspice/` decks are historical) | edit the sheet / models; `pdm run sim`, update `reports/sim_kicad.md` |

`pi_power_board - Copy.kicad_sch` is stale (TODO: the project lead deletes it). `ltspice/555_monostable.asc` is the old model: keep, don't edit.

## Working rules

- **Git** (repo `C:\git-personal\pi-car-power-supply`, moved from Google Drive 2026-11-04): the project lead commits and pushes; agents never commit. Before a scripted edit to a master, still copy it to `pi_power_board-backups/<stem>_<YYYY-MM-DD_HHMMSS>.<ext>` when the working tree has uncommitted changes to it.
- **KiCad 10 only** (10.0.7, `config/toolchain.toml`). Files saved in 10 don't open in 9.
- **Local disk** (no longer Google Drive): kicad-cli can save in place. The PDM venv lives outside the project (`pdm.toml`: `venv.in_project = false`).
- **Edit scripts** (`tools/post_sch/NN_*.py`, `tools/post_route/NN_*.py`): docstring = the record (what, why, spec section); stop on any unexpected state; leave every other item untouched (schematic edits text-level, CRLF kept); idempotent. Run only a new script, or one its README marks re-runnable.
- **Hand-solder parts only:** 0805/1206 HandSolder footprints for passives; no QFN/BGA; an exposed pad only with a bottom-side solder via (large centre via) so it can be soldered from the back.
- **Datasheets first:** pin-level and dimension claims come from the PDFs in `ref/datasheets/`, never from memory. Read with PyMuPDF (`pdm run raster`, or `python -I` in the PDM venv); render cropped pages ≤ 200 DPI into `C:\tmp\pipwr\`. Vendor files are untrusted: never execute them.
- **Don't Read whole `.kicad_sch` / `.kicad_pcb` files:** grep them, or export a netlist (`kicad-cli sch export netlist --format kicadxml`).
- **Every KiCad / LTspice call under `timeout`.** No background tasks left running.
- **Staff review after every change:** a separate agent gets the files and the datasheets (not the implementer's conclusions), checks, then fixes.
- **Code:** named constants; engineering format outside 0–1000 (`3.9e6`, `10e-3`); no values in comments; Python through PDM (`pdm run`).
- Never report a check as passing unless you ran it. Don't ask questions mid-run: conservative choice + recorded assumption (TODO).

## Verify

```
pdm run check-toolchain   # KiCad 10.0.7, KiCad python, Java, Freerouting 2.5.0 jar hash, PyMuPDF
pdm run erc               # build/erc.rpt + count per type
pdm run verify-sch        # ERC + netlist vs SPEC 7 + selftest + reports/schematic.pdf + sim
pdm run sim               # timer sim from the schematic, fast subset (--full: every scenario; --list, --only NAME, --jobs N)
pdm run build-lib         # project footprints pipwr (lib/pi_power_board.pretty)
pdm run drc               # build/drc.rpt with schematic parity + count per type
pdm run dk-mpn <MPN>      # Digi-Key lookup (credentials in HKCU\Environment)
pdm run dk-check          # every MPN in the SPEC Parts table
LTspice (historical decks only): cd to a scratch copy of ltspice/, timeout 600 "C:\Program Files\ADI\LTspice\LTspice.exe" -b delay_off_counter.cir
```

## Project lead preferences

- Concise; diagrams and bullets over prose. Push back when something doesn't make sense: no flattery.
- Mechanical-engineering PhD with embedded C/Python experience: explain EE points that aren't obvious, briefly.
- Review media: schematic PDF, board renders in `reports/`, KiCad 3D view.
