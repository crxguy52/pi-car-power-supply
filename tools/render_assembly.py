"""Assembly drawing of the top side: reports/assembly_top.png (hand soldering; placement phase, overnight 2026-11-04).

Usage (KiCad python, under timeout, from the project root):
    python.exe -I tools/render_assembly.py [board] [png]

Draws, at SCALE x board size and DPI dots per inch: the board outline (Edge.Cuts), every footprint's F.Fab
graphics, its pads (pad 1 in PAD1_COLOUR: diode cathode, electrolytic +, IC pin 1, SW1 pin 1), the courtyard
outline, and the reference (bold) plus value inside the courtyard, turned along the courtyard's long side.
Read-only on the board. Needs PIL (bundled with KiCad 10 python) and a TrueType font from FONT_DIRS.
"""
import math
import pathlib
import sys

import pcbnew
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
PCB = ROOT / 'pi_power_board.kicad_pcb'
OUT = ROOT / 'reports' / 'assembly_top.png'

SCALE = 4.0                  # drawing size / board size
DPI = 200
MARGIN_MM = 3.0              # board mm around the outline
TITLE_MM = 7.0               # board mm above the board for the title block
REF_PX = 30                  # reference text height, px (shrunk to fit the courtyard)
VAL_PX = 20                  # value text height, px
MIN_PX = 13                  # smallest text drawn
FONT_DIRS = (pathlib.Path(r'C:\Windows\Fonts'),)
FONT_REG, FONT_BOLD = 'arial.ttf', 'arialbd.ttf'
OUTLINE_COLOUR = (0, 0, 0)
FAB_COLOUR = (110, 110, 110)
CRT_COLOUR = (200, 200, 230)
PAD_COLOUR = (230, 190, 120)
PAD1_COLOUR = (220, 60, 60)
REF_COLOUR = (0, 0, 120)
VAL_COLOUR = (0, 100, 0)
LINE_PX = 2


def font(name, px):
    for d in FONT_DIRS:
        if (d / name).exists():
            return ImageFont.truetype(str(d / name), px)
    raise SystemExit(f'font {name} not found in {FONT_DIRS}')


