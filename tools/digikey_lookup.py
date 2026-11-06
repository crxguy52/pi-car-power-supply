"""Digi-Key part lookup (Product Information API v4): status, stock, Digi-Key PN, prices, datasheet.

Adapted from the Turbogen SLAB tool for the Pi power HAT. Stdlib only; run from the project root:

    pdm run dk-mpn SE555D [MPN ...]   # one block per MPN
    pdm run dk-check                  # every row of the SPEC "Parts" table: active, stocked, DK PN
    pdm run dk-bom                    # bom/: Digi-Key BOM Manager CSV + PIPWR_BOM.md
    python -I tools/digikey_lookup.py [--json] [--refresh] [--boards N] [--spares F] mpn <MPN...>
    python -I tools/digikey_lookup.py [...] check [spec.md]
    python -I tools/digikey_lookup.py [...] bom [spec.md] [--out bom]

Credentials: DIGIKEY_CLIENT_ID / DIGIKEY_CLIENT_SECRET. On Windows the user registry (HKCU\\Environment, what
`setx` writes) wins over the process environment. The credentials and the access token are never printed, logged
or written to disk. Responses are cached in build/digikey_cache/ for CACHE_MAX_AGE_S; --refresh ignores the cache.

Spec tables: any markdown table with an 'MPN' column. The Parts table has a 'Ref' column (one or more refs,
comma-separated): its ref count is the per-board quantity. The cut-tape rule (an SMD row's DK PN must be the
cut-tape variant) still applies: cut tape is what small quantities ship in. Mount 'SMD (tube)' (or any Mount other
than 'SMD') takes any Digi-Key-stocked packaging: an SMD part whose cut tape is not stocked, bought in its tube.
`check` exits 1 on any problem (unknown MPN, not Active, stock below the order quantity, DK PN, manufacturer, a
chip-size Package (e.g. 0805) or a resistor / capacitor / LED Value different from Digi-Key (value; tolerance,
power, TCR, voltage and dielectric where the Value text states them), a Marketplace listing, a non-cut-tape SMD
DK PN). Order quantity: refs x --boards plus spares (Spares column: 'yes' / default = --spares fraction rounded up,
at least SPARES_MIN_DEFAULT; '+N' = N; 'no' = none). Rows whose MPN is TBD are SKIP; Status 'pending owner' rows are
PEND; Status 'order at ...' rows are EXT (bought elsewhere); rows whose first cell is struck out (~~...~~) are
skipped. `selftest` (pdm run dk-selftest): offline checks of that parsing.
"""
import argparse
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / 'docs' / 'SPEC.md'
CACHE_DIR = ROOT / 'build' / 'digikey_cache'
BOM_DIR = ROOT / 'bom'
BOM_CSV, BOM_MD = 'PIPWR_BOM_digikey.csv', 'PIPWR_BOM.md'
DK_CSV_HEADER = ['Digi-Key Part Number', 'Manufacturer Part Number', 'Manufacturer', 'Quantity',
                 'Reference Designator', 'Customer Reference', 'Description']
CUSTOMER_REF_MAX = 48                      # Digi-Key Customer Reference field length (assumption, not verified)
CUSTOMER_REF_PREFIX = 'PIPWR '
CSV_ASCII = {'Ω': 'Ohm', 'µ': 'u', '×': 'x', '–': '-', '—': '-', '−': '-', '→': '->', '≥': '>=', '≤': '<=',
             '±': '+/-', '°': 'deg', '·': '*', '≈': '~', '²': '^2', '≪': '<<'}
NON_ASCII = re.compile(r'[^\x00-\x7f]')
BOM_HEADING = 'Parts'                     # spec section of the board part table
SECTION_NUMBER = re.compile(r'^\d+(?:\.\d+)*\.?\s+')   # '6. Parts' -> 'Parts'

# order quantities: two boards plus spares, override with --boards / --spares
BOARDS_DEFAULT = 2
SPARE_FRACTION_DEFAULT = 0.10
SPARES_MIN_DEFAULT = 5                     # 'yes' rows: at least this many spares (cheap passives, hand assembly)
ROUND_DIGITS = 6                           # float noise before rounding a quantity up

TOKEN_URL = 'https://api.digikey.com/v1/oauth2/token'
DETAILS_URL = 'https://api.digikey.com/products/v4/search/{mpn}/productdetails'
KEYWORD_URL = 'https://api.digikey.com/products/v4/search/keyword'
KEYWORD_LIMIT = 10
ENV_ID, ENV_SECRET = 'DIGIKEY_CLIENT_ID', 'DIGIKEY_CLIENT_SECRET'
REG_KEY = 'Environment'                    # HKCU\Environment: user variables set by setx
LOCALE = {'X-DIGIKEY-Locale-Site': 'US', 'X-DIGIKEY-Locale-Language': 'en', 'X-DIGIKEY-Locale-Currency': 'USD'}

TIMEOUT_S = 30.0
CACHE_MAX_AGE_S = 86.4e3                   # one day: stock moves, but not within a work session
CALL_SPACING_S = 0.6                       # stays under the per-minute burst limit
RETRY_LIMIT = 3                            # on HTTP 429 (rate limit), waiting Retry-After
RETRY_DEFAULT_S = 10.0
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_TOO_MANY = 429

ACTIVE = 'Active'
CUT_TAPE = 'Cut Tape (CT)'
PRICE_BREAKS = (1, 10, 100)
TBD = 'TBD'
KEY_PARAMETERS = ('Resistance', 'Capacitance', 'Tolerance', 'Power (Watts)', 'Composition',
                  'Temperature Coefficient', 'Voltage - Rated', 'Package / Case', 'Operating Temperature', 'Ratings',
                  'Color', 'Voltage - Forward (Vf) (Typ)', 'Current - Test',
                  'Wavelength - Dominant', 'Millicandela Rating', 'Lens Style', 'Height (Max)')

