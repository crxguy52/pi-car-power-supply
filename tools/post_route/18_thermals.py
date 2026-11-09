"""Post-route edit 18 (2026-11-09, project lead): thermal reliefs on SMD pads in every pour, for hand soldering.

Run with KiCad's python from the project root (KiCad must not have the board open):

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" -I tools/post_route/18_thermals.py [--dry-run] [--root DIR]

--root DIR works on DIR/pi_power_board.kicad_pcb (a scratch copy with the project files); default: the master.

What and why (project lead 2026-11-09: "I didn't want EVERY part to require [a preheat station]"):
- Since 09 / 11 the GND pours used thermals on through-hole pads only (SMD pads solid) and the BATT / VOUT / +5V1
  pours were solid on every pad. A solid 0805 / 1210 pad on 1 oz pours on both layers with 5 mm GND stitching sinks
  too much heat for a normal iron.
- Every copper pour's pad connection -> thermal relief (spoke width and gap unchanged: the zones' own settings).
- Footprint overrides, solid (SOLID_REFS), the parts where the copper is the point and which need the preheat
  station anyway:
  U8: the PowerPAD is its ground and heat path (soldered from the back by its centre via); its VIN / GND pins and
  C17 (the 100 nF input capacitor) form the hot loop (SLVSCD5D 10.1), where spokes would make the loop current
  detour round the pad gap (the spokes' own inductance, about 0.04 nH each, is small next to the part's ESL);
  Q1: the tab is its heatsink (DECISIONS "Routing staff review", Q1 tab thermal estimate).
- Pad override, solid (SOLID_PADS): C32 pad 1 sits at the left end of the P5V_TOP strip, where only one spoke fits
  (DRC starved_thermal on the first try); a solid pad beats a single-spoke joint there.
- Vias always connect solid (KiCad), so the stitching and the U8 / Q1 via fields are unchanged.
- Refill (route_lib.refill).

Staff review (2026-11-09; pcbnew diff vs the 152249 backup, spoke counts from the fill polygons, SLVSCD5D 10.1):
- Diff: only the 6 pours' pad connection, the 3 footprint overrides, C32.1's override and the refilled fills; the
  2 board dimensions' cached text re-rendered in mm (units "automatic"; every scripted save does this, the GUI
  re-renders it). Tracks, vias, footprints, drawings unchanged.
- Kept as applied. Spokes after the refill (0.5 mm x 35 um x 0.3 mm, about 0.3 mOhm each; conduction to the pour at
  both ends, so the long-trace IPC charts don't apply):
  J4.1 VOUT 3 (bottom; top pour doesn't reach it, as before): 1.7 A each at 5 A, about 95 A/mm2, 2.5 mW in all,
  self-heating in mK; J1.3 BATT 4: 1.25 A each; L1.2 +5V1 3: 1 A each at 3 A (L1's own loss is the bigger heat
  source; the spokes' 0.07 W/K adds a few K at most); TVS1/TVS2 2-3 spokes: about 3 K adiabatic per spoke at the
  SMBJ16A peak pulse current (10/1000 us), spoke inductance negligible. All acceptable.
- C15 / C31 (the 10 uF bypass caps SLVSCD5D 10.1 puts at VIN / GND) left on thermals: they carry the input ripple
  (about 1.5 A rms in all at 3 A) at the switching frequency, where the spokes' resistance and inductance are
  negligible next to the 1206 ESR / ESL; C15's spokes face U8. C31.2 has 1 spoke plus its 0.6 mm track (before:
  a 1.2 mm neck): about the same width.
- C32.1 confirmed: on thermal it fills with 1 spoke (scratch copy).
- Fixed: KiCad lock-file guard (route_lib.guard_locks) and check_fixed after the refill were missing.

Guards: KiCad lock files (route_lib.guard_locks); every pour is in POURS with the recorded old connection (else stop); no pad / footprint override exists
except the ones this script sets (SOLID_REFS, SOLID_PADS); "already applied" when every pour is thermal and the overrides are in place.
Backup first; check_fixed after the refill. Nothing else is touched.
"""
import pathlib
import sys

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import route_lib  # noqa: E402

