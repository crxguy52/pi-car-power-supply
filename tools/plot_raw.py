"""Plot LTspice traces from a .raw file to PNG with PyMuPDF (no matplotlib): one strip per trace, shared time axis.

    pdm run python -I tools/plot_raw.py <file.raw> <out.png> <step, 1-based> <trace> [trace ...]
"""
import pathlib
import sys

import fitz

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ltspice_raw  # noqa: E402

PAGE_W, STRIP_H, MARGIN_L, MARGIN_R, MARGIN_T = 900.0, 110.0, 70.0, 20.0, 20.0
GAP, AXIS_H, FONT = 12.0, 30.0, 9.0
DPI = 110
TIME_TICK_S = 10.0
COLORS = [(0.0, 0.3, 0.7), (0.8, 0.3, 0.0), (0.0, 0.55, 0.2), (0.55, 0.0, 0.55), (0.4, 0.4, 0.4)]


def _columns(t, sx):
    """Point indices grouped per whole x unit (min/max decimation keeps every edge)."""
    cols, cur, key = [], [], None
    for i, tt in enumerate(t):
        k = int(sx(tt))
        if k != key and cur:
            cols.append((key, cur))
            cur = []
        key = k
        cur.append(i)
    if cur:
        cols.append((key, cur))
    return cols


def main(argv):
    raw, out, step, traces = argv[1], argv[2], int(argv[3]), argv[4:]
    st = ltspice_raw.read(raw)['steps'][step - 1]
    t = st['time']
    height = MARGIN_T + len(traces) * (STRIP_H + GAP) + AXIS_H
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=height)
    x0, x1 = MARGIN_L, PAGE_W - MARGIN_R
    t_end = t[-1]
    sx = lambda tt: x0 + (x1 - x0) * tt / t_end
    for k, name in enumerate(traces):
        v = st[name]
        top = MARGIN_T + k * (STRIP_H + GAP)
        lo, hi = min(v), max(v)
        span = (hi - lo) or 1.0
        sy = lambda vv: top + STRIP_H - STRIP_H * (vv - lo) / span
        page.draw_rect(fitz.Rect(x0, top, x1, top + STRIP_H), color=(0.7, 0.7, 0.7), width=0.5)
        pts = []
        for col, idx in _columns(t, sx):
            i_lo = min(idx, key=lambda i: v[i])
            i_hi = max(idx, key=lambda i: v[i])
            for i in sorted({idx[0], i_lo, i_hi, idx[-1]}):
                pts.append(fitz.Point(sx(t[i]), sy(v[i])))
        page.draw_polyline(pts, color=COLORS[k % len(COLORS)], width=0.8)
        page.insert_text((4, top + 12), name, fontsize=FONT)
        page.insert_text((4, top + 24), f'{hi:.3g}', fontsize=FONT)
        page.insert_text((4, top + STRIP_H), f'{lo:.3g}', fontsize=FONT)
    base = MARGIN_T + len(traces) * (STRIP_H + GAP)
    tick = 0.0
    while tick <= t_end:
        page.draw_line((sx(tick), MARGIN_T), (sx(tick), base - GAP), color=(0.88, 0.88, 0.88), width=0.4)
        page.insert_text((sx(tick) - 6, base + 4), f'{tick:g}', fontsize=FONT)
        tick += TIME_TICK_S
    page.insert_text((x1 - 40, base + 18), 'time (s)', fontsize=FONT)
    page.get_pixmap(dpi=DPI).save(out)
    print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