# spec MPN tables: column names (header cells, case-insensitive)
COL_MPN, COL_DK, COL_QTY, COL_MFR = 'mpn', 'digi-key pn', 'qty', 'manufacturer'
COL_VALUE, COL_PACKAGE = 'value', 'package'
COL_PART, COL_ITEM, COL_FUNCTIONS, COL_FITTED = 'part', 'item', 'functions', 'fitted / dnp'
COL_REF, COL_FUNCTION = 'ref', 'function'   # Parts table: refs of one board, what the part does
COL_MOUNT, COL_SPARES, COL_STATUS, COL_ORDER, COL_SOURCE = 'mount', 'spares', 'status', 'order qty', 'source'
MOUNT_SMD = 'SMD'                          # cut-tape rule; other mounts: 'THT', 'loose'
SPARES_YES, SPARES_NO = 'yes', 'no'
SOURCE_DIGIKEY = 'Digi-Key'
STATUS_ORDER = 'order'                     # in the CSV
STATUS_PENDING = 'pending owner'           # PEND in dk-check; its recommended alternate goes into the CSV
STATUS_ALT_RECOMMENDED = 'alt (recommended)'
STATUS_REMOVE = 'remove pending'           # owner will remove the part: checked, not ordered
STATUS_ALT = 'alt'                         # second option: checked, not in the CSV
STATUS_SUPERSEDED = 'superseded'           # still on the schematic, being replaced: checked, not in the CSV
STATUS_EXTERNAL = 'order at'               # e.g. 'order at Mouser/Arrow (owner)': bought elsewhere, EXT, not in the CSV
STRUCK = '~~'                              # a row whose first cell is struck out is history: never parsed
NONE = '-'
PAR_RESISTANCE, PAR_PACKAGE, PAR_COLOR = 'Resistance', 'Package / Case', 'Color'
PAR_CAPACITANCE, PAR_TOLERANCE, PAR_POWER = 'Capacitance', 'Tolerance', 'Power (Watts)'
PAR_VOLTAGE, PAR_TEMPCO = 'Voltage - Rated', 'Temperature Coefficient'
EIA_SIZE = re.compile(r'\d{4}')            # imperial chip size ('0805'): the only Package text compared with Digi-Key
SPARES_EXTRA = re.compile(r'\+\s*(\d+)')   # Spares cell '+2': exactly that many spares
SI_PREFIX = {'': 1.0, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6, 'm': 1e-3, 'k': 1e3, 'K': 1e3, 'M': 1e6}
RE_OHMS = re.compile(r'(\d+(?:\.\d+)?)\s*([kKM]?)\s*(?:Ω|Ohms?)')
RE_FARADS = re.compile(r'(\d+(?:\.\d+)?)\s*([pnuµ])F')
RE_VOLTS = re.compile(r'(\d+(?:\.\d+)?)\s*V\b')
RE_PERCENT = re.compile(r'(\d+(?:\.\d+)?)\s*%')
RE_WATTS = re.compile(r'(\d+(?:\.\d+)?)\s*W\b')
RE_PPM = re.compile(r'(\d+(?:\.\d+)?)\s*ppm')
RE_DIELECTRIC = re.compile(r'\b(C0G|NP0|X7R|X5R|X7S|X6S|X8R)\b')
REL_TOL = 1e-6                             # value comparison after unit conversion


class DigiKeyError(Exception):
    """A lookup that could not be completed (network, credentials, HTTP)."""


# ---------------------------------------------------------------------------
# Credentials and HTTP
# ---------------------------------------------------------------------------

def _registry_value(name):
    if os.name != 'nt':
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
            return str(winreg.QueryValueEx(k, name)[0]) or None
    except OSError:
        return None


def credentials():
    """(client_id, client_secret): registry first (authoritative after setx), then the environment."""
    vals = [_registry_value(n) or os.environ.get(n) for n in (ENV_ID, ENV_SECRET)]
    if not all(vals):
        missing = [n for n, v in zip((ENV_ID, ENV_SECRET), vals) if not v]
        raise DigiKeyError(f'missing credentials {missing}: see docs/SETUP.md "Digi-Key API (part lookup)"')
    return vals[0], vals[1]


