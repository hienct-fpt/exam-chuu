"""Step 3b: 解説 (worked solutions) crops for 四谷大塚 組分け exams -> out/q/{exam}/x{大問}.png

Only the round's 結果.pdf carries 解説 ("新５年生 解答と解説": per subject an answer table, then a 解説 block with
one paragraph per 大問). Its later pages (正答率一覧 / 評価表 / 順位一覧, with the child's results) are never read:
parsing stops at the first 正答率一覧 page. School past papers only have 模範解答 (answers), so nothing to crop.

Big markers are the boxed numbers in the left margin, set in the FC-KigouGothic font whose glyphs extract as the
kanji below. Within a subject the markers run 1..N for the answer table, then restart for the 解説 block; each 解説
paragraph runs from its marker to the next one (continuing over a page break). Run after render.py (it wipes q/).

usage: python pipeline/kaisetsu.py [exam_id ...]
"""
from __future__ import annotations

import re
import sys

import fitz

from common import OUT, ROOT, load_json
from render import render_regions

KIGOU = {c: i for i, c in enumerate("宗就州修愁拾洲秀", 1)}    # FC-KigouGothic boxed 1..8
MARKER_FONT = "KigouGothic"
MARKER_MAX_X = 60
SUBJECT_HEAD = {"算数": "math", "国語": "japanese", "理科": "science", "社会": "social"}
STOP = "正答率一覧"
TOP, BOTTOM = 40, 40      # continuation crop starts / page crop ends this far from the edge (pt)


def page_subject(page: fitz.Page) -> str | None:
    """Subject banner at the top of a subject's first page ("算 数", "国語 ５年㊤組分①")."""
    head = re.sub(r"\s+", "", page.get_textbox(fitz.Rect(0, 0, page.rect.width, 130)))
    return next((s for k, s in SUBJECT_HEAD.items() if k in head), None)


def markers(page: fitz.Page) -> list[tuple[float, int]]:
    out = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            for s in line["spans"]:
                t = s["text"].strip()
                if MARKER_FONT in s["font"] and s["bbox"][0] < MARKER_MAX_X and t in KIGOU:
                    out.append((s["bbox"][1], KIGOU[t]))
    return sorted(out)


def explain_regions(doc: fitz.Document) -> dict[str, dict[int, list[dict]]]:
    """{subject: {大問: [regions]}} for the 解説 blocks of every subject."""
    pages: dict[str, list[int]] = {}
    cur = None
    for pi, page in enumerate(doc):
        if STOP in page.get_text():
            break
        cur = page_subject(page) or cur
        if cur:
            pages.setdefault(cur, []).append(pi)
    out: dict[str, dict[int, list[dict]]] = {}
    for subj, pis in pages.items():
        seq = [(pi, y, n) for pi in pis for y, n in markers(doc[pi])]
        start = next((i for i in range(1, len(seq)) if seq[i][2] <= seq[i - 1][2]), None)   # numbering restarts
        if start is None:
            continue
        expl = seq[start:]
        res: dict[int, list[dict]] = {}
        for k, (pi, y, n) in enumerate(expl):
            end_pi, end_y = (expl[k + 1][0], expl[k + 1][1]) if k + 1 < len(expl) else (pis[-1], None)
            regs, p, y0 = [], pi, y - 8
            while True:
                h = doc[p].rect.height
                if p == end_pi and end_y is not None:
                    if end_y - 4 > y0 + 8:
                        regs.append({"page": p, "y0": round(y0, 1), "y1": round(end_y - 4, 1)})
                    break
                regs.append({"page": p, "y0": round(y0, 1), "y1": round(h - BOTTOM, 1)})
                if p >= end_pi:
                    break
                p, y0 = p + 1, TOP
            res[n] = regs
        out[subj] = res
    return out


def main(only: tuple[str, ...] = ()) -> None:
    exams = load_json(OUT / "exams.json", {})
    docs: dict[str, dict] = {}
    for eid, ex in exams.items():
        if only and eid not in only:
            continue
        res = ex.get("files", {}).get("result")
        if ex.get("school") != "kumiwake" or not res or not (ROOT / res).exists():
            continue
        if res not in docs:
            doc = fitz.open(ROOT / res)
            docs[res] = {"doc": doc, "regions": explain_regions(doc)}
        d = docs[res]
        qdir = OUT / "q" / eid
        qdir.mkdir(parents=True, exist_ok=True)
        for old in qdir.glob("x*.png"):
            old.unlink()
        bigs = d["regions"].get(ex["subject"], {})
        for bno, regs in sorted(bigs.items()):
            render_regions(d["doc"], regs, qdir / f"x{bno}.png")
        print(f"[kaisetsu] {eid}: 大問 {sorted(bigs)}")


if __name__ == "__main__":
    main(tuple(sys.argv[1:]))