def main(argv):
    board_path = pathlib.Path(argv[1]) if len(argv) > 1 else PCB
    out = pathlib.Path(argv[2]) if len(argv) > 2 else OUT
    board = pcbnew.LoadBoard(str(board_path))
    edge = board.GetBoardEdgesBoundingBox()
    x0 = edge.GetLeft() / 1e6 - MARGIN_MM
    y0 = edge.GetTop() / 1e6 - MARGIN_MM - TITLE_MM
    w_mm = edge.GetWidth() / 1e6 + 2 * MARGIN_MM
    h_mm = edge.GetHeight() / 1e6 + 2 * MARGIN_MM + TITLE_MM
    px_per_mm = SCALE * DPI / 25.4
    img = Image.new('RGB', (int(w_mm * px_per_mm), int(h_mm * px_per_mm)), 'white')
    dr = ImageDraw.Draw(img)

    def P(x_nm, y_nm):
        return ((x_nm / 1e6 - x0) * px_per_mm, (y_nm / 1e6 - y0) * px_per_mm)

    def shape(s, colour, fill=None):
        t = s.GetShape()
        if t == pcbnew.SHAPE_T_SEGMENT:
            dr.line([P(s.GetStart().x, s.GetStart().y), P(s.GetEnd().x, s.GetEnd().y)], fill=colour, width=LINE_PX)
        elif t in (pcbnew.SHAPE_T_RECTANGLE, pcbnew.SHAPE_T_POLY):
            pts = [P(c.x, c.y) for c in s.GetCorners()] if t == pcbnew.SHAPE_T_RECTANGLE else None
            if pts is None:
                ps = s.GetPolyShape()
                pts = [P(ps.CVertex(i).x, ps.CVertex(i).y) for i in range(ps.FullPointCount())]
            if len(pts) > 1:
                dr.polygon(pts, outline=colour, fill=fill)
        elif t == pcbnew.SHAPE_T_CIRCLE:
            cx, cy = P(s.GetCenter().x, s.GetCenter().y)
            r = s.GetRadius() / 1e6 * px_per_mm
            dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline=colour, width=LINE_PX)
        elif t == pcbnew.SHAPE_T_ARC:
            n = 16
            c, r = s.GetCenter(), s.GetRadius()
            a0 = math.atan2(s.GetStart().y - c.y, s.GetStart().x - c.x)
            a1 = math.atan2(s.GetEnd().y - c.y, s.GetEnd().x - c.x)
            sweep = math.radians(s.GetArcAngle().AsDegrees())
            pts = [P(c.x + r * math.cos(a0 + sweep * k / n), c.y + r * math.sin(a0 + sweep * k / n))
                   for k in range(n + 1)]
            dr.line(pts, fill=colour, width=LINE_PX)
            del a1

    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts and d.GetClass() == 'PCB_SHAPE':
            shape(d, OUTLINE_COLOUR)

    labels = []
    for f in board.GetFootprints():
        if f.IsFlipped():
            continue
        for g in f.GraphicalItems():
            if g.GetLayer() == pcbnew.F_CrtYd and g.GetClass() == 'PCB_SHAPE':
                shape(g, CRT_COLOUR)
        for p in f.Pads():
            if not (p.IsOnLayer(pcbnew.F_Cu) or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH):
                continue
            poly = p.GetEffectivePolygon(pcbnew.F_Cu, pcbnew.ERROR_INSIDE)
            colour = PAD1_COLOUR if p.GetNumber() == '1' else PAD_COLOUR
            for k in range(poly.OutlineCount()):
                o = poly.Outline(k)
                pts = [P(o.CPoint(i).x, o.CPoint(i).y) for i in range(o.PointCount())]
                if len(pts) > 2:
                    dr.polygon(pts, fill=colour)
        for g in f.GraphicalItems():
            if g.GetLayer() == pcbnew.F_Fab and g.GetClass() == 'PCB_SHAPE':
                shape(g, FAB_COLOUR)
        c = f.GetCourtyard(pcbnew.F_CrtYd)
        bb = c.BBox() if c.OutlineCount() else f.GetBoundingBox(False)
        labels.append((f.GetReference(), f.GetValue(), bb))

    for ref, value, bb in labels:
        (bx0, by0), (bx1, by1) = P(bb.GetLeft(), bb.GetTop()), P(bb.GetRight(), bb.GetBottom())
        bw, bh = bx1 - bx0, by1 - by0
        vertical = bh > bw * 1.15
        long_px, short_px = (bh, bw) if vertical else (bw, bh)
        if ref.startswith('MH'):
            continue
        texts = []
        for txt, name, size, colour in ((ref, FONT_BOLD, REF_PX, REF_COLOUR), (value, FONT_REG, VAL_PX, VAL_COLOUR)):
            s = size
            while s >= MIN_PX:
                fnt = font(name, s)
                tw = dr.textlength(txt, font=fnt)
                if tw <= long_px * 0.95:
                    break
                s -= 1
            texts.append((txt, fnt, colour, s))
        total_h = sum(t[3] for t in texts) * 1.15
        if total_h > short_px * 0.98:          # only the reference fits
            texts = texts[:1]
            total_h = texts[0][3] * 1.15
        tile = Image.new('RGBA', (int(long_px) + 2, int(max(total_h, short_px)) + 2), (255, 255, 255, 0))
        td = ImageDraw.Draw(tile)
        yy = (tile.size[1] - total_h) / 2
        for txt, fnt, colour, s in texts:
            tw = td.textlength(txt, font=fnt)
            td.text(((tile.size[0] - tw) / 2, yy), txt, font=fnt, fill=colour)
            yy += s * 1.15
        if vertical:
            tile = tile.rotate(90, expand=True)
        img.paste(tile, (int(bx0 + (bw - tile.size[0]) / 2), int(by0 + (bh - tile.size[1]) / 2)), tile)

    title = (f'pi_power_board top-side assembly (scale {SCALE:g}:1 at {DPI} dpi). Blue = reference, green = value, '
             'red pad = pad 1 (diode cathode, electrolytic +, IC pin 1)')
    dr.text((MARGIN_MM * px_per_mm, MARGIN_MM * px_per_mm * 0.5), title, font=font(FONT_REG, VAL_PX + 4),
            fill=(0, 0, 0))
    out.parent.mkdir(exist_ok=True)
    img.save(out, dpi=(DPI, DPI))
    print(f'{out} ({img.size[0]} x {img.size[1]} px)')


if __name__ == '__main__':
    main(sys.argv)