class DigiKey:
    def __init__(self, refresh=False):
        self.refresh = refresh
        self._cid = self._secret = self._token = None
        self._last_call = 0.0

    def _open(self, req):
        for attempt in range(RETRY_LIMIT + 1):
            wait = CALL_SPACING_S - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == HTTP_TOO_MANY and attempt < RETRY_LIMIT:
                    retry = e.headers.get('Retry-After') or ''
                    time.sleep(float(retry) if re.fullmatch(r'\d+(\.\d+)?', retry) else RETRY_DEFAULT_S)
                    continue
                raise
        raise DigiKeyError('rate limit: retries exhausted')

    def _auth(self):
        if self._token:
            return
        self._cid, self._secret = credentials()
        body = urllib.parse.urlencode({'client_id': self._cid, 'client_secret': self._secret,
                                       'grant_type': 'client_credentials'}).encode()
        req = urllib.request.Request(TOKEN_URL, data=body, method='POST',
                                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            self._token = self._open(req)['access_token']
        except urllib.error.HTTPError as e:     # message only: the request body holds the secret
            raise DigiKeyError(f'token request: HTTP {e.code} (sandbox credentials on the production '
                               f'endpoint, or a wrong/expired secret?)') from None

    def _api(self, url, body=None):
        """JSON response of one API call; a rejected (expired) access token is renewed once."""
        for renew in (False, True):
            self._auth()
            headers = {'Authorization': f'Bearer {self._token}', 'X-DIGIKEY-Client-Id': self._cid, **LOCALE}
            if body is not None:
                headers['Content-Type'] = 'application/json'
            req = urllib.request.Request(url, data=body, headers=headers, method='GET' if body is None else 'POST')
            try:
                return self._open(req)
            except urllib.error.HTTPError as e:
                if e.code != HTTP_UNAUTHORIZED or renew:
                    raise
                self._token = None

    def product(self, mpn):
        """Product dict for an exact MPN, or None if Digi-Key does not know it. Cached in build/."""
        cache = CACHE_DIR / (re.sub(r'[^A-Za-z0-9._-]', '_', mpn) + '.json')
        if not self.refresh and cache.exists() and time.time() - cache.stat().st_mtime < CACHE_MAX_AGE_S:
            return json.loads(cache.read_text(encoding='utf-8')).get('Product')
        try:
            data = self._api(DETAILS_URL.format(mpn=urllib.parse.quote(mpn, safe='')))
        except urllib.error.HTTPError as e:
            if e.code != HTTP_NOT_FOUND:
                raise DigiKeyError(f'{mpn}: HTTP {e.code}') from None
            # 404 also means "Duplicate Products found" (one MPN listed by several suppliers): keyword search
            data = {'Product': self._keyword_match(mpn)}
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, indent=1), encoding='utf-8')
        return data.get('Product')

    def product_by_dk(self, dk_pn, mpn):
        """Product listing that carries the Digi-Key PN dk_pn for this exact MPN, or None (keyword search, cached).
        For an MPN that several suppliers list (e.g. a MIL part number): the details lookup returns one listing,
        which may not be the one the spec orders."""
        cache = CACHE_DIR / ('dkpn_' + re.sub(r'[^A-Za-z0-9._-]', '_', dk_pn) + '.json')
        if not self.refresh and cache.exists() and time.time() - cache.stat().st_mtime < CACHE_MAX_AGE_S:
            return json.loads(cache.read_text(encoding='utf-8')).get('Product')
        try:
            data = self._api(KEYWORD_URL, json.dumps({'Keywords': dk_pn, 'Limit': KEYWORD_LIMIT}).encode())
        except urllib.error.HTTPError as e:
            raise DigiKeyError(f'{dk_pn}: keyword search HTTP {e.code}') from None
        hit = next((p for p in (data.get('ExactMatches') or []) + (data.get('Products') or [])
                    if (p.get('ManufacturerProductNumber') or '').upper() == mpn.upper()
                    and any(v.get('DigiKeyProductNumber') == dk_pn for v in p.get('ProductVariations') or [])), None)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({'Product': hit}, indent=1), encoding='utf-8')
        return hit

    def _keyword_match(self, mpn):
        """Exact-MPN product from a keyword search, or None: the Digi-Key-stocked listing (one with a cut-tape
        variation) first, then the largest stock."""
        try:
            data = self._api(KEYWORD_URL, json.dumps({'Keywords': mpn, 'Limit': KEYWORD_LIMIT}).encode())
        except urllib.error.HTTPError as e:
            raise DigiKeyError(f'{mpn}: keyword search HTTP {e.code}') from None
        hits = [p for p in (data.get('ExactMatches') or []) + (data.get('Products') or [])
                if (p.get('ManufacturerProductNumber') or '').upper() == mpn.upper()]
        return max(hits, key=lambda p: (_variation(p, CUT_TAPE) is not None, p.get('QuantityAvailable') or 0),
                   default=None)


# ---------------------------------------------------------------------------
# Product summary
# ---------------------------------------------------------------------------

def _variation(p, package):
    return next((v for v in p.get('ProductVariations') or []
                 if (v.get('PackageType') or {}).get('Name') == package), None)


def _variation_rank(v):
    """Cut tape first, then Digi-Key-stocked packagings by stock, Marketplace listings last."""
    ct = (v.get('PackageType') or {}).get('Name') == CUT_TAPE
    return (not ct, bool(v.get('MarketPlace')), -(v.get('QuantityAvailableforPackageType') or 0))


def _price_at(pricing, qty):
    """Unit price at quantity qty from a list of {BreakQuantity, UnitPrice}, or None below the first break."""
    best = None
    for b in sorted(pricing or [], key=lambda b: b.get('BreakQuantity', 0)):
        if b.get('BreakQuantity', 0) <= qty:
            best = b.get('UnitPrice')
    return best


def summary(mpn, p):
    """Flat dict of what the tool reports for one MPN (p = API Product or None)."""
    if p is None:
        return {'mpn': mpn, 'found': False}
    exact = (p.get('ManufacturerProductNumber') or '').upper() == mpn.upper()
    variations = sorted(p.get('ProductVariations') or [], key=_variation_rank)
    ct = variations[0] if variations else {}      # cut tape, else the best-stocked Digi-Key packaging
    stock = p.get('QuantityAvailable')
    if stock is None:
        # v4 may leave it null: use the per-packaging stock; reel, cut tape and Digi-Reel share one pool, so no sum
        stock = max((v.get('QuantityAvailableforPackageType') or 0 for v in variations), default=0)
    params = {q.get('ParameterText'): q.get('ValueText') for q in p.get('Parameters') or []}
    return {
        'mpn': mpn, 'found': exact,
        'api_mpn': p.get('ManufacturerProductNumber'),
        'manufacturer': (p.get('Manufacturer') or {}).get('Name'),
        'description': (p.get('Description') or {}).get('ProductDescription'),
        'status': (p.get('ProductStatus') or {}).get('Status'),
        'stock': stock,
        'dk_pn': ct.get('DigiKeyProductNumber'),
        'dk_package': (ct.get('PackageType') or {}).get('Name'),
        'dk_package_stock': ct.get('QuantityAvailableforPackageType'),
        'has_cut_tape': _variation(p, CUT_TAPE) is not None,
        'variations': [{'dk_pn': v.get('DigiKeyProductNumber'), 'package': (v.get('PackageType') or {}).get('Name'),
                        'stock': v.get('QuantityAvailableforPackageType'), 'moq': v.get('MinimumOrderQuantity'),
                        'marketplace': bool(v.get('MarketPlace')),
                        'supplier': (v.get('Supplier') or {}).get('Name'),
                        'pricing': v.get('StandardPricing') or []}
                       for v in variations],
        'prices': {q: _price_at(ct.get('StandardPricing'), q) for q in PRICE_BREAKS},
        'datasheet': p.get('DatasheetUrl'),
        'parameters': {k: params[k] for k in KEY_PARAMETERS if k in params},
    }


