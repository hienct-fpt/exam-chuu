"""Step 4 (shinagawa): slots from the question tree -> out/answers/{exam_id}.json

Shinagawa 模範解答 are scanned handwriting, so nothing can be extracted automatically:
every leaf of the segmented question tree becomes a slot, and the answers are transcribed
by hand into pipeline/overrides/answers/{exam_id}.json (same shape as the kyoritsu overrides).
Slots still lacking an answer after overrides are listed as "needs transcription".
"""
from __future__ import annotations

import sys

from common import OUT, load_json, dump_json
from answer_key_generic import apply_overrides


def slots_from_tree(seg: dict) -> list[dict]:
    slots: list[dict] = []
    for b in seg["bigs"]:
        bno = b["no"]

        def walk(node: dict, path: list[str], labels: list[str]) -> None:
            if not node.get("subs"):
                sid = "-".join([str(bno), *path])
                slots.append({
                    "id": sid, "big": bno, "path": path, "label": " ".join(labels) or str(bno),
                    "unit": "", "parts": None, "answer_type": None, "answer": None,
                    "confidence": "none", "raw_values": [],
                })
                return
            for s in node["subs"]:
                walk(s, path + [s["key"]], labels + [s["label"]])

        walk(b, [], [])
    return slots


def process(eid: str, verbose: bool = True) -> list[dict] | None:
    seg = load_json(OUT / "segments" / f"{eid}.json")
    if not seg:
        print(f"[answers] {eid}: no segments, skip")
        return None
    slots = apply_overrides(eid, slots_from_tree(seg))
    for s in slots:
        s.setdefault("path", s["id"].split("-")[1:])
        if s.get("answer_type") is None:
            s["answer_type"] = "manual"
    dump_json(OUT / "answers" / f"{eid}.json", {"exam_id": eid, "slots": slots})
    todo = [s["id"] for s in slots if s["confidence"] != "manual"]
    print(f"[answers] {eid}: tree mode, {len(slots)} slots, needs transcription ({len(todo)}): {todo}")
    if verbose:
        for s in slots:
            print(f"    {s['id']:10} {s['label']:12} unit={s['unit']!r:10} parts={s['parts']} -> {s['answer_type']}:{s['answer']!r}")
    return slots


def main(only: set[str] | None = None, verbose: bool = False) -> None:
    exams = load_json(OUT / "exams.json", {})
    for eid, ex in exams.items():
        if ex["school"] != "shinagawa":
            continue
        if only and eid not in only:
            continue
        process(eid, verbose)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    main(set(args) or None, verbose="-v" in sys.argv or bool(args))
