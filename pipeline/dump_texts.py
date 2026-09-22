"""Dump question text per 大問/小問 for manual tagging -> out/texts/{exam_id}.json and stdout summary."""
from __future__ import annotations

import re

import fitz

from common import OUT, ROOT, load_json, dump_json

LEFT, RIGHT = 40, 480


def region_text(doc: fitz.Document, regions: list[dict]) -> str:
    parts = []
    for r in regions:
        clip = fitz.Rect(LEFT, r["y0"], RIGHT, r["y1"])
        parts.append(doc[r["page"]].get_text("text", clip=clip))
    t = " ".join(parts)
    return re.sub(r"\s+", " ", t).strip()


def main(limit: int = 160) -> None:
    exams = load_json(OUT / "exams.json", {})
    for eid, ex in exams.items():
        seg = load_json(OUT / "segments" / f"{eid}.json")
        if not seg:
            continue
        doc = fitz.open(ROOT / ex["files"]["question"])
        out = {}
        print(f"===== {eid}")
        for b in seg["bigs"]:
            stem = region_text(doc, [b["stem"]]) if b.get("stem") else region_text(doc, b["regions"])
            out[f"{b['no']}"] = {"stem": stem, "subs": {}}
            print(f"[{b['no']}] {stem[:limit]}")
            for s in b["subs"]:
                t = region_text(doc, s["regions"])
                out[f"{b['no']}"]["subs"][str(s["no"])] = t
                print(f"   {b['no']}-{s['no']} {t[:limit]}")
        dump_json(OUT / "texts" / f"{eid}.json", out)


if __name__ == "__main__":
    main()