def _summary_variation(s, dk_pn):
    return next((v for v in s.get('variations') or [] if v['dk_pn'] == dk_pn), None)


def print_summary(s):
    if not s['found']:
        other = f" (API returned {s['api_mpn']})" if s.get('api_mpn') else ''
        print(f"{s['mpn']}: NOT FOUND on Digi-Key{other}")
        return
    price = ', '.join(f"{q}: {'-' if v is None else f'${v:.4f}'}" for q, v in s['prices'].items())
    print(f"{s['mpn']}  ({s['manufacturer']})  {s['description']}")
    print(f"  status   : {s['status']}")
    print(f"  stock    : {s['stock']}  ({s['dk_package']}: {s['dk_package_stock']})")
    print(f"  Digi-Key : {s['dk_pn']}  [{s['dk_package']}]"
          + ('' if s['has_cut_tape'] else f'  (no {CUT_TAPE} variant: fine for THT parts, not for SMD)'))
    print(f"  price    : {price}")
    for v in s['variations']:
        mkt = f"  MARKETPLACE ({v['supplier']})" if v['marketplace'] else ''
        print(f"  packaging: {str(v['dk_pn']):30s} {str(v['package']):18s} stock {v['stock']}, MOQ {v['moq']}{mkt}")
    print(f"  datasheet: {s['datasheet']}")
    for k, v in s['parameters'].items():
        print(f"  {k:25s}: {v}")


# ---------------------------------------------------------------------------
# Spec tables
# ---------------------------------------------------------------------------

def _cells(line):
    body = line.strip().strip('|')
    return [c.strip() for c in body.split('|')]


def _clean(cell):
    return cell.replace('**', '').strip()          # bold only: a single * is a Functions wildcard


def _untick(cell):
    return cell.replace('`', '').strip()


def spec_rows(md):
    """Rows of every markdown table whose header has an 'MPN' column: dicts keyed by lower-case header, plus
    '_heading' (the nearest ## / ### heading above the table). Cells keep their backticks (Functions patterns).
    Rows whose first cell is struck out (~~...~~) are skipped."""
    rows, header, heading = [], None, ''
    for line in md.splitlines():
        m = re.match(r'^#{2,6}\s+(.*)$', line)
        if m:
            heading = m.group(1).strip()
        if not line.strip().startswith('|'):
            header = None
            continue
        cells = [_clean(c) for c in _cells(line)]
        if header is not None and cells and cells[0].startswith(STRUCK):
            continue                               # struck-out (superseded) row, as tools/check_pcb.py
        if header is None:
            header = [_untick(c).lower() for c in cells]
            continue
        if all(re.fullmatch(r':?-+:?', c) for c in cells if c):
            continue
        if COL_MPN in header:
            row = dict(zip(header, cells))
            row['_heading'] = heading
            rows.append(row)
    return rows


def _get(row, col, default=''):
    return _untick(row.get(col, default) or default)


def row_mount(row):
    """'SMD' (cut-tape rule applies), 'THT' or 'loose'. Tables without a Mount column hold SMD passives."""
    return _get(row, COL_MOUNT, MOUNT_SMD) or MOUNT_SMD


def row_status(row):
    return row_status_text(row).lower()


def row_status_text(row):
    """The Status cell as written (case kept: distributor names), for the BOM tables and notes."""
    return _get(row, COL_STATUS, STATUS_ORDER) or STATUS_ORDER


def row_counts(row):
    """(fitted, dnp) per board (or per harness) from 'Fitted / DNP', else (Qty, 0); None if unreadable."""
    refs = row_ref_list(row)
    if refs:
        return len(refs), 0
    m = re.fullmatch(r'(\d+)\s*/\s*(\d+)', _get(row, COL_FITTED))
    if m:
        return int(m.group(1)), int(m.group(2))
    q = re.match(r'\d+', _get(row, COL_QTY))
    return (int(q.group()), 0) if q else None


def row_ref_list(row):
    """Refs in the row's Ref cell ('R4, R5' -> ['R4', 'R5']); [] without a Ref column."""
    return [r for r in re.split(r'[,\s]+', _get(row, COL_REF)) if r and r != NONE]


def row_spares(row):
    """Spares rule for the row: tables without a Spares column (resistors, LED) take spares."""
    return _get(row, COL_SPARES, SPARES_YES).lower() != SPARES_NO


def spares_for(row, n, spare_fraction, spares_min=SPARES_MIN_DEFAULT):
    """Spares on top of n parts: 'no' none; '+N' exactly N (ICs, connectors); 'yes' (default) the fraction of n
    rounded up, at least spares_min (cheap passives: a dropped 0805 costs more time than the part). None for n = 0."""
    if n == 0:
        return 0
    m = SPARES_EXTRA.fullmatch(_get(row, COL_SPARES, SPARES_YES))
    if m:
        return int(m.group(1))
    if not row_spares(row):
        return 0
    return max(math.ceil(round(n * spare_fraction, ROUND_DIGITS)), spares_min)


