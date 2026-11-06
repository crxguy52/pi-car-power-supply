"""kicad-cli ERC / DRC for the Pi power HAT, under a timeout: pdm run erc | pdm run drc.

Reports go to build/ (erc.rpt, drc.rpt); the kicad-cli summary lines and a count per violation type are printed.
Exit code: kicad-cli's (nonzero on a run failure, not on violations: compare the counts with CLAUDE.md "Verify").
"""
import collections
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import toolchain  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
STEM = 'pi_power_board'
SCH = ROOT / f'{STEM}.kicad_sch'
PCB = ROOT / f'{STEM}.kicad_pcb'
BUILD = ROOT / 'build'
COMMAND_TIMEOUT_S = 300.0
SUMMARY = re.compile(r'^(Found .*|Saved .*)$', re.M)
VIOLATION = re.compile(r'^\[([a-z_]+)\]', re.M)


def run(args, report):
    BUILD.mkdir(exist_ok=True)
    r = subprocess.run([str(toolchain.Toolchain().kicad_cli), *args, '-o', str(report)],
                       capture_output=True, text=True, timeout=COMMAND_TIMEOUT_S)
    print('\n'.join(SUMMARY.findall(r.stdout + r.stderr)) or (r.stdout + r.stderr).strip()[:400])
    if report.exists():
        for kind, n in sorted(collections.Counter(VIOLATION.findall(report.read_text(encoding='utf-8'))).items()):
            print(f'  {n:4d} {kind}')
    return r.returncode


def main(argv):
    if len(argv) != 2 or argv[1] not in ('erc', 'drc'):
        print(__doc__)
        return 2
    if argv[1] == 'erc':
        return run(['sch', 'erc', '--severity-all', str(SCH)], BUILD / 'erc.rpt')
    return run(['pcb', 'drc', '--schematic-parity', '--severity-all', str(PCB)], BUILD / 'drc.rpt')


if __name__ == '__main__':
    sys.exit(main(sys.argv))
