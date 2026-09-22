"""Step 4 (science / social): slots from 解答用紙 + answers from 模範解答 -> out/answers/{exam_id}.json

Same output shape as answer_key.py (math). Overrides: pipeline/overrides/answers/{exam_id}.json
  {"slots": {"1-7-1": {"answer": "...", "answer_type": "text"}, "1-4": {"answer_type": "manual", "note": "graph"}}}
"""
from __future__ import annotations

import sys

import fitz

from common import OUT, OVERRIDES, ROOT, load_json, dump_json
from sheet import slots_from_sheet, extract_answers


def apply_overrides(exam_id: str, slots: list[dict]) -> list[dict]:
    ov = load_json(OVERRIDES / "answers" / f"{exam_id}.json")
    if not ov:
        return slots
    by_id = {s["id"]: s for s in slots}
    for sid, patch in ov.get("slots", {}).items():
        if patch.get("delete"):
            by_id.pop(sid, None)
            continue
        s = by_id.get(sid)
        if s is None:
            big = int(sid.split("-")[0])
            s = {"id": sid, "big": big, "path": sid.split("-")[1:], "label": patch.get("label", sid), "unit": "",
                 "parts": None, "answer_type": None, "answer": None, "confidence": "none", "raw_values": []}
            by_id[sid] = s
        s.update(patch)
        s["confidence"] = "manual"
    return sorted(by_id.values(), key=lambda s: (s["big"], [int(p) if p.isdigit() else 99 for p in s["path"]]))


def process(eid: str, ex: dict, verbose: bool = True) -> list[dict] | None:
    f = ex["files"]
    if "sheet" not in f or "answer" not in f:
        print(f"[answers] {eid}: missing sheet/answer, skip")
        return None
    sheet = fitz.open(ROOT / f["sheet"])
    model = fitz.open(ROOT / f["answer"])
    if ex["subject"] == "japanese":
        import japanese
        slots = japanese.slots_from_sheet(sheet)
        japanese.extract_answers(sheet, model, slots)
        mode = "vertical"
    else:
        slots = slots_from_sheet(sheet)
        mode = extract_answers(sheet, model, slots)
    for s in slots:
        s.pop("y", None); s.pop("x", None)
    slots = apply_overrides(eid, slots)
    dump_json(OUT / "answers" / f"{eid}.json", {"exam_id": eid, "slots": slots})
    low = [s["id"] for s in slots if s["confidence"] in ("low", "none")]
    print(f"[answers] {eid}: mode={mode} {len(slots)} slots, needs review ({len(low)}): {low}")
    if verbose:
        for s in slots:
            print(f"    {s['id']:8} {s['label']:10} unit={s['unit']!r:14} parts={s['parts']} -> {s['answer_type']}:{s['answer']!r} [{s['confidence']}]")
    return slots


def main(only: set[str] | None = None, verbose: bool = False) -> None:
    exams = load_json(OUT / "exams.json", {})
    for eid, ex in exams.items():
        if only and eid not in only:
            continue
        if ex["school"] == "shinagawa":
            import answer_key_tree
            answer_key_tree.process(eid, verbose)
            continue
        if ex["subject"] == "math":
            continue
        process(eid, ex, verbose)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    main(set(args) or None, verbose="-v" in sys.argv or bool(args))