def order_split(row, boards, spare_fraction):
    """(placed, dnp_spares) order quantities: fitted x boards plus the row's spares (spares_for), and one board's
    DNP parts as loose spares (not placed) plus theirs. An 'Order qty' cell (harness rows) is all 'placed'. None if
    unreadable."""
    m = re.match(r'\d+', _get(row, COL_ORDER))
    if m:
        return int(m.group()), 0
    counts = row_counts(row)
    if counts is None:
        return None
    fitted, dnp = counts
    n = fitted * boards
    return n + spares_for(row, n, spare_fraction), dnp + spares_for(row, dnp, spare_fraction)


def order_qty(row, boards, spare_fraction):
    """Total quantity to order from Digi-Key (placed + DNP spares): what dk-check compares with the stock."""
    split = order_split(row, boards, spare_fraction)
    return None if split is None else sum(split)


def row_external(row):
    """The row's Status says another distributor (owner buys it): not looked up, not in the Digi-Key CSV."""
    return row_status(row).startswith(STATUS_EXTERNAL)


def row_skip_reason(row):
    """Why dk-check does not look the row up (None = look it up)."""
    mpn = row.get(COL_MPN) or ''
    if not mpn or mpn == NONE or mpn.upper().startswith(TBD):
        return 'MPN TBD'
    src = _get(row, COL_SOURCE)
    if src and src.lower() != SOURCE_DIGIKEY.lower():
        return f'source {src} (not Digi-Key)'
    return None


def check_row(row, s, qty):
    """Problems for one spec row against its lookup summary (empty list = OK). qty = order quantity.

    SMD rows: the spec DK PN must be the cut-tape packaging (board house assembly). THT and loose rows: any
    Digi-Key-stocked packaging (tray, tube, bulk, bag) with stock >= qty and MOQ <= qty. Marketplace (third-party
    seller) packagings fail for every row."""
    if not s['found']:
        return ['not found']
    probs = []
    if s['status'] != ACTIVE:
        probs.append(f"status {s['status']}")
    if qty is None:
        return probs + [f"qty {row.get(COL_QTY)!r} unreadable"]
    smd = row_mount(row).upper() == MOUNT_SMD
    if smd and not s['has_cut_tape']:
        probs.append(f'SMD part without a {CUT_TAPE} variant on Digi-Key (board house assembly takes cut tape)')
    dk = row.get(COL_DK)
    if COL_DK in row and not dk:
        probs.append(f"no spec DK PN (Digi-Key: {s['dk_pn']})")
    if dk:
        v = _summary_variation(s, dk)
        if v is None:
            probs.append(f"spec DK PN {dk} is not a packaging of {s['api_mpn']} (Digi-Key: {s['dk_pn']})")
        else:
            if v['marketplace']:
                probs.append(f"spec DK PN {dk} is a Digi-Key Marketplace listing ({v['supplier']}), "
                             f"not Digi-Key stock")
            if smd and v['package'] != CUT_TAPE:
                probs.append(f"SMD: spec DK PN {dk} is {v['package']}, not {CUT_TAPE} ({s['dk_pn']})")
            elif smd and dk != s['dk_pn']:
                probs.append(f"spec DK PN {dk}, Digi-Key cut tape {s['dk_pn']}")
            if (v['stock'] or 0) < qty:
                probs.append(f"stock {v['stock']} ({v['package']}) < order qty {qty}")
            if (v['moq'] or 1) > qty:
                probs.append(f"MOQ {v['moq']} > order qty {qty}")
    elif (s['stock'] or 0) < qty:
        probs.append(f"stock {s['stock']} < order qty {qty}")
    mfr = row.get(COL_MFR)
    if mfr and mfr.lower() not in (s['manufacturer'] or '').lower():
        probs.append(f"spec manufacturer {mfr}, Digi-Key {s['manufacturer']}")
    par = s['parameters']
    pkg = _get(row, COL_PACKAGE)
    if EIA_SIZE.fullmatch(pkg):                  # chip passives / LED; other Package cells are footprint notes
        if not par.get(PAR_PACKAGE):
            probs.append(f"spec package {pkg}: no '{PAR_PACKAGE}' on Digi-Key")
        elif not par[PAR_PACKAGE].startswith(pkg):
            probs.append(f"spec package {pkg}, Digi-Key {par[PAR_PACKAGE]}")
    return probs + value_problems(row.get(COL_VALUE) or '', par)


def _si(num, prefix):
    return float(num) * SI_PREFIX[prefix]


def _close(a, b):
    return abs(a - b) <= REL_TOL * max(abs(a), abs(b))


def _bound(probs, what, rx, val, dk_text, upper):
    """Spec number in val (if stated) against the Digi-Key text: upper=True means the spec is an upper bound."""
    s, d = rx.search(val), rx.search(dk_text or '')
    if s and (not d or (float(d.group(1)) > float(s.group(1)) if upper else float(d.group(1)) < float(s.group(1)))):
        probs.append(f"spec {what} {s.group(0)}, Digi-Key {dk_text}")