STEM = 'pi_power_board'
THERMAL = pcbnew.ZONE_CONNECTION_THERMAL
SOLID = pcbnew.ZONE_CONNECTION_FULL
INHERIT = pcbnew.ZONE_CONNECTION_INHERITED
# pour name -> connection before this script (09 / 11)
POURS = {
    'GND_TOP': pcbnew.ZONE_CONNECTION_THT_THERMAL,
    'GND_BOT': pcbnew.ZONE_CONNECTION_THT_THERMAL,
    'BATT_TOP': SOLID,
    'VOUT_TOP': SOLID,
    'VOUT_BOT': SOLID,
    'P5V_TOP': SOLID,
}
SOLID_REFS = ('U8', 'Q1', 'C17')
SOLID_PADS = (('C32', '1'),)


def state(board):
    pours = {z.GetZoneName(): z for z in board.Zones() if not z.GetIsRuleArea()}
    if set(pours) != set(POURS):
        raise SystemExit(f'unexpected state: pours {sorted(pours)}')
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    for f in fps.values():
        want = (INHERIT, SOLID) if f.GetReference() in SOLID_REFS else (INHERIT,)
        if f.GetLocalZoneConnection() not in want:
            raise SystemExit(f'unexpected state: {f.GetReference()} footprint zone connection override')
        for p in f.Pads():
            want = (INHERIT, SOLID) if (f.GetReference(), p.GetNumber()) in SOLID_PADS else (INHERIT,)
            if p.GetLocalZoneConnection() not in want:
                raise SystemExit(f'unexpected state: {f.GetReference()} pad {p.GetNumber()} zone connection override')
    return pours, fps


def pad(fps, ref, num):
    (p,) = [p for p in fps[ref].Pads() if p.GetNumber() == num]
    return p


def main():
    argv = sys.argv[1:]
    dry = '--dry-run' in argv
    root = pathlib.Path(argv[argv.index('--root') + 1]).resolve() if '--root' in argv else ROOT
    pcb = root / f'{STEM}.kicad_pcb'
    route_lib.guard_locks()
    board = pcbnew.LoadBoard(str(pcb))
    pours, fps = state(board)
    done = (all(z.GetPadConnection() == THERMAL for z in pours.values())
            and all(fps[r].GetLocalZoneConnection() == SOLID for r in SOLID_REFS)
            and all(pad(fps, r, n).GetLocalZoneConnection() == SOLID for r, n in SOLID_PADS))
    if done:
        print('already applied')
        return 0
    for name, z in pours.items():
        if z.GetPadConnection() not in (POURS[name], THERMAL):
            raise SystemExit(f'unexpected state: {name} pad connection {z.GetPadConnection()}')
        print(f'  {name:9s} -> thermal (spoke {z.GetThermalReliefSpokeWidth() / 1e6:.2f} mm, '
              f'gap {z.GetThermalReliefGap() / 1e6:.2f} mm)')
    print(f'  solid overrides: {", ".join(SOLID_REFS)}; pads {", ".join(f"{r}.{n}" for r, n in SOLID_PADS)}')
    if dry:
        print('dry run: nothing written')
        return 0
    if root == ROOT:
        route_lib.backup(pcb)
    for z in pours.values():
        z.SetPadConnection(THERMAL)
    for r in SOLID_REFS:
        fps[r].SetLocalZoneConnection(SOLID)
    for r, n in SOLID_PADS:
        pad(fps, r, n).SetLocalZoneConnection(SOLID)
    pcbnew.SaveBoard(str(pcb), board)
    route_lib.refill(pcb)
    route_lib.check_fixed(pcb)
    print('applied; zones refilled')
    return 0


if __name__ == '__main__':
    sys.exit(main())
