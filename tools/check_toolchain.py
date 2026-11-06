"""Check the toolchain against config/toolchain.toml: one PASS/FAIL line per item, exit 1 on any FAIL.

    pdm run check-toolchain                          # all items
    python -I tools/check_toolchain.py --only kicad-cli,pymupdf

Items: kicad-cli (version == pin), kicad-python (imports pcbnew, version == pin), java (runs, major >=
minimum), freerouting (jar exists, SHA-256 == pin), pymupdf (imports in this interpreter: the PDM env).
"""
import argparse
import hashlib
import re
import subprocess
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import toolchain  # noqa: E402

TOOL_TIMEOUT_S = 60.0       # KiCad python's first pcbnew import can take several seconds
HASH_CHUNK_BYTES = 1 << 20
LEGACY_JAVA_MAJOR = 1       # "1.8.0" style version strings: the major is the second field


class CheckError(Exception):
    pass


def _run(cmd):
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=TOOL_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CheckError(f'cannot run {cmd[0]}: {e}')
    if r.returncode != 0:
        raise CheckError(f'{pathlib.Path(str(cmd[0])).name} exit {r.returncode}: {(r.stderr or r.stdout).strip()[:120]}')
    return r.stdout + r.stderr


def check_kicad_cli(tc):
    found = _run([tc.kicad_cli, 'version']).strip()
    if found != tc.kicad_version:
        raise CheckError(f'{tc.kicad_cli} is {found}, pinned {tc.kicad_version}')
    return f'{found} ({tc.kicad_cli})'


def check_kicad_python(tc):
    out = _run([tc.kicad_python, '-I', '-c',
                'import sys, pcbnew; print("PIPWR_PCBNEW", pcbnew.Version(), sys.version.split()[0])'])
    m = re.search(r'^PIPWR_PCBNEW (\S+) (\S+)', out, re.M)
    if not m:
        raise CheckError(f'no pcbnew version in output: {out.strip()[:120]}')
    found, py = m.groups()
    if found != tc.kicad_version:
        raise CheckError(f'pcbnew is {found}, pinned {tc.kicad_version}')
    return f'pcbnew {found}, python {py} ({tc.kicad_python})'


def java_major(version_text):
    m = re.search(r'version "([^"]+)"', version_text)
    if not m:
        raise CheckError(f'no version in java -version output: {version_text.strip()[:80]}')
    fields = [int(x) for x in re.findall(r'\d+', m.group(1))]
    major = fields[1] if fields[0] == LEGACY_JAVA_MAJOR and len(fields) > 1 else fields[0]
    return m.group(1), major


def check_java(tc):
    version, major = java_major(_run([tc.java, '-version']))
    if major < tc.java_min_major:
        raise CheckError(f'java {version} (major {major}) < required {tc.java_min_major}')
    return f'{version} (major {major} >= {tc.java_min_major}) ({tc.java})'


def check_freerouting(tc):
    if not tc.freerouting_jar.is_file():
        raise CheckError(f'jar not found: {tc.freerouting_jar}')
    h = hashlib.sha256()
    with open(tc.freerouting_jar, 'rb') as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_BYTES), b''):
            h.update(chunk)
    if h.hexdigest() != tc.freerouting_sha256:
        raise CheckError(f'SHA-256 {h.hexdigest()} != pinned {tc.freerouting_sha256} ({tc.freerouting_jar})')
    return f'{tc.freerouting_version}, SHA-256 matches ({tc.freerouting_jar})'


def check_pymupdf(tc):
    try:
        import fitz
    except ImportError as e:
        raise CheckError(f'PyMuPDF not importable in {sys.executable} ({e}); run `pdm install`')
    return f'{fitz.VersionBind} ({sys.executable})'


CHECKS = {
    'kicad-cli': check_kicad_cli,
    'kicad-python': check_kicad_python,
    'java': check_java,
    'freerouting': check_freerouting,
    'pymupdf': check_pymupdf,
}


def run_checks(names, tc=None):
    """Run the named checks, print one line each; return True if all pass."""
    try:
        tc = tc or toolchain.Toolchain()
    except (OSError, KeyError, ValueError) as e:
        print(f'FAIL config: {e}')
        return False
    ok = True
    for name in names:
        try:
            print(f'PASS {name}: {CHECKS[name](tc)}')
        except CheckError as e:
            print(f'FAIL {name}: {e}')
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--only', help=f'comma-separated subset of: {",".join(CHECKS)}')
    args = ap.parse_args()
    names = args.only.split(',') if args.only else list(CHECKS)
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        ap.error(f'unknown check(s): {unknown}')
    return 0 if run_checks(names) else 1


if __name__ == '__main__':
    sys.exit(main())
