"""組分け 正答率一覧 -> average score of all test-takers per round and subject (for the 推定偏差値).

Reads ONLY the 配点 and 正答率 columns of the 正答率一覧 pages of kumiwake_past/*結果.pdf: every page is clipped to
the left of its 「結果」 header, so the child's own per-question results are never extracted. Only all-test-taker
figures are written:

  functions/kumiwake_population.json  {"kumiwake_2026_r1_math": {"max": 200, "mean": 128.4, "rows": 25,
                                        "points": [8, ...], "rates": [92.3, ...]}, ...}

`rates` (正答率 % per row = per answer slot) become item["rate"] in build.py -> the 取るべき問題 list.

mean = Σ 配点 × 正答率. A subject whose 配点 do not add up to its full marks is reported and skipped.
(pipeline/kaisetsu.py still stops before these pages; this step needs nothing else from them.)
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import fitz

from common import ROOT

SRC = ROOT / "kumiwake_past"
OUT = ROOT / "functions" / "kumiwake_population.json"
SUBJECTS = {"算数": "math", "国語": "japanese", "理科": "science", "社会": "social"}
FULL = {"math": 200, "japanese": 150, "science": 100, "social": 100}
NUM = re.compile(r"\d+(\.\d+)?")


def round_of(path: Path) -> int | None:
    m = re.search(r"第([0-9０-９]+)回", unicodedata.normalize("NFKC", path.name))
    return int(m.group(1)) if m else None


def page_rows(page: fitz.Page) -> tuple[str | None, list[tuple[int, float]]]:
    """(subject, [(配点, 正答率 %)]) of one 正答率一覧 page, read left of the 結果 column only."""
    head = {w[4]: w for w in page.get_text("words") if w[4] in ("配点", "正答率", "結果")}
    if "結果" not in head or "配点" not in head:
        return None, []
    clip = fitz.Rect(0, 0, head["結果"][0] - 1, page.rect.height)   # the child's 結果 column stays outside
    words = page.get_text("words", clip=clip)
    top = page.get_text("text", clip=fitz.Rect(0, 0, clip.x1, head["配点"][3] + 2))   # title + header row only
    subject = next((v for k, v in SUBJECTS.items() if k in top), None)
    px0, px1 = head["配点"][0] - 25, head["配点"][2] + 4
    lines: dict[int, list] = {}
    for w in words:
        if w[1] > head["配点"][3]:
            lines.setdefault(round(w[1] / 3), []).append(w)
    rows = []
    for ws in lines.values():
        pts = [w for w in ws if px0 <= w[0] <= px1 and w[4].isdigit()]
        rate = [w for w in ws if w[0] > px1 and NUM.fullmatch(w[4])]
        if pts and rate:
            rows.append((int(pts[0][4]), float(rate[0][4])))
    return subject, rows


def main() -> None:
    out = {}
    for pdf in sorted(SRC.glob("*結果.pdf")):
        rnd = round_of(pdf)
        year = re.match(r"(\d{4})年", pdf.name)
        if rnd is None or not year:
            continue
        doc = fitz.open(pdf)
        for page in doc:
            if "正答率一覧" not in page.get_text("text"):
                continue
            subject, rows = page_rows(page)
            if not subject or not rows:
                continue
            total = sum(p for p, _ in rows)
            eid = f"kumiwake_{year.group(1)}_r{rnd}_{subject}"
            if total != FULL[subject]:
                print(f"[seitouritsu] {eid}: 配点 sum {total} != {FULL[subject]}, skipped")
                continue
            # points / rates per row (= per answer slot, in sheet order): build.py gives each item its 正答率
            out[eid] = {"max": total, "mean": round(sum(p * r / 100 for p, r in rows), 1), "rows": len(rows),
                        "points": [p for p, _ in rows], "rates": [r for _, r in rows]}
            print(f"[seitouritsu] {eid}: mean {out[eid]['mean']} / {total} ({len(rows)} rows)")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[seitouritsu] {len(out)} subject-rounds -> {OUT}")


if __name__ == "__main__":
    main()
