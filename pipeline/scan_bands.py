"""Helper for scanned 問題 PDFs (no text layer): print the ink bands of each page so crop regions for
pipeline/overrides/segments/{exam_id}.json can be written by hand.

usage: python pipeline/scan_bands.py <pdf> [page ...]        (pages 0-based; default: all)

Coordinates are PDF points, the unit render.py clips in. A landscape page (2-page spread, e.g. kyoritsu 2023)
is split into a left and a right half; each band line reads

  p1 L  y  62.0- 98.5  x  60-460   ...first-row ink profile...

and goes straight into a region: {"page": 1, "x0": 40, "x1": 500, "y0": 58, "y1": 102} (pad a few pt).
Bands are rows of ink separated by >= GAP pt of white; a 大問/小問 cut belongs in such a white gap.
"""
from __future__ import annotations

import sys

import fitz
import numpy as np

GAP = 7          # pt of white that separates two bands
DARK = 170       # gray level counted as ink
EDGE = 18        # pt ignored at each half's outer/inner edge (scan shadows, the spread's fold)


def bands(page: fitz.Page) -> list[tuple[str, float, float, int, int]]:
    pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), colorspace=fitz.csGRAY, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    w = pix.width
    halves = [("L", 0, w // 2), ("R", w // 2, w)] if w > pix.height * 1.2 else [("-", 0, w)]
    out = []
    for name, x0, x1 in halves:
        part = img[:, x0 + EDGE:x1 - EDGE] < DARK
        rows = np.where(part.sum(axis=1) >= 2)[0]
        if not len(rows):
            continue
        start = prev = rows[0]
        for r in list(rows[1:]) + [None]:
            if r is None or r - prev > GAP:
                cols = np.where(part[start:prev + 1].any(axis=0))[0]
                out.append((name, float(start), float(prev + 1), int(cols[0] + x0 + EDGE), int(cols[-1] + x0 + EDGE)))
                if r is not None:
                    start = r
            if r is not None:
                prev = r
    return out


def main() -> None:
    doc = fitz.open(sys.argv[1])
    pages = [int(a) for a in sys.argv[2:]] or range(len(doc))
    for p in pages:
        page = doc[p]
        print(f"== page {p}  {page.rect.width:.0f}x{page.rect.height:.0f}pt  rotation={page.rotation}")
        for name, y0, y1, xa, xb in bands(page):
            print(f"  p{p} {name}  y {y0:6.1f}-{y1:6.1f}  h {y1 - y0:5.1f}  x {xa:4d}-{xb:4d}")


if __name__ == "__main__":
    main()
