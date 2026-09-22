"""Step 5: merge segments + answers + tags -> bank.

Outputs:
  out/bank/{exam_id}.json   public: exam meta, 大問 list, items WITHOUT answers (ships to Hosting)
  out/bank/index.json       list of exams (+ grade_counts)
  out/answers_all.json      secret: {item_id: {answer, variants, answer_type, parts, options}}  (-> Firestore answerKeys)

item_id = f"{exam_id}#{slot_id}"   slot_id = "1-1" / "1-7-2" / "2-1-1"
Slot <-> question tree: the slot path is matched against node keys; the deepest matching node supplies the
image, its ancestors' stems form `stem_images`. Slots deeper than the tree (kana fill-ins) share the node image.
Tags: pipeline/tags/{exam_id}.json  {"bigs": {"3": {grade, topic}}, "items": {"3-1": {grade, topic}}}
"""
from __future__ import annotations

from collections import Counter

from common import OUT, ROOT, load_json, dump_json
from render import node_name

TAGS = ROOT / "pipeline" / "tags"


def load_tags(eid: str) -> tuple[dict, dict]:
    t = load_json(TAGS / f"{eid}.json", {}) or {}
    return t.get("bigs", {}), t.get("items", {})


def resolve(big: dict, path: list[str]) -> tuple[dict, list[str], list[dict], bool]:
    """Walk the tree along path. Returns (node, node_path, ancestors incl. big, exact_match)."""
    node, node_path, ancestors = big, [], []
    for key in path:
        nxt = next((s for s in node.get("subs", []) if s["key"] == key), None)
        if nxt is None:
            return node, node_path, ancestors, False
        ancestors.append(node)
        node, node_path = nxt, node_path + [key]
    return node, node_path, ancestors, True


def build_exam(eid: str, ex: dict, seg: dict, ans: dict) -> tuple[dict, dict]:
    big_tags, item_tags = load_tags(eid)
    items: list[dict] = []
    secret: dict[str, dict] = {}
    bigs_out = []
    bigs_by_no = {b["no"]: b for b in seg["bigs"]}
    for b in seg["bigs"]:
        bno = b["no"]
        bt = big_tags.get(str(bno), {})
        slots = [s for s in ans["slots"] if s["big"] == bno]
        item_ids = []
        big_img = f"q/{eid}/q{bno}.png"
        big_stem = f"q/{eid}/q{bno}_stem.png" if (b.get("stem") and b.get("subs")) else None
        for s in slots:
            path = s.get("path") or s["id"].split("-")[1:]
            node, node_path, ancestors, exact = resolve(b, path)
            image = f"q/{eid}/{node_name(bno, node_path)}.png" if node_path else big_img
            stems = []
            if b.get("page_regions"):
                pages = [f"q/{eid}/q{bno}-p{i}.png" for i in range(1, len(b["page_regions"]) + 1)]
                image, stems = pages[-1], pages[:-1]
                node_path, exact = [], False
            for a in ancestors:
                if a.get("stem") and a.get("subs"):
                    stems.append(f"q/{eid}/{node_name(bno, a_path(a, b, bno))}_stem.png")
            if not node_path and big_stem and node.get("subs"):
                stems = []  # whole 大問 image already contains the stem
            shared = not exact or not node_path
            iid = f"{eid}#{s['id']}"
            tag = {**bt, **item_tags.get(s["id"], {})}
            items.append({
                "id": iid, "exam_id": eid, "big": bno, "sub": s.get("sub") or (int(path[0]) if path and path[0].isdigit() else 0),
                "path": path, "label": s.get("label", ""),
                "image": image, "stem_images": stems, "stem_image": stems[0] if stems else None,
                "shared_image": shared,
                "unit": s.get("unit", ""), "parts": s.get("parts"), "part_units": s.get("part_units"),
                "frame": s.get("frame"), "width": s.get("width"),
                "answer_type": s.get("answer_type") or "text", "options": s.get("options"),
                "work_required": bool(s.get("work_required")), "points": 1,
                "grade": tag.get("grade"), "topic": tag.get("topic"), "difficulty": tag.get("difficulty"),
                "note": s.get("note"),
            })
            secret[iid] = {"answer": s.get("answer"), "variants": s.get("variants", []),
                           "answer_type": s.get("answer_type") or "text", "parts": s.get("parts"),
                           "unit": s.get("unit", ""), "options": s.get("options"), "note": s.get("note")}
            item_ids.append(iid)
        bigs_out.append({"no": bno, "image": big_img, "stem_image": big_stem,
                         "sub_count": len(b.get("subs", [])), "items": item_ids,
                         "grade": bt.get("grade"), "topic": bt.get("topic")})
    grade_counts = Counter(str(i["grade"] or "?") for i in items)
    pub = {**{k: v for k, v in ex.items() if k != "files"}, "bigs": bigs_out, "items": items,
           "item_count": len(items), "grade_counts": dict(grade_counts),
           "manual_count": sum(1 for i in items if i["answer_type"] in ("manual", "essay"))}
    return pub, secret


def a_path(node: dict, big: dict, bno: int) -> list[str]:
    """Path (keys) of an ancestor node inside big (linear search)."""
    if node is big:
        return []
    def walk(n, p):
        for s in n.get("subs", []):
            if s is node:
                return p + [s["key"]]
            r = walk(s, p + [s["key"]])
            if r is not None:
                return r
        return None
    return walk(big, []) or []


def main() -> None:
    exams = load_json(OUT / "exams.json", {})
    index = []
    all_secret: dict[str, dict] = {}
    for eid, ex in exams.items():
        seg = load_json(OUT / "segments" / f"{eid}.json")
        ans = load_json(OUT / "answers" / f"{eid}.json")
        if not seg or not ans:
            print(f"[build] {eid}: missing segments/answers, skip")
            continue
        pub, secret = build_exam(eid, ex, seg, ans)
        dump_json(OUT / "bank" / f"{eid}.json", pub)
        all_secret.update(secret)
        index.append({k: pub[k] for k in ("id", "school", "school_name", "year", "session", "session_label",
                                          "subject", "subject_label", "time_limit_min", "item_count",
                                          "grade_counts", "manual_count")})
        missing = [i["id"].split("#")[1] for i in pub["items"]
                   if all_secret[i["id"]]["answer"] in (None, "", []) and i["answer_type"] != "manual"]
        untagged = sum(1 for i in pub["items"] if not i["grade"])
        shared = sum(1 for i in pub["items"] if i["shared_image"])
        print(f"[build] {eid}: {pub['item_count']} items, grades={pub['grade_counts']}, shared_img={shared}, manual={pub['manual_count']}"
              + (f"  NO ANSWER: {missing}" if missing else "") + (f"  untagged={untagged}" if untagged else ""))
    dump_json(OUT / "bank" / "index.json", index)
    dump_json(OUT / "answers_all.json", all_secret)
    print(f"[build] index: {len(index)} exams, {len(all_secret)} answers -> {OUT / 'bank'}")


if __name__ == "__main__":
    main()
