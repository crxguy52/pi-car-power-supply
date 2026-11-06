# Agent-driven KiCad board work: tool gotchas (Turbogen SLAB)

The KiCad 10, Freerouting, Digi-Key, Onshape and Beta-jobset traps that each cost a round trip on the Turbogen SLAB (2026-10-26 to 2026-10-31). Tool gotchas only. Elsewhere:

- **Process** (phases and gates, pipeline, coordinator vs. subagents, staff reviews, unattended runs, edits to a master, the **shared subagent rules** to paste into every brief): [docs/WORKFLOW.md](../../docs/WORKFLOW.md).
- **Per-phase questions and design lessons** (pin budget, mechanical concept first, technician access, ground islands vs. connector order): [templates/PHASE_CHECKLISTS.md](../../templates/PHASE_CHECKLISTS.md).
- **Reusable tools** and the spec tables they parse: [templates/TOOLS_AND_TABLES.md](../../templates/TOOLS_AND_TABLES.md). Starter files: [templates/](../../templates/README.md).

## KiCad 10

- **Schematic parity:** footprint `Path` = `/sheet-uuid/symbol-uuid` from the netlist tstamps. Also set the Sheetname/Sheetfile properties.
- **Y axis:** KiCad's Y points down. Use one conversion helper for spec coordinates (mil, Y up).
- **File format:** check the version's format before generating files (save an empty sheet with that KiCad and match it). Files saved in KiCad 10 don't open in 9: agree the version with every reviewer and the release machine.
- **3D models:** vendor STEP files attached with zero offset/rotate rendered as vertical jacks, or hung under the board. Verify each one: export a scratch board to STL with kicad-cli, match pin tips to pads (< 0.05 mm), and render in perspective.
- **The pcbnew API doesn't expose everything:**
  - Paper size (no `PAGE_INFO`) and the stackup are written by patching the saved file text, asserting exactly one match.
  - Add the solder-mask material to the stackup, or KiCad drops the mask Er on re-save.
  - No `PCB_TABLECELL` in Python: insert `(table ...)` nodes into the saved text, then reload.
- **Net-class order:** KiCad saves Default first, then by name. Write the same order, or every GUI open churns `.kicad_pro`.
- **`.kicad_dru`:** comments start with `#`. KiCad silently drops a rules file it can't parse, so check that every custom rule is in force after an edit.
- **Check what a DRC rule actually matches.** A rule with condition `A.Type == 'Zone'` silently skips track-to-pad cases. Test every custom rule with a deliberate violation, one per item-type pair.
- **Vendor silk at the board edge** gives `silk_edge_clearance`. Clipping it on the board gives `lib_footprint_mismatch` instead. Clip it in the library (`build_lib.py`) and update the board from the library, so DRC expects 0 and a real mismatch can't hide among expected ones.
- **Library UUIDs:** seed them (uuid5), or every library rebuild causes uuid-only churn.
- **Keep-out rule area:** cut it out around mounting holes, so the holes can sit inside "no parts" areas. Test by moving a part inside and checking that DRC fires.
- **Zones:**
  - DRC doesn't flag fill-to-fill clearance between same-priority zones.
  - A gap rule must cover zones *and* pads, vias and tracks of other ground nets.
  - A via with no track adopts the net of the zone it sits in on save.
  - Refill one priority level at a time after a scripted copper edit.
- **Diff-pair router:** it only recognises `_P/_N` or `+/-` net names, not `*_H/_L`. A blanket diff-pair DRC rule flags every connector breakout; scope it with rule areas.
- **Fields:** adding a symbol field makes DRC parity report `footprint_symbol_field_mismatch` per field until the footprints carry it ("Update PCB from Schematic", or a script). Insert a missing property as a copy of the symbol's hidden Datasheet property: an insert-only diff. In a field-copy loop, don't let `for key, value in ...` shadow an outer `value` (the board Value became the Digi-Key PN once; parity caught it).
- **Table sheets** (`(table ...)` objects, format from `share/kicad/demos/jetson-agx-thor-baseboard/power.kicad_sch`): give each table its own `(uuid ...)`, or kicad-cli adds a random one and re-sorts items (not reproducible). Pre-wrap long cells; there is no monospace font, so no ASCII art.
- **Text-level schematic edits:** hand-saved sheets keep CRLF line endings; detect and keep them, don't normalise.
- **wx Debug Alert dialogs** (e.g. `SHAPE_POLY_SET::SquaredDistance aOutlineOnly`) can block a headless script indefinitely. Wrap every KiCad python / kicad-cli call in `timeout`.
- **pcbnew pitfalls:** copying a board footprint crashes; footprints from `pcbnew.FootprintLoad` go invalid after the call; a shape needs a parent footprint before Flip; vias need a layer for GetWidth; `kicad-cli export bom --sort-asc true` crashes (bad_any_cast).
- **GUI edits can unlock or split scripted locked segments:** check the lock state in the regression.
- **Exact endpoint coincidence:** scripted tracks must share endpoints exactly (nm). Near-misses (< 2 µm) still pass DRC by overlap, but break Select Connection (U) and the length tuner. Snap them and check for them; rounding in your own measuring script hides them.
- **Lengths:** Net Inspector = total copper per net, including stubs (termination branches); the pair rule = signal path pad to pad; `U` selects the signal path; the tuner refuses locked tracks.
- **Footprint swaps** (vertical → right-angle, top → bottom): compare pads with the mechanical datum fixed (board edge or flange), not pin 1 (aligning pin 1 hid that every pad of the bottom-side P2 moved one row pitch). A bottom-side flip is a mirror that no rotation undoes; plug and socket footprints are mirrors of each other.

