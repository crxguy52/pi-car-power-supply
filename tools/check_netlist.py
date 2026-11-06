"""Compare the schematic netlist with SPEC section 7 (Netlist) and the Parts table: pdm run check-netlist.

    python -I tools/check_netlist.py [--netlist build/netlist.xml]   # exports the netlist first if not given
    python -I tools/check_netlist.py --selftest                       # every check must catch a mutated copy

Checks (each one a named function, so the selftest can prove each one fails on a mutated copy):
- refs: every SPEC 7 ref is in the netlist, no extra parts;
- values and footprints: equal to SPEC 7 (aliases `R_1206` / `C_1206` and "(as J4)" resolved);
- footprints resolve: the library nickname is a KiCad standard library or a project `fp-lib-table` entry, and the
  .kicad_mod file exists;
- pads: every symbol pin number is a copper pad of the footprint and every numbered copper pad is a symbol pin (the
  netlist pin numbers are symbol pins; the board connects by pad number, which the SPEC 7 comparison can't see);
- pins: every pin of every part has the SPEC net, or is unconnected where SPEC says "no connect"; no pin SPEC
  doesn't list;
- nets: no net SPEC doesn't name;
- fields: MPN = the Parts table MPN where one is given; Datasheet = `${KIPRJMOD}/<Parts table path>` where given,
  and every `${KIPRJMOD}` datasheet path exists.

Sim-only symbols (the simulation sheet, tools/post_sch/12: excluded from the board AND the BOM) are left out before
the checks, with the nets only they touch; a SPEC part flagged that way is therefore reported missing (selftest).

SPEC is the contract (docs/SPEC.md "## 7. Netlist", "## 6. Parts"). The parser lives here and is imported by the
edit scripts in tools/post_sch/ (01 historical, 03 current), so the schematic and the check read the table the same
way.
"""
import argparse
import copy
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sexpr  # noqa: E402
import toolchain  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / 'docs' / 'SPEC.md'
SCH = ROOT / 'pi_power_board.kicad_sch'
NETLIST = ROOT / 'build' / 'netlist.xml'
FP_LIB_TABLE = ROOT / 'fp-lib-table'
KICAD_FP_DIR = toolchain.Toolchain().kicad_cli.parent.parent / 'share' / 'kicad' / 'footprints'
KIPRJMOD = '${KIPRJMOD}/'
NETLIST_HEADING = '## 7. Netlist'
PARTS_HEADING = '## 6. Parts'
NETLIST_HEADER0 = 'Ref'
NC = None                                   # "no connect" in SPEC = unconnected pin in the netlist
NC_TEXT = 'no connect'
UNCONNECTED_PREFIX = 'unconnected-'
SUPERSEDED = 'superseded'
NO_MPN = ('TBD', '-', '')
COMMAND_TIMEOUT_S = 120.0
COPPER_LAYER_SUFFIX = '.Cu'                 # '*.Cu', 'F.Cu', 'B.Cu'
SELFTEST_FP_2PAD = 'Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder'
SELFTEST_FP_3PAD = 'Package_TO_SOT_SMD:SOT-23_Handsoldering'
SELFTEST_FP_14PAD = 'Package_SO:SOIC-14_3.9x8.7mm_P1.27mm'   # a quad-comparator package for U1
SELFTEST_FP_8PAD = 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'     # an 8-pin package for U5
# Design-specific mutations (staff review 2026-11-05): the errors that flip this board's logic
SELFTEST_CMP = ('U1', '2', '3')            # U1A IN- / IN+: swapped inputs invert the timer (LM2903B design)
SELFTEST_CMP_POWER = ('U1', ('4', '8'))   # U1 power unit (GND, VCC) left unplaced (LM2903B design)
SELFTEST_DIODE = ('D4', '1', '2')         # SW1 diode reversed
# CD4541B timer (2026-11-05, tools/post_sch/08): mutations that break the hold
SELFTEST_TMR = 'U5'
SELFTEST_TMR_SWAPS = (('5', '6', 'U5 AR / MR swapped (reset tied off, auto reset fed by ACC)'),
                      ('10', '9', 'U5 MODE / Q-SELECT swapped (recycle mode, output low after reset)'),
                      ('1', '3', 'U5 RTC / RS swapped (oscillator wired backwards)'))