def value_problems(val, par):
    """Spec Value text vs the Digi-Key parameters, for resistors (Resistance), capacitors (Capacitance) and LEDs
    (Color): the value, and where the spec text states them the tolerance and TCR (spec = upper bounds), the power
    and rated voltage (spec = lower bounds) and the dielectric. Other parts (semiconductors, connectors): the Value
    cell is a description and the MPN is the check. Colour: only for a Value without digits (an LED's 'red'; a
    terminal block's housing colour is not its Value)."""
    probs = []
    if PAR_RESISTANCE in par:
        s, d = RE_OHMS.search(val), RE_OHMS.search(par[PAR_RESISTANCE])
        if not s or not d or not _close(_si(*s.groups()), _si(*d.groups())):
            probs.append(f"spec value {val}, Digi-Key {par[PAR_RESISTANCE]}")
        _bound(probs, 'power', RE_WATTS, val, par.get(PAR_POWER), upper=False)
        _bound(probs, 'TCR', RE_PPM, val, par.get(PAR_TEMPCO), upper=True)
    elif PAR_CAPACITANCE in par:
        s, d = RE_FARADS.search(val), RE_FARADS.search(par[PAR_CAPACITANCE])
        if not s or not d or not _close(_si(*s.groups()), _si(*d.groups())):
            probs.append(f"spec value {val}, Digi-Key {par[PAR_CAPACITANCE]}")
        _bound(probs, 'voltage', RE_VOLTS, val, par.get(PAR_VOLTAGE), upper=False)
        s = RE_DIELECTRIC.search(val)
        if s and s.group(1) not in (par.get(PAR_TEMPCO) or ''):
            probs.append(f"spec dielectric {s.group(1)}, Digi-Key {par.get(PAR_TEMPCO)}")
    else:
        if PAR_COLOR in par and val and not re.search(r'\d', val) and val.lower() != par[PAR_COLOR].lower():
            probs.append(f"spec value {val}, Digi-Key colour {par[PAR_COLOR]}")
        return probs
    _bound(probs, 'tolerance', RE_PERCENT, val, par.get(PAR_TOLERANCE), upper=True)
    return probs


def evaluate(dk, rows, boards, spare_fraction):
    """One result dict per spec row: result OK / FAIL / PEND (problems reported, owner decision open) / SKIP."""
    results = []
    for row in rows:
        mpn = row[COL_MPN]
        qty = order_qty(row, boards, spare_fraction)
        split = order_split(row, boards, spare_fraction) or (None, None)
        skip = row_skip_reason(row)
        if not skip and row_external(row):
            dk_pn = _get(row, COL_DK, NONE) or NONE
            if dk_pn != NONE:      # an external row is never looked up: a Digi-Key PN on it would go unchecked
                results.append({'mpn': mpn, 'result': 'FAIL', 'row': row, 'qty': qty, 'placed': split[0],
                                'spares': split[1], 'problems': [f"external source with a Digi-Key PN {dk_pn}: "
                                                                 f"write '{NONE}' or order it from Digi-Key"]})
                continue
            results.append({'mpn': mpn, 'result': 'EXT', 'problems': [f'external source: {row_status_text(row)}'],
                            'row': row, 'qty': qty, 'placed': split[0], 'spares': split[1]})
            continue
        if skip:
            results.append({'mpn': mpn or '-', 'result': 'SKIP', 'problems': [skip], 'row': row, 'qty': qty,
                            'placed': split[0], 'spares': split[1]})
            continue
        s = summary(mpn, dk.product(mpn))
        dk_spec = _get(row, COL_DK, NONE) or NONE
        if dk_spec != NONE and s['found'] and _summary_variation(s, dk_spec) is None:
            alt = dk.product_by_dk(dk_spec, mpn)       # the spec orders another supplier's listing of the MPN
            if alt is not None:
                s = summary(mpn, alt)
        probs = check_row(row, s, qty)
        pending = STATUS_PENDING in row_status(row)
        result = 'OK' if not probs else ('PEND' if pending else 'FAIL')
        results.append({'mpn': mpn, 'result': result, 'problems': probs, 'row': row, 'lookup': s, 'qty': qty,
                        'placed': split[0], 'spares': split[1]})
    return results


def cmd_check(dk, spec_path, as_json, boards, spare_fraction):
    rows = spec_rows(pathlib.Path(spec_path).read_text(encoding='utf-8'))
    if not rows:
        print(f'{spec_path}: no table with an MPN column')
        return 1
    results = evaluate(dk, rows, boards, spare_fraction)
    bad = sum(r['result'] == 'FAIL' for r in results)
    pend = sum(r['result'] == 'PEND' for r in results)
    if as_json:
        print(json.dumps([{k: v for k, v in r.items()} for r in results], indent=1, default=str))
    else:
        print(f"{'MPN':26s} {'spec Digi-Key PN':30s} {'mount':5s} {'order':>5s} {'stock':>9s} {'status':8s} result")
        for r in results:
            s = r.get('lookup') or {}
            row = r['row']
            print(f"{r['mpn'][:26]:26s} {str(row.get(COL_DK) or '-')[:30]:30s} {row_mount(row)[:5]:5s} "
                  f"{str(r['qty']):>5s} {str(s.get('stock', '-')):>9s} {str(s.get('status') or '-')[:8]:8s} "
                  f"{r['result']}" + (f"  ({'; '.join(r['problems'])})" if r['problems'] else ''))
        print(f"{'FAIL' if bad else 'PASS'}: {len(results)} MPN rows ({boards} boards, {_spares_text(spare_fraction)}"
              f"), {bad} with problems, {pend} pending owner (not counted), "
              f"{sum(r['result'] == 'EXT' for r in results)} external source (owner orders), "
              f"{sum(r['result'] == 'SKIP' for r in results)} skipped")
    return 1 if bad else 0


# ---------------------------------------------------------------------------
# BOM files
# ---------------------------------------------------------------------------

def _unit_price(r, qty=None):
    """Digi-Key unit price of the spec DK PN at qty (default: the row's total order quantity)."""
    s, row = r.get('lookup') or {}, r['row']
    qty = r['qty'] if qty is None else qty
    v = _summary_variation(s, row.get(COL_DK)) if s else None
    return _price_at(v['pricing'], qty) if v and qty else None


