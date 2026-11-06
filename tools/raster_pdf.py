"""Render one PDF page to PNG with PyMuPDF: pdm run raster <pdf> <png> <dpi> [page, 1-based, default 1].

Optional crop: --clip x0,y0,x1,y1 in PDF points (top-left origin). Prints the PNG size in pixels.
Keep dpi at or below MAX_DPI_HINT unless pin-level detail needs more (CLAUDE.md "Reading the source PDFs").
"""
import argparse
import sys

import fitz

DEFAULT_PAGE = 1
MAX_DPI_HINT = 200


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('pdf')
    ap.add_argument('png')
    ap.add_argument('dpi', type=int)
    ap.add_argument('page', type=int, nargs='?', default=DEFAULT_PAGE)
    ap.add_argument('--clip', help='x0,y0,x1,y1 in PDF points')
    a = ap.parse_args()
    doc = fitz.open(a.pdf)
    if not 1 <= a.page <= doc.page_count:
        ap.error(f'page {a.page} outside 1..{doc.page_count}')
    page = doc[a.page - 1]
    clip = fitz.Rect(*[float(v) for v in a.clip.split(',')]) if a.clip else None
    pix = page.get_pixmap(dpi=a.dpi, clip=clip)
    pix.save(a.png)
    if a.dpi > MAX_DPI_HINT:
        print(f'note: {a.dpi} DPI is above {MAX_DPI_HINT}: crop to the needed area', file=sys.stderr)
    print(pix.width, pix.height)
    return 0


if __name__ == '__main__':
    sys.exit(main())