SELFTEST_TMR_SUPPLY = ('U5', '14', 'VOUT')  # U5 VDD straight on VOUT, bypassing R30 / D7 (tools/post_sch/09)
SELFTEST_CLAMP_DIODE = ('D7', '1', '2')    # D7 zener reversed: VDD_TMR held at one forward drop
SELFTEST_HOLD_FET = ('Q5', '1', '3')       # Q5 gate / drain swapped: HOLD_G on the drain
SIM_ONLY_FLAGS = ('exclude_from_board', 'exclude_from_bom')   # kicadxml <property name=...> of a sim-only symbol
SELFTEST_SIM_ONLY = 'R8'                  # a real part flagged sim-only must not vanish silently
SELFTEST_BLEED = 'R31'                     # VDD_TMR bleed left off: parked Q1 leakage can wake U5
SELFTEST_SUPPLY_SPOT = {'D7': {'1': 'VDD_TMR', '2': 'GND'}, 'R30': {'1': 'VOUT', '2': 'VDD_TMR'},
                        'R31': {'1': 'VDD_TMR', '2': 'GND'}}
ALIAS_RE = re.compile(r'`(\w+)` = `([^`]+)`')
AS_RE = re.compile(r'^\(as (\w+)\)$')
VALUE_RE = re.compile(r'value "([^"]+)"')
NOTE_RE = re.compile(r'\.\s+(?=[A-Z])')     # a sentence after the pin list
PIN_RE = re.compile(r'^(?P<pins>(?:\d+|SH)(?:\s*,\s*(?:\d+|SH))*)(?![\w])(?P<name>[^→]*)→\s*'
                    r'(?P<net>no connect|[A-Za-z0-9_+]+)')


# ---------------------------------------------------------------- SPEC parsing

def _section(md, heading):
    start = md.index(heading)
    nxt = md.find('\n## ', start + len(heading))
    return md[start:nxt if nxt >= 0 else len(md)]