## Freerouting 2.5.0 (with scripted pairs)

- Locked copper exported as `type fix` comes back from the SES unchanged; confirm by comparing segment lists.
- **Set the plane layers to type `power` in the DSN.** Freerouting then routes only on the signal layers, and its vias join the planes.
- **A fixed stub to an SMD pad doesn't count as connected,** and ground fan-out fails. Place the SMD ground fan-out vias by script before exporting.
- **Island and split rules are invisible to it.** Route everything, check the island plan, rip the offending nets, re-route them with DSN keep-outs over the splits, slots and Chassis areas. About 26 min for 122 connections on a 390 × 235 mm board. Headless: `-de/-do --router.autorouter.max_passes=100 --gui.enabled=false`.
- **Review its output:** it left thin traces (class width not held on long runs), 1.125 mm necks on a 1.5 mm power net, a single via on a 3 A path (good for about 1 A) and 214 slivers under 10 µm. Fix with a targeted pcbnew script: change only the offending items, refill, save.
- **Small re-routes on a routed board: script them.** With nearly all copper fixed, Freerouting stalled (75 unrouted / 311 violations).
- **Java:** the Windows download bundles a JRE; no system Java needed (`config/toolchain.toml`).
- **Pair length matching by script:** bump the pair centre line with equal left and right turns (intra-pair skew unchanged); keep bumps out of pin fields and termination stubs; read the parameters from the spec.

## Impedance

IPC-2141A reads low for tight edge-coupled microstrip. Use Kirschning–Jansen or a 2D solver, and state whether the pairs are under solder mask. Always run a mesh-convergence check on a 2D solver and cross-check with the closed form: a non-converged solve gave 109 Ω, where the converged result and the closed form both read ~103 Ω.

## Digi-Key API

