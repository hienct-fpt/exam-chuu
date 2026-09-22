"""Step 5: merge segments + answers -> bank.

Outputs:
  out/bank/{exam_id}.json   public: exam meta, 大問 list, items WITHOUT answers (ships to Hosting)
  out/bank/index.json       list of exams
  out/answers_all.json      secret: {item_id: {answer, variants, answer_type, parts}}  (-> Firestore answerKeys)

item_id = f"{exam_id}#{big}-{sub}"
"""
from __future__ import annotations

from common import OUT, load_json, dump_json


def build_exam(eid: str, ex: dict, seg: dict, ans: dict) -> tuple[dict, dict]:
    bigs_by_no = {b["no"]: b for b in seg["bigs"]}
    items: list[dict] = []
    secret: dict[str, dict] = {}
    bigs_out = []
    for b in seg["bigs"]:
        bno = b["no"]
        sub_imgs = {s["no"]: f"q/{eid}/q{bno}-{s['no']}.png" for s in b["subs"]}
        big_img = f"q/{eid}/q{bno}.png"
        stem_img = f"q/{eid}/q{bno}_stem.png" if b.get("stem") else None
        slots = [s for s in ans["slots"] if s["big"] == bno]
        item_ids = []
        for s in slots:
            iid = f"{eid}#{s['id']}"
            # image: matching 小問 crop if the slot label is ①②③ and crop exists; else whole 大問
            image = sub_imgs.get(s["sub"]) if s["label"] and s["label"] in "①②③④⑤⑥⑦⑧⑨⑩" else None
            shared = image is None
            items.append({
                "id": iid, "exam_id": eid, "big": bno, "sub": s["sub"], "label": s["label"],
                "image": image or big_img, "stem_image": None if shared else stem_img,
                "shared_image": shared,  # several items point at the same 大問 crop (あ〜く fill-ins)
                "unit": s.get("unit", ""), "parts": s.get("parts"), "answer_type": s["answer_type"],
                "work_required": bool(s.get("work_required")), "points": 1,
                "topic": None, "difficulty": None,
            })
            secret[iid] = {"answer": s["answer"], "variants": s.get("variants", []),
                           "answer_type": s["answer_type"], "parts": s.get("parts"), "unit": s.get("unit", "")}
            item_ids.append(iid)
        bigs_out.append({"no": bno, "image": big_img, "stem_image": stem_img,
                         "sub_count": len(b["subs"]), "items": item_ids})
    pub = {**{k: v for k, v in ex.items() if k != "files"}, "bigs": bigs_out, "items": items,
           "item_count": len(items)}
    return pub, secret


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
                                          "subject", "subject_label", "time_limit_min", "item_count")})
        missing = [i["id"] for i in pub["items"] if all_secret[i["id"]]["answer"] in (None, "", [])]
        print(f"[build] {eid}: {pub['item_count']} items" + (f"  NO ANSWER: {missing}" if missing else ""))
    dump_json(OUT / "bank" / "index.json", index)
    dump_json(OUT / "answers_all.json", all_secret)
    print(f"[build] index: {len(index)} exams, {len(all_secret)} answers -> {OUT / 'bank'}")


if __name__ == "__main__":
    main()
