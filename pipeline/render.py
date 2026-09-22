"""Step 3: render question crops -> out/q/{exam_id}/*.png, pages -> out/pages/{exam_id}/, preview html.

Nested tree naming:
  q{big}.png            whole 大問          q{big}_stem.png         大問 text before first sub marker
  q{big}-{k}.png        sub node (問1 / ⑴)   q{big}-{k}_stem.png     its text before its own children
  q{big}-{k}-{k2}.png   nested sub (⑴①)
Multi-page regions are stitched vertically.
"""
from __future__ import annotations

from pathlib import Path

import fitz

from common import OUT, ROOT, load_json

ZOOM = 2.5
LEFT = 40
RIGHT = 480
GAP = 12


def render_regions(doc: fitz.Document, regions, out_png: Path) -> None:
    if isinstance(regions, dict):
        regions = [regions]
    pix_list = []
    for r in regions:
        clip = fitz.Rect(LEFT, r["y0"], RIGHT, r["y1"])
        pix_list.append(doc[r["page"]].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip, alpha=False))
    if not pix_list:
        return
    if len(pix_list) == 1:
        pix_list[0].save(out_png)
        return
    w = max(p.width for p in pix_list)
    h = sum(p.height for p in pix_list) + GAP * (len(pix_list) - 1)
    canvas = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), False)
    canvas.clear_with(255)
    y = 0
    for p in pix_list:
        p.set_origin(0, y)
        canvas.copy(p, p.irect)
        y += p.height + GAP
    canvas.save(out_png)


def node_name(big_no: int, path: list[str]) -> str:
    return f"q{big_no}" + "".join(f"-{k}" for k in path)


def render_node(doc: fitz.Document, qdir: Path, big_no: int, path: list[str], node: dict, html: list[str], eid: str, depth: int) -> None:
    name = node_name(big_no, path)
    if node.get("page_regions"):
        for i, r in enumerate(node["page_regions"], 1):
            render_regions(doc, r, qdir / f"{name}-p{i}.png")
            html.append(f"<div class='sub'><h3>{node.get('label', name)} page {i}</h3><img src='../q/{eid}/{name}-p{i}.png'></div>")
        return
    if node.get("regions"):
        render_regions(doc, node["regions"], qdir / f"{name}.png")
        html.append(f"<div class='sub' style='margin-left:{depth * 28}px'><h3>{node.get('label', name)}</h3><img src='../q/{eid}/{name}.png'></div>")
    if node.get("stem") and node.get("subs"):
        render_regions(doc, node["stem"], qdir / f"{name}_stem.png")
        html.append(f"<div class='sub' style='margin-left:{depth * 28}px'><h3>{node.get('label', name)} stem</h3><img src='../q/{eid}/{name}_stem.png'></div>")
    for s in node.get("subs", []):
        render_node(doc, qdir, big_no, path + [s["key"]], s, html, eid, depth + 1)


def main() -> None:
    exams = load_json(OUT / "exams.json", {})
    for eid, ex in exams.items():
        seg = load_json(OUT / "segments" / f"{eid}.json")
        if not seg:
            continue
        doc = fitz.open(ROOT / ex["files"]["question"])
        qdir = OUT / "q" / eid
        qdir.mkdir(parents=True, exist_ok=True)
        for old in qdir.glob("*.png"):
            old.unlink()
        pdir = OUT / "pages" / eid
        pdir.mkdir(parents=True, exist_ok=True)
        for pi, page in enumerate(doc):
            page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(pdir / f"p{pi + 1}.png")
        if ex["files"].get("answer"):
            fitz.open(ROOT / ex["files"]["answer"])[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(pdir / "answer.png")
        html = [f"<html><head><meta charset='utf-8'><title>{eid}</title>"
                "<style>body{font-family:sans-serif;background:#eee}img{max-width:100%;border:1px solid #999;background:#fff}"
                ".q{margin:12px;padding:8px;background:#fff}.sub{margin-top:8px}h3{margin:4px 0;font-size:14px;color:#555}</style></head><body>"
                f"<h1>{eid}</h1>"]
        for b in seg["bigs"]:
            html.append(f"<div class='q'><h2>大問 {b['no']}</h2>")
            render_node(doc, qdir, b["no"], [], b, html, eid, 0)
            html.append("</div>")
        html.append("</body></html>")
        (OUT / "preview").mkdir(parents=True, exist_ok=True)
        (OUT / "preview" / f"{eid}.html").write_text("\n".join(html), encoding="utf-8")
        print(f"[render] {eid}: {len(list(qdir.glob('*.png')))} crops")


if __name__ == "__main__":
    main()