- **The website returns HTTP 403 to scripts:** use the API (developer.digikey.com, ProductInformation V4, 2-legged client credentials). Some manufacturer datasheet sites reject bare clients too (Lite-On: "Request Rejected" without browser headers; Python's certifi store also failed on its TLS chain: Windows `curl.exe` worked).
- **Sandbox vs production:** a Sandbox app's credentials fail on `api.digikey.com`. Create a Production app.
- **`setx` does not update running processes:** VS Code and its terminals keep the old (or no) value until restarted. Read `HKCU\Environment` (winreg) first; it is authoritative after a setx.
- **`productdetails` 404 can mean "Duplicate Products found":** the same MPN listed twice (Digi-Key stock plus a marketplace seller, e.g. RC0603JR-070RL). The body says so; fall back to a keyword search and take the exact-MPN listing with a cut-tape variation. Before that fallback, a valid part read as "not on Digi-Key".
- **`Product.QuantityAvailable` can be null:** use the per-variation `QuantityAvailableforPackageType`. The variations (tape & reel, cut tape, Digi-Reel) share one stock pool: take the max (or the cut-tape one), never the sum.
- **Cut tape for board-house assembly:** list the Digi-Key PN of the "Cut Tape (CT)" variation (`...CT-ND`, Lite-On `...-1-ND`), not tape & reel (`TR`, MOQ of a reel) or Digi-Reel (`DKR`, reeling fee).
- **Valid-looking codes can be unstocked:** pick passives by the manufacturer's naming rule, then confirm each one (RC0603FR-07100RL: 0 stock, 24 weeks; the `-13` reel code was stocked).

## Onshape API

- **Free accounts can only create public documents** (409 on `isPublic: false`). Before uploading, agree what may be public. Here: fixture geometry only, no board outlines or models, neutral names ("board A/B").
- **Explicit parameters:** adding a custom feature with an empty parameter list fails its precondition. Send every parameter, with values from the Feature Studio's `featurespecs` defaults.
- **Delete and re-add:** updating a feature after its FeatureScript changed fails with "does not match its feature spec". `build.py` deletes and re-adds the feature, so parameter edits in the Onshape UI are lost; edit the defaults in `baseplate.fs`.
- **Error messages:** the API reports only `REGEN_ERROR`. To debug, wrap the body in `try`/`catch`, store `toString(error)` with `setVariable`, read it back with a FeatureScript eval (`getVariable`), and remove the wrapper afterwards.
- **Reserved words:** `box` is reserved in FeatureScript. The eval endpoint takes `"queries": {}` (an object, not a list).
- **Exports:** STL downloads redirect to a signed URL; re-attach the auth header only on onshape.com redirects.
- **Keys:** like Digi-Key, read `HKCU\Environment` first ([docs/SETUP.md](../../docs/SETUP.md) "Onshape API").

## Beta 3DX jobset

- **Release BOM:** the jobset's BOM lists Reference, Value, Footprint, Datasheet, Description, Qty, #, MPN, DNP, but a `__` prefix in `fields_ordered` hides a column: the CSV is Reference, Value, Qty, MPN. Export with kicad-cli to a temp dir and look before claiming what a jobset outputs.
- **DNP parts:** the BOM job includes them unless "Exclude from BOM" is set; the position job has `exclude_dnp` false, so set "Exclude from position files" too.
- **Output origins:** pick-and-place = aux (drill/place) origin, STEP = grid origin, Gerbers / NC drill / ODB++ = page origin (absolute). Put the aux and grid origins on the board lower-left corner, and never use the aux origin as the spec frame in scripts (SLAB: `tools/slab_frame.py`).
- **`ASY_VARIANT`:** the FAB stage sets it to 0 while plotting, so silk built from `${ASY_VARIANT}` or `${REVISION}` prints the wrong revision on the Gerbers: write the revision as plain text.
- **Path variables:** the jobsets reference only `${BETA_KICAD_BOARDS_REPO}` (their scripts); `${BETA_KICAD_LIBS_REPO}` is used by the projects' title-block path. Grep the jobset before listing prerequisites.

## Reading PDFs

The Read tool can't render PDFs. Use PyMuPDF from the project venv (`pdm run raster`), ≤ 200 DPI (170–300 only for pin-level detail, cropped). Take pin-level facts from `page.get_drawings()` (wire geometry), not from the image by eye.

## Pi power HAT additions (2026-11-04)

- **Google Drive folder:** `kicad-cli sch/pcb upgrade` fails in place ("Cannot copy permissions ... .kicad-save-NNN"). Copy the KiCad files to `C:\tmp\pipwr\`, upgrade there, copy back. Read-only kicad-cli commands work in place. Keep the PDM venv out of the folder (`pdm config --local venv.in_project false`).
- **KiCad 10 on a KiCad 9 board:** DRC reports `lib_footprint_mismatch` for most standard footprints (22 here) both before and after the upgrade: library drift, not damage.
- **LTspice 24 batch:** `LTspice.exe -b file.cir` works (~1 s per 125 s run). A latching circuit fails the DC operating point (bistable): use `.tran ... uic`. A wrapper `.asc` with `.include` hung in batch (likely a modal dialog): run the `.cir` directly. Hard `if()` B-sources stall at t = 0: smooth them with `tanh`.
- **LTspice LT1017 is not open collector:** its output sources current. For an LM393/LM397 stand-in use a behavioural switch (or check the model with an output pull-down first).
- **LTspice raw:** `array.array('d', memoryview)` iterates bytes as ints; pass `bytes(...)` (tools/ltspice_raw.py). Decimate plots per pixel column (min/max), or edges vanish.
- **PyMuPDF text under `python -I`:** `PYTHONIOENCODING` is ignored; call `sys.stdout.reconfigure(encoding='utf-8')`.
- **pcbnew SWIG (KiCad 10.0.7):** `PCB_IO.FootprintLoad(lib, name)` with two arguments returns a bare `SwigPyObject`; pass the third (`False`). After `board.Remove(fp)`, keep a Python reference to `fp` until the save: once its proxy is garbage-collected, every later `FOOTPRINT*` comes back as a bare `SwigPyObject`. Never `taskkill /IM python.exe` to stop a hung run: it kills other agents' and MCP pythons too; stop the task or the PID.
- **Footprint order on save** follows the uuids: after reseeding uuids in the text (uuid5), load and save once more, or two identical runs give different files.
- **Terminal-block wire entry:** KiCad's Metz Type086 and Phoenix MKDS horizontal footprints both have the wire entry on local +y (the side 3.6 mm from the pad row; the Metz silk "nibble" rectangles are on the back). Check a lead's rotations against that before calling an edge "the wire side".
