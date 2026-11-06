"""Schematic gate: pdm run verify-sch.

1. ERC (kicad-cli, all severities) -> build/erc.rpt; fails on any error, lists warnings by type;
2. netlist check against SPEC 7 (tools/check_netlist.py) and its selftest;
3. schematic PDF -> reports/schematic.pdf (exported to a local temp dir and copied: kicad-cli can't write in place
   on the Google Drive folder) and a PNG -> reports/schematic.png;
4. text overlap check on the PDF: no two words overlap (identical text plotted twice at the same place is ignored);
5. the delay-off timer sim from the schematic: every scenario in fast mode plus the sim selftest
   (`tools/run_sim.py --selftest`; real time: `pdm run sim --full`).

Exit code 0 only if every step passes. Every KiCad call runs under a timeout.
"""
import collections
import itertools
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_netlist  # noqa: E402
import toolchain  # noqa: E402

import fitz  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCH = ROOT / 'pi_power_board.kicad_sch'
BUILD = ROOT / 'build'
REPORTS = ROOT / 'reports'
ERC_RPT = BUILD / 'erc.rpt'
PDF_OUT = REPORTS / 'schematic.pdf'
PNG_OUT = REPORTS / 'schematic.png'
PNG_DPI = 100
COMMAND_TIMEOUT_S = 300.0
SIM_TIMEOUT_S = 1800.0         # fast mode + selftest (in parallel); run_sim.py has its own per-run timeout
RUN_SIM = pathlib.Path(__file__).resolve().parent / 'run_sim.py'
PT_PER_MM = 72 / 25.4
WORD_SHRINK_PT = 0.35          # word boxes are padded: shrink before testing overlap
SAME_PLACE_PT = 0.2
ERC_ITEM = re.compile(r'^\[([a-z_]+)\]: .*\n\s+; (error|warning)', re.M)


def kicad(args):
    r = subprocess.run([str(toolchain.Toolchain().kicad_cli), *args], capture_output=True, text=True,
                       timeout=COMMAND_TIMEOUT_S)
    if r.returncode != 0:
        raise SystemExit(f'kicad-cli {args[:3]} failed: {(r.stdout + r.stderr).strip()[:400]}')


def step_erc():
    BUILD.mkdir(exist_ok=True)
    kicad(['sch', 'erc', '--severity-all', '-o', str(ERC_RPT), str(SCH)])
    items = ERC_ITEM.findall(ERC_RPT.read_text(encoding='utf-8'))
    count = collections.Counter(items)
    errors = sum(n for (kind, sev), n in count.items() if sev == 'error')
    print(f'ERC: {errors} error(s), {len(items) - errors} warning(s)')
    for (kind, sev), n in sorted(count.items()):
        print(f'  {n:4d} {sev:7s} {kind}')
    return errors == 0


def step_netlist():
    ok = check_netlist.main(['check_netlist']) == 0
    ok_self = check_netlist.main(['check_netlist', '--netlist', str(check_netlist.NETLIST), '--selftest']) == 0
    return ok and ok_self


def text_overlaps(pdf):
    """(word count, overlaps) over every page (root sheet and sub-sheets)."""
    n, out = 0, []
    for page_no, page in enumerate(fitz.open(pdf), 1):
        words = page.get_text('words')
        n += len(words)
        out += [f'page {page_no}: {o}' for o in _page_overlaps(words)]
    return n, out


def _page_overlaps(words):
    out = []
    for a, b in itertools.combinations(words, 2):
        if a[4] == b[4] and abs(a[0] - b[0]) < SAME_PLACE_PT and abs(a[1] - b[1]) < SAME_PLACE_PT:
            continue
        ra = fitz.Rect(a[:4]) + (WORD_SHRINK_PT, WORD_SHRINK_PT, -WORD_SHRINK_PT, -WORD_SHRINK_PT)
        rb = fitz.Rect(b[:4]) + (WORD_SHRINK_PT, WORD_SHRINK_PT, -WORD_SHRINK_PT, -WORD_SHRINK_PT)
        if ra.intersects(rb):
            out.append(f'{a[4]!r} / {b[4]!r} at {a[0] / PT_PER_MM:.1f}, {a[1] / PT_PER_MM:.1f} mm')
    return out


def step_pdf():
    REPORTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        pdf = pathlib.Path(tmp) / 'schematic.pdf'
        kicad(['sch', 'export', 'pdf', '-o', str(pdf), str(SCH)])
        shutil.copyfile(pdf, PDF_OUT)
    doc = fitz.open(PDF_OUT)
    doc[0].get_pixmap(dpi=PNG_DPI).save(PNG_OUT)
    doc.close()
    n, overlaps = text_overlaps(PDF_OUT)
    print(f'PDF: {PDF_OUT.relative_to(ROOT)}, {PNG_OUT.relative_to(ROOT)}; {n} words, {len(overlaps)} overlap(s)')
    for o in overlaps:
        print(f'    {o}')
    return not overlaps


def step_sim():
    try:
        r = subprocess.run([sys.executable, '-I', str(RUN_SIM), '--selftest'], capture_output=True, text=True,
                           encoding='utf-8', timeout=SIM_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        print(f'sim: timeout {SIM_TIMEOUT_S:g} s')
        return False
    print((r.stdout + r.stderr).rstrip())
    return r.returncode == 0


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    results = {'erc': step_erc(), 'netlist + selftest': step_netlist(), 'pdf + text overlap': step_pdf(),
               'sim (run_sim.py)': step_sim()}
    for name, ok in results.items():
        print(f'{"PASS" if ok else "FAIL"} {name}')
    return 0 if all(results.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
