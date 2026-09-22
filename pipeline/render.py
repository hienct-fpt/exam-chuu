"""Step 3: render question crops -> out/q/{exam_id}/*.png and full pages -> out/pages/{exam_id}/p{n}.png

Multi-page regions are stitched vertically into one PNG.
Also writes out/preview/{exam_id}.html contact sheet for visual QA.
"""
from __future__ import annotations

from pathlib import Path

import fitz

from common import OUT, ROOT, load_json

ZOOM = 2.5
LEFT = 40
RIGHT = 480
GAP = 12  # px between stitched pages


def render_regions(doc: fitz.Document, regions: list[dict], out_png: Path) -> tuple[int, int]:
    pix_list = []
    for r in regions:
        page = doc[r["page"]]
        clip = fitz.Rect(LEFT, r["y0"], RIGHT, r["y1"])
        pix_list.append(page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip, alpha=False))
    if len(pix_list) == 1:
        pix_list[0].save(out_png)
        return pix_list[0].width, pix_list[0].height
    w = max(p.width for p in pix_list)
    h = sum(p.height for p in pix_list) + GAP * (len(pix_list) - 1)
    canvas = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), False)
    canvas.clear_with(255)
    y = 0
    for p in pix_list:
        _blit(canvas, p, y)
        y += p.height + GAP
    canvas.save(out_png)
    return w, h


def _blit(canvas: fitz.Pixmap, src: fitz.Pixmap, y: int) -> None:
    # PyMuPDF: set_origin then copy
    src.set_origin(0, y)
    canvas.copy(src, src.irect)


def main() -> None:
    exams = load_json(OUT / "exams.json", {})
    for eid, ex in exams.items():
        seg = load_json(OUT / "segments" / f"{eid}.json")
        if not seg:
            continue
        doc = fitz.open(ROOT / ex["files"]["question"])
        qdir = OUT / "q" / eid
        qdir.mkdir(parents=True, exist_ok=True)
        pdir = OUT / "pages" / eid
        pdir.mkdir(parents=True, exist_ok=True)
        for pi, page in enumerate(doc):
            page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(pdir / f"p{pi + 1}.png")
        # answer key page
        if ex["files"].get("answer"):
            adoc = fitz.open(ROOT / ex["files"]["answer"])
            adoc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(pdir / "answer.png")
        html = [f"<html><head><meta charset='utf-8'><title>{eid}</title>"
                "<style>body{font-family:sans-serif;background:#eee}img{max-width:100%;border:1px solid #999;background:#fff}"
                ".q{margin:12px;padding:8px;background:#fff}.sub{margin-left:32px}h3{margin:4px 0}</style></head><body>"
                f"<h1>{eid}</h1>"]
        for b in seg["bigs"]:
            bno = b["no"]
            fn = f"q{bno}.png"
            render_regions(doc, b["regions"], qdir / fn)
            html.append(f"<div class='q'><h2>大問 {bno}</h2><img src='../q/{eid}/{fn}'>")
            if b["stem"]:
                render_regions(doc, [b["stem"]], qdir / f"q{bno}_stem.png")
                html.append(f"<h3>stem</h3><img src='../q/{eid}/q{bno}_stem.png'>")
            for s in b["subs"]:
                sfn = f"q{bno}-{s['no']}.png"
                render_regions(doc, s["regions"], qdir / sfn)
                html.append(f"<div class='sub'><h3>{s['label']}</h3><img src='../q/{eid}/{sfn}'></div>")
            html.append("</div>")
        html.append("</body></html>")
        (OUT / "preview").mkdir(parents=True, exist_ok=True)
        (OUT / "preview" / f"{eid}.html").write_text("\n".join(html), encoding="utf-8")
        print(f"[render] {eid}: {len(list(qdir.glob('*.png')))} crops")


if __name__ == "__main__":
    main()