def _rows(text, header0):
    """Rows (lists of cells) of the first markdown table whose first header cell is header0."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if line.startswith('|') and cells[0] == header0:
            out = []
            for row in lines[i + 2:]:
                if not row.startswith('|'):
                    break
                out.append([c.strip() for c in row.strip().strip('|').split('|')])
            return cells, out
    raise SystemExit(f'SPEC: no table with first column {header0!r}')


def _split_top(text, sep):
    """Split on sep outside parentheses."""
    parts, depth, cur = [], 0, ''
    for ch in text:
        depth += (ch == '(') - (ch == ')')
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    return parts + [cur]


def parse_pins(cell, ref):
    """'1 K → BATT; 2 A → GND' -> {'1': 'BATT', '2': 'GND'} (NC for 'no connect')."""
    pins = {}
    cell = NOTE_RE.split(cell, 1)[0]            # free text after the pin list ("... ACC_N. J4 and J5 ...")
    for chunk in _split_top(cell, ';'):
        chunk = chunk.strip()
        m = PIN_RE.match(chunk)
        if not m:
            raise SystemExit(f'SPEC 7 {ref}: cannot parse pin entry {chunk!r}')
        net = NC if m['net'] == 'no' or m['net'] == NC_TEXT else m['net']
        for pin in re.split(r'\s*,\s*', m['pins']):
            if pin in pins:
                raise SystemExit(f'SPEC 7 {ref}: pin {pin} listed twice')
            pins[pin] = net
    return pins


def parse_netlist_table(md):
    """{ref: {'value', 'footprint', 'pins': {pin: net or NC}}} from SPEC section 7."""
    sec = _section(md, NETLIST_HEADING)
    aliases = dict(ALIAS_RE.findall(sec))
    header, rows = _rows(sec, NETLIST_HEADER0)
    if len(header) != 4:
        raise SystemExit(f'SPEC 7 table header {header}: expected 4 columns')
    spec = {}
    for ref_cell, value, fp, pins in rows:
        ref = ref_cell.split()[0]
        m = VALUE_RE.search(value)
        spec[ref] = {'value': m[1] if m else value, 'footprint_cell': fp, 'pins': parse_pins(pins, ref)}
    for ref, row in spec.items():
        fp = row.pop('footprint_cell')
        m = AS_RE.match(fp)
        if m:
            fp = spec[m[1]].get('footprint') or spec[m[1]]['footprint_cell']
        row['footprint'] = aliases.get(fp, fp)
    return spec


def parse_parts_table(md):
    """{ref: {'mpn', 'datasheet'}} for every non-superseded Parts row (empty strings where not given)."""
    header, rows = _rows(_section(md, PARTS_HEADING), 'Ref')
    col = {name: i for i, name in enumerate(header)}
    parts = {}
    for row in rows:
        if row[col['Status']] == SUPERSEDED:
            continue
        mpn = row[col['MPN']]
        for ref in re.split(r'\s*,\s*', row[col['Ref']]):
            parts[ref] = {'mpn': '' if mpn in NO_MPN else mpn, 'datasheet': row[col['Datasheet']]}
    return parts


# ---------------------------------------------------------------- netlist

def export_netlist(out):
    out.parent.mkdir(exist_ok=True)
    cmd = [str(toolchain.Toolchain().kicad_cli), 'sch', 'export', 'netlist', '--format', 'kicadxml',
           '-o', str(out), str(SCH)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_S)
    if r.returncode != 0:
        raise SystemExit(f'netlist export failed: {(r.stdout + r.stderr).strip()[:400]}')


def read_netlist(path):
    """{'comps': {ref: {value, footprint, fields}}, 'pins': {ref: {pin: net or NC}}, 'nets': set}."""
    root = ET.parse(path).getroot()
    comps, pins, nets, netrefs = {}, {}, set(), {}
    libpins = {(lp.get('lib'), lp.get('part')): {p.get('num') for p in lp.iter('pin')} for lp in root.iter('libpart')}
    for c in root.iter('comp'):
        fields = {f.get('name'): (f.text or '') for f in c.iter('field')}
        src = c.find('libsource')
        flags = {p.get('name') for p in c.iter('property')}
        comps[c.get('ref')] = {'sim_only': all(f in flags for f in SIM_ONLY_FLAGS),'value': c.findtext('value') or '', 'footprint': c.findtext('footprint') or '',
                               'fields': fields, 'datasheet': c.findtext('datasheet') or '',
                               'sympins': set(libpins.get((src.get('lib'), src.get('part')), ()))}
    for n in root.iter('net'):
        name = n.get('name').lstrip('/')
        net = NC if name.startswith(UNCONNECTED_PREFIX) else name
        if net is not NC:
            nets.add(net)
        for node in n.iter('node'):
            pins.setdefault(node.get('ref'), {})[node.get('pin')] = net
            if net is not NC:
                netrefs.setdefault(net, set()).add(node.get('ref'))
    return {'comps': comps, 'pins': pins, 'nets': nets, 'netrefs': netrefs}


def board_view(nl):
    """The netlist without the sim-only symbols and the nets only they touch."""
    sim = {r for r, c in nl['comps'].items() if c.get('sim_only')}
    if not sim:
        return nl
    refs = nl.get('netrefs', {})
    return {'comps': {r: c for r, c in nl['comps'].items() if r not in sim},
            'pins': {r: p for r, p in nl['pins'].items() if r not in sim},
            'nets': {n for n in nl['nets'] if n not in refs or refs[n] - sim},
            'netrefs': {n: rs - sim for n, rs in refs.items()}}


# ---------------------------------------------------------------- checks (each returns a list of error strings)

def check_refs(spec, parts, nl):
    have, want = set(nl['comps']), set(spec)
    return [f'missing part {r}' for r in sorted(want - have)] + [f'extra part {r}' for r in sorted(have - want)]


def check_values(spec, parts, nl):
    return [f'{r}: value {nl["comps"][r]["value"]!r}, SPEC {s["value"]!r}' for r, s in spec.items()
            if r in nl['comps'] and nl['comps'][r]['value'] != s['value']]


def check_footprints(spec, parts, nl):
    return [f'{r}: footprint {nl["comps"][r]["footprint"]!r}, SPEC {s["footprint"]!r}' for r, s in spec.items()
            if r in nl['comps'] and nl['comps'][r]['footprint'] != s['footprint']]


def project_fp_libs():
    if not FP_LIB_TABLE.exists():
        return {}
    text = FP_LIB_TABLE.read_text(encoding='utf-8')
    return {m[0]: pathlib.Path(m[1].replace(KIPRJMOD.rstrip('/'), str(ROOT)))
            for m in re.findall(r'\(name "([^"]+)"\).*?\(uri "([^"]+)"\)', text)}


def footprint_file(fp, libs=None):
    libs = project_fp_libs() if libs is None else libs
    nick, _, name = fp.partition(':')
    return libs.get(nick, KICAD_FP_DIR / f'{nick}.pretty') / f'{name}.kicad_mod'


def check_footprint_files(spec, parts, nl):
    libs, errs = project_fp_libs(), []
    for ref, comp in sorted(nl['comps'].items()):
        path = footprint_file(comp['footprint'], libs)
        if not path.exists():
            errs.append(f'{ref}: footprint {comp["footprint"]} not found ({path.parent})')
    return errs


_PAD_CACHE = {}


def footprint_pads(path):
    """Numbered copper pads of a .kicad_mod file (paste-only and unnumbered pads excluded)."""
    if path not in _PAD_CACHE:
        root = sexpr.parse(path.read_text(encoding='utf-8'))
        pads = set()
        for pad in sexpr.find_all(root, 'pad'):
            layers = sexpr.find(pad, 'layers') or []
            if pad[1] and any(str(la).endswith(COPPER_LAYER_SUFFIX) for la in layers[1:]):
                pads.add(pad[1])
        _PAD_CACHE[path] = pads
    return _PAD_CACHE[path]


def check_pads(spec, parts, nl):
    libs, errs = project_fp_libs(), []
    for ref, comp in sorted(nl['comps'].items()):
        path = footprint_file(comp['footprint'], libs)
        if not path.exists():
            continue                                    # check_footprint_files reports it
        pads, sym = footprint_pads(path), comp['sympins']
        errs += [f'{ref}.{p}: symbol pin has no pad in {comp["footprint"]}' for p in sorted(sym - pads)]
        errs += [f'{ref}: footprint pad {p} has no symbol pin' for p in sorted(pads - sym)]
    return errs


def check_pins(spec, parts, nl):
    errs = []
    for ref, s in spec.items():
        got = nl['pins'].get(ref, {})
        for pin, net in s['pins'].items():
            if pin not in got:
                errs.append(f'{ref}.{pin}: not in the netlist')
            elif got[pin] != net:
                errs.append(f'{ref}.{pin}: net {got[pin] or NC_TEXT}, SPEC {net or NC_TEXT}')
        errs += [f'{ref}.{pin}: pin not in SPEC 7 (net {got[pin] or NC_TEXT})' for pin in got if pin not in s['pins']]
    return errs


def check_nets(spec, parts, nl):
    want = {n for s in spec.values() for n in s['pins'].values() if n is not NC}
    return ([f'extra net {n}' for n in sorted(nl['nets'] - want)]
            + [f'net {n} missing' for n in sorted(want - nl['nets'])])


def check_fields(spec, parts, nl):
    errs = []
    for ref, comp in sorted(nl['comps'].items()):
        p = parts.get(ref)
        if p and p['mpn'] and comp['fields'].get('MPN') != p['mpn']:
            errs.append(f'{ref}: MPN {comp["fields"].get("MPN")!r}, Parts table {p["mpn"]!r}')
        if p and p['datasheet'] and comp['datasheet'] != KIPRJMOD + p['datasheet']:
            errs.append(f'{ref}: Datasheet {comp["datasheet"]!r}, Parts table {p["datasheet"]!r}')
        ds = comp['datasheet']
        if ds.startswith(KIPRJMOD) and not (ROOT / ds[len(KIPRJMOD):]).exists():
            errs.append(f'{ref}: Datasheet file {ds} missing')
    return errs


CHECKS = (check_refs, check_values, check_footprints, check_footprint_files, check_pads, check_pins, check_nets,
          check_fields)


def run_checks(spec, parts, nl):
    board = board_view(nl)
    return {c.__name__: c(spec, parts, board) for c in CHECKS}


# ---------------------------------------------------------------- selftest

def _first(nl, ref_pred=lambda r: True):
    return next(r for r in sorted(nl['comps']) if ref_pred(r))


def mutations(spec, parts, nl):
    """(name, check expected to fail, mutated netlist copy)."""
    out = []

    def mut(name, check, fn):
        m = copy.deepcopy(nl)
        fn(m)
        out.append((name, check, m))

    bv = board_view(nl)                      # pick the mutated parts among the board parts
    ref = _first(bv)
    mpn_ref = next(r for r in sorted(parts) if parts[r]['mpn'] and r in bv['comps'])
    ds_ref = next(r for r in sorted(parts) if parts[r]['datasheet'] and r in bv['comps'])
    two_net = next(r for r in sorted(spec) if len({n for n in spec[r]['pins'].values() if n}) >= 2)
    pin_a, pin_b = [p for p, n in spec[two_net]['pins'].items() if n][:2]
    nc_ref, nc_pin = next((r, p) for r in sorted(spec) for p, n in spec[r]['pins'].items() if n is NC)
    three_pin = next(r for r in sorted(bv['comps']) if len(bv['comps'][r]['sympins']) == 3)
    two_pin = next(r for r in sorted(bv['comps']) if len(bv['comps'][r]['sympins']) == 2)
    some_net = sorted(bv['nets'])[0]
    mut('drop a part', 'check_refs', lambda m: (m['comps'].pop(ref), m['pins'].pop(ref, None)))
    mut('extra part', 'check_refs', lambda m: m['comps'].__setitem__('R99', dict(m['comps'][ref])))
    mut('wrong value', 'check_values', lambda m: m['comps'][ref].__setitem__('value', 'X'))
    mut('wrong footprint', 'check_footprints',
        lambda m: m['comps'][ref].__setitem__('footprint', 'Resistor_SMD:R_0402_1005Metric'))
    mut('missing footprint file', 'check_footprint_files',
        lambda m: m['comps'][ref].__setitem__('footprint', 'Resistor_SMD:R_DOES_NOT_EXIST'))
    mut('symbol pin without a pad', 'check_pads',
        lambda m: m['comps'][three_pin].__setitem__('footprint', SELFTEST_FP_2PAD))
    mut('pad without a symbol pin', 'check_pads',
        lambda m: m['comps'][two_pin].__setitem__('footprint', SELFTEST_FP_3PAD))
    mut('pin on the wrong net', 'check_pins',
        lambda m: m['pins'][two_net].__setitem__(pin_a, m['pins'][two_net][pin_b]))
    mut('NC pin connected', 'check_pins', lambda m: m['pins'][nc_ref].__setitem__(nc_pin, 'GND'))
    mut('pin missing', 'check_pins', lambda m: m['pins'][two_net].pop(pin_a))
    mut('extra pin', 'check_pins', lambda m: m['pins'][two_net].__setitem__('99', 'GND'))
    mut('extra net', 'check_nets', lambda m: m['nets'].add('NET_NOT_IN_SPEC'))
    mut('net missing', 'check_nets', lambda m: m['nets'].discard(some_net))
    if SELFTEST_CMP[0] in spec:
        r, a, b = SELFTEST_CMP
        mut('U1A inputs swapped', 'check_pins',
            lambda m: m['pins'][r].update({a: m['pins'][r][b], b: m['pins'][r][a]}))
        r, power_pins = SELFTEST_CMP_POWER
        mut('U1 power unit missing', 'check_pins', lambda m: [m['pins'][r].pop(p) for p in power_pins])
        mut('U1 on a 14-pin package', 'check_pads',
            lambda m: m['comps'][r].__setitem__('footprint', SELFTEST_FP_14PAD))
    if SELFTEST_DIODE[0] in spec:
        r, a, b = SELFTEST_DIODE
        mut('D4 reversed', 'check_pins', lambda m: m['pins'][r].update({a: m['pins'][r][b], b: m['pins'][r][a]}))
    if SELFTEST_TMR in spec:
        r = SELFTEST_TMR
        for a, b, name in SELFTEST_TMR_SWAPS:
            mut(name, 'check_pins', lambda m, a=a, b=b: m['pins'][r].update({a: m['pins'][r][b], b: m['pins'][r][a]}))
        rr, pin, net = SELFTEST_TMR_SUPPLY
        mut('U5 VDD on VOUT (R30 / D7 bypassed)', 'check_pins', lambda m: m['pins'][rr].__setitem__(pin, net))
        mut('U5 on an 8-pin package', 'check_pads',
            lambda m: m['comps'][r].__setitem__('footprint', SELFTEST_FP_8PAD))
    if SELFTEST_CLAMP_DIODE[0] in spec:
        r, a, b = SELFTEST_CLAMP_DIODE
        mut('D7 zener reversed', 'check_pins', lambda m: m['pins'][r].update({a: m['pins'][r][b], b: m['pins'][r][a]}))
    if SELFTEST_HOLD_FET[0] in spec:
        r, a, b = SELFTEST_HOLD_FET
        mut('Q5 gate / drain swapped', 'check_pins',
            lambda m: m['pins'][r].update({a: m['pins'][r][b], b: m['pins'][r][a]}))
    if SELFTEST_BLEED in spec:
        mut('R31 bleed missing', 'check_refs',
            lambda m: (m['comps'].pop(SELFTEST_BLEED), m['pins'].pop(SELFTEST_BLEED, None)))
    if SELFTEST_SIM_ONLY in nl['comps']:
        mut('real part flagged sim-only (excluded from board and BOM)', 'check_refs',
            lambda m: m['comps'][SELFTEST_SIM_ONLY].__setitem__('sim_only', True))
    mut('wrong MPN', 'check_fields', lambda m: m['comps'][mpn_ref]['fields'].__setitem__('MPN', 'WRONG'))
    mut('wrong datasheet', 'check_fields',
        lambda m: m['comps'][ds_ref].__setitem__('datasheet', KIPRJMOD + 'ref/datasheets/missing.pdf'))
    return out


def selftest(spec, parts, nl):
    base = run_checks(spec, parts, nl)
    if any(base.values()):
        print('selftest: the unmutated netlist must pass first')
        return 1
    if spec['J2']['pins'].get('SH') != 'GND' or spec['U8']['pins'].get('7') is not NC \
            or spec['D6']['pins'].get('2') is not NC or spec['SW1']['pins'].get('2') != 'BATT' \
            or len(spec['J2']['pins']) != 19 or spec['J5']['value'] != 'ACC_N GND' \
            or len(spec['U5']['pins']) != 14 or spec['U5']['pins'].get('4') is not NC \
            or spec['U5']['pins'].get('14') != 'VDD_TMR' \
            or any(spec.get(ref, {}).get('pins') != pins for ref, pins in SELFTEST_SUPPLY_SPOT.items()):
        print('selftest: SPEC parser spot checks failed (J2 SH/19 pins, U8.7 / D6.2 NC, SW1.2, J5 value, U5 14 '
              'pins / pin 4 NC / VDD on VDD_TMR, D7 / R30 / R31 pins)')
        return 1
    fails = 0
    for name, check, m in mutations(spec, parts, nl):
        caught = run_checks(spec, parts, m)[check]
        print(f'  {"ok  " if caught else "MISS"} {name}: {check} -> {caught[0] if caught else "no error"}')
        fails += not caught
    print(f'selftest: {len(mutations(spec, parts, nl)) - fails} caught, {fails} missed')
    return 1 if fails else 0


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--netlist', type=pathlib.Path, help='kicadxml netlist (default: export to build/)')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args(argv[1:])
    md = SPEC.read_text(encoding='utf-8')
    spec, parts = parse_netlist_table(md), parse_parts_table(md)
    path = a.netlist
    if path is None:
        path = NETLIST
        export_netlist(path)
    nl = read_netlist(path)
    if a.selftest:
        return selftest(spec, parts, nl)
    res = run_checks(spec, parts, nl)
    n = 0
    for name, errs in res.items():
        print(f'{name}: {"ok" if not errs else f"{len(errs)} error(s)"}')
        for e in errs:
            print(f'    {e}')
        n += len(errs)
    print(f'check_netlist: {len(spec)} parts, {sum(len(s["pins"]) for s in spec.values())} pins, '
          f'{len(nl["nets"])} nets: {n} error(s)')
    return 1 if n else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