def _in_csv(row):
    st = row_status(row)
    if st.startswith(STATUS_ALT_RECOMMENDED):
        return True
    return STATUS_PENDING not in st and not any(st.startswith(x) for x in (STATUS_ALT, STATUS_SUPERSEDED,
                                                                          STATUS_REMOVE, STATUS_EXTERNAL))


def _part(row):
    return _get(row, COL_PART) or _get(row, COL_ITEM) or _get(row, COL_FUNCTION)


def _part_text(row):
    part, value, pkg = _part(row), _get(row, COL_VALUE), _get(row, COL_PACKAGE)
    if value and value.lower() in part.lower():
        value = ''                                  # 'LED, green' + 'green'
    return ' '.join(p for p in (part, value, pkg) if p and p != NONE)


def _ascii(text):
    """CSV text without non-ASCII symbols: BOM Manager / Excel may not read the file as UTF-8."""
    for k, v in CSV_ASCII.items():
        text = text.replace(k, v)
    left = sorted(set(NON_ASCII.findall(text)))
    if left:
        raise DigiKeyError(f'CSV text {text[:40]!r}: no ASCII mapping for {left} (add them to CSV_ASCII)')
    return text


def _customer_ref(row):
    return _ascii(CUSTOMER_REF_PREFIX + _part_text(row))[:CUSTOMER_REF_MAX]


def _description(row):
    text = _part_text(row)
    st = row_status(row)
    if st != STATUS_ORDER:
        text += f' [{st}]'
    return text


def write_bom(results, out_dir, boards, spare_fraction):
    """bom/PIPWR_BOM_digikey.csv (Digi-Key BOM Manager upload) and bom/PIPWR_BOM.md from the Parts rows."""
    import csv
    out_dir.mkdir(parents=True, exist_ok=True)
    board = [r for r in results if SECTION_NUMBER.sub('', r['row']['_heading']) == BOM_HEADING]
    total, md = 0.0, []
    with open(out_dir / BOM_CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(DK_CSV_HEADER)
        for r in board:
            row = r['row']
            q = r.get('placed') or 0
            price = _unit_price(r, q) if q else None
            line = price * q if price is not None else None
            if _in_csv(row) and r['result'] != 'SKIP' and q:
                total += line or 0.0
                w.writerow([row.get(COL_DK, ''), r['mpn'], row.get(COL_MFR, ''), q, ' '.join(row_ref_list(row)),
                            _customer_ref(row), _ascii(_description(row))])
            md.append((r, q, price, line))
    write_bom_md(out_dir / BOM_MD, md, total, boards, spare_fraction)
    return total


def _spares_text(spare_fraction):
    return (f"spares: Spares 'yes' rows {spare_fraction:.0%} rounded up, at least {SPARES_MIN_DEFAULT}; "
            "'+N' rows N; 'no' rows none")


def _money(v):
    return '-' if v is None else f'{v:,.2f}'


def write_bom_md(path, md, total, boards, spare_fraction):
    stamp = time.strftime('%Y-%m-%d')
    lines = [
        '# Pi power HAT: bill of materials (Digi-Key)', '',
        f'Generated {stamp} by `pdm run dk-bom` (tools/digikey_lookup.py) from the "Parts" table in '
        '[docs/SPEC.md](../docs/SPEC.md). Do not edit: change the spec and re-run. Stock and prices: Digi-Key API '
        'on the day.', '',
        f'- {boards} boards; {_spares_text(spare_fraction)}. Price = unit price at the order quantity.',
        f'- `{BOM_CSV}`: Digi-Key BOM Manager upload; Quantity is the total order quantity (build quantity 1).', '',
        f'**Order total: ${total:,.2f}**', '',
        '| Status | Part | Refs | Order | Manufacturer | MPN | Digi-Key PN | Stock | Unit $ | Line $ | dk-check |',
        '|---|---|---|---|---|---|---|---|---|---|---|']
    for r, q, price, line in md:
        row = r['row']
        stock = (r.get('lookup') or {}).get('stock', '-')
        chk = r['result'] + (f": {'; '.join(r['problems'])}" if r['problems'] else '')
        lines.append(f"| {row_status_text(row)} | {_part_text(row)} | {' '.join(row_ref_list(row)) or '-'} | {q} | "
                     f"{row.get(COL_MFR, '')} | {r['mpn']} | {row.get(COL_DK) or '-'} | {stock} | {_money(price)} | "
                     f"{_money(line)} | {chk} |")
    lines.append('')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))


def cmd_bom(dk, spec_path, out_dir, boards, spare_fraction):
    rows = spec_rows(pathlib.Path(spec_path).read_text(encoding='utf-8'))
    results = evaluate(dk, rows, boards, spare_fraction)
    total = write_bom(results, pathlib.Path(out_dir), boards, spare_fraction)
    bad = sum(r['result'] == 'FAIL' for r in results)
    print(f"{'FAIL' if bad else 'PASS'}: {BOM_CSV}, {BOM_MD} in {out_dir}; ${total:,.2f} ({boards} boards); "
          f"{bad} rows FAIL dk-check, {sum(r['result'] == 'PEND' for r in results)} pending owner")
    return 1 if bad else 0


def cmd_mpn(dk, mpns, as_json):
    sums = [summary(m, dk.product(m)) for m in mpns]
    if as_json:
        print(json.dumps(sums, indent=1))
    else:
        for s in sums:
            print_summary(s)
    return 0 if all(s['found'] for s in sums) else 1


SELFTEST_MD = '''## Parts

| Ref | Function | Mount | Spares | Manufacturer | MPN | Digi-Key PN | Status |
|---|---|---|---|---|---|---|---|
| X1 | Kept part | THT | no | Acme | TBD | - | order |
| ~~X2~~ | Old part | THT | no | Acme | ~~OLD-1~~ | OLD-1-ND | order |
| X3, X5 | Bought elsewhere | THT | no | Acme | EXT-1 | - | order at Mouser/Arrow (owner) |
| X4 | Elsewhere, DK PN | THT | no | Acme | EXT-2 | EXT-2-ND | order at Mouser (owner) |
'''

SELFTEST_SPARES = (           # (Spares cell, refs per board, expected order quantity for BOARDS_DEFAULT boards)
    ('yes', 1, 2 * 1 + 5), ('yes', 30, 2 * 30 + 6), ('+2', 1, 2 * 1 + 2), ('no', 3, 2 * 3), ('', 2, 2 * 2 + 5))


class _NoLookup:
    """Selftest stand-in for DigiKey: any lookup is a failure (TBD and external rows must not be looked up)."""

    def product(self, mpn):
        raise AssertionError(f'looked up {mpn}')

    def product_by_dk(self, dk_pn, mpn):
        raise AssertionError(f'looked up {dk_pn}')


def cmd_selftest(spec_path):
    """Offline unit checks of the spec parsing: struck rows skipped, external rows EXT and out of the CSV, and no
    struck row of the real spec parsed. Exit 1 on any failure."""
    bad = []
    rows = spec_rows(SELFTEST_MD)
    mpns = [r[COL_MPN] for r in rows]
    if mpns != [TBD, 'EXT-1', 'EXT-2']:
        bad.append(f'synthetic table: parsed MPNs {mpns}, expected the struck row skipped')
    try:
        res = {r['mpn']: r for r in evaluate(_NoLookup(), rows, BOARDS_DEFAULT, SPARE_FRACTION_DEFAULT)}
    except AssertionError as e:
        res = {}
        bad.append(f'evaluate: {e}')
    ext = res.get('EXT-1')
    if res and (ext is None or ext['result'] != 'EXT' or _in_csv(ext['row']) or ext['qty'] != 2 * BOARDS_DEFAULT):
        bad.append(f"external row: {ext and (ext['result'], _in_csv(ext['row']), ext['qty'])}, expected EXT, "
                   f'not in the CSV, qty {2 * BOARDS_DEFAULT}')
    ext2 = res.get('EXT-2')
    if res and (ext2 is None or ext2['result'] != 'FAIL'):
        bad.append(f"external row with a Digi-Key PN: {ext2 and ext2['result']}, expected FAIL (never looked up)")
    for cell, n, want in SELFTEST_SPARES:
        row = {COL_REF: ', '.join(f'X{i}' for i in range(n)), COL_SPARES: cell}
        got = order_qty(row, BOARDS_DEFAULT, SPARE_FRACTION_DEFAULT)
        if got != want:
            bad.append(f'spares {cell!r} x {n} refs: order {got}, expected {want}')
    real = spec_rows(pathlib.Path(spec_path).read_text(encoding='utf-8'))
    struck = [r[COL_MPN] for r in real if any(STRUCK in (v or '') for k, v in r.items() if k in (COL_MPN, COL_DK))]
    if struck:
        bad.append(f'spec: struck MPN / DK PN cells parsed: {struck}')
    for r in real:                               # the CSV must be pure ASCII (BOM Manager upload)
        try:
            _customer_ref(r), _ascii(_description(r))
        except DigiKeyError as e:
            bad.append(f'spec row {r.get(COL_MPN)}: {e}')
    try:
        _ascii('x ☃')
        bad.append('CSV ASCII guard: an unmapped symbol passed')
    except DigiKeyError:
        pass
    for b in bad:
        print(f'FAIL {b}')
    print(f"selftest {'FAILED' if bad else 'PASSED'}: struck rows skipped, external rows EXT and not in the CSV, "
          f'{len(SELFTEST_SPARES)} spares rules, '
          f'{len(real)} spec MPN rows, none struck, CSV text ASCII')
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--json', action='store_true', help='machine-readable output')
    ap.add_argument('--refresh', action='store_true', help='ignore the build/ cache')
    ap.add_argument('--boards', type=int, default=BOARDS_DEFAULT, help='boards to order for')
    ap.add_argument('--spares', type=float, default=SPARE_FRACTION_DEFAULT, help='spare fraction on Spares rows')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sp = sub.add_parser('mpn', help='look up manufacturer part numbers')
    sp.add_argument('mpns', nargs='+')
    sc = sub.add_parser('check', help="check every MPN in the spec's MPN tables")
    sc.add_argument('spec', nargs='?', default=str(SPEC))
    sb = sub.add_parser('bom', help='write the Digi-Key BOM files from the spec Parts table')
    sb.add_argument('spec', nargs='?', default=str(SPEC))
    sb.add_argument('--out', default=str(BOM_DIR))
    st = sub.add_parser('selftest', help='offline unit checks of the spec-table parsing (no Digi-Key calls)')
    st.add_argument('spec', nargs='?', default=str(SPEC))
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')   # Digi-Key text has ±, Ω, °
    if a.cmd == 'selftest':
        return cmd_selftest(a.spec)
    dk = DigiKey(refresh=a.refresh)
    try:
        if a.cmd == 'mpn':
            return cmd_mpn(dk, a.mpns, a.json)
        if a.cmd == 'bom':
            return cmd_bom(dk, a.spec, a.out, a.boards, a.spares)
        return cmd_check(dk, a.spec, a.json, a.boards, a.spares)
    except (DigiKeyError, urllib.error.URLError, TimeoutError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
