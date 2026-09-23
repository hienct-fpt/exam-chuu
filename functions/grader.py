"""Pure grading of a submitted attempt. No Firebase imports so it is unit-testable.

attempt.answers : {slotId: str | list[str]}          slotId = "1-1" / "1-7-2"
keys            : {slotId: {answer, variants, answer_type, parts, unit}}   (answerKeys/{examId}.items)
exam            : bank json for the exam (items with id "exam#1-1", big, label, unit, parts, points, grade, topic)
item_ids        : optional subset of slotIds to grade — e.g. 小5 practice mode
manual_grades   : {slotId: bool} set by the parent for essay / manual items
"""
from __future__ import annotations

from examcore.grading import grade, PENDING_TYPES


def slot_id(item_id: str) -> str:
    return item_id.split("#", 1)[1] if "#" in item_id else item_id


def _answered(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, tuple)):
        return any(str(x).strip() for x in v)
    return bool(str(v).strip())


def grade_submission(answers: dict, keys: dict, exam: dict, item_ids: list[str] | None = None,
                     manual_grades: dict | None = None, full_ids: bool = False) -> dict:
    """full_ids=True: items/keys/answers are keyed by the full item id "exam#slot" (cross-exam practice sets)."""
    key_of = (lambda it: it["id"]) if full_ids else (lambda it: slot_id(it["id"]))
    subset = set(item_ids) if (item_ids and full_ids) else ({slot_id(i) for i in item_ids} if item_ids else None)
    manual_grades = manual_grades or {}
    per_item: dict[str, dict] = {}
    per_big: dict[str, dict] = {}
    per_topic: dict[str, dict] = {}
    per_grade: dict[str, dict] = {}
    earned = total = correct_n = answered_n = 0
    graded_items = 0
    pending: list[str] = []
    for it in exam["items"]:
        sid = key_of(it)
        if subset is not None and sid not in subset:
            continue
        graded_items += 1
        key = keys.get(sid)
        student = answers.get(sid)
        points = int(it.get("points") or 1)
        total += points
        answered = _answered(student)
        atype = (key or {}).get("answer_type") or it.get("answer_type") or "text"
        res = grade(key, student) if (key and answered) else None
        is_pending = False
        if atype in PENDING_TYPES:
            if sid in manual_grades:
                correct = bool(manual_grades[sid])
            else:
                correct = False
                is_pending = answered  # blank essays are simply wrong, no need to grade by hand
                if is_pending:
                    pending.append(sid)
        else:
            correct = bool(res and res.correct)
        if correct:
            earned += points
            correct_n += 1
        if answered:
            answered_n += 1
        per_item[sid] = {
            "big": it["big"], "sub": it.get("sub", 0), "path": it.get("path"), "label": it.get("label", ""),
            "unit": it.get("unit", ""), "parts": it.get("parts"), "image": it.get("image"),
            "grade": it.get("grade"), "topic": it.get("topic"), "answerType": atype,
            "examId": it.get("exam_id"), "sid": slot_id(it["id"]), "subject": it.get("subject"),
            "answered": answered, "correct": correct, "pending": is_pending,
            "manual": sid in manual_grades,
            "student": student if student is not None else "",
            "expected": key["answer"] if key else None,
            "variants": (key.get("variants") or []) if key else [],
            "note": (key or {}).get("note"),
            "source": it.get("source"),  # imported items (min-san): {school, year, stars, tags, url, ...}
            "partsCorrect": list(res.parts_correct) if res else [],
            "points": points, "earned": points if correct else 0,
        }
        big_key = f"{it['exam_id']}#{it['big']}" if full_ids else str(it["big"])
        for bucket, k in ((per_big, big_key), (per_topic, it.get("topic") or "未分類"),
                          (per_grade, str(it.get("grade") or "?"))):
            b = bucket.setdefault(k, {"items": 0, "correct": 0, "answered": 0, "points": 0, "earned": 0, "pending": 0})
            b["items"] += 1
            b["points"] += points
            if answered:
                b["answered"] += 1
            if correct:
                b["correct"] += 1
                b["earned"] += points
            if is_pending:
                b["pending"] += 1
        per_big[big_key]["big"] = it["big"]
        per_big[big_key]["examId"] = it.get("exam_id")
    return {
        "score": earned, "max": total, "percent": round(100 * earned / total) if total else 0,
        "correctCount": correct_n, "answeredCount": answered_n, "itemCount": graded_items,
        "pendingCount": len(pending), "pending": pending,
        "perBig": per_big, "perItem": per_item, "perTopic": per_topic, "perGrade": per_grade,
    }


def virtual_exam(banks: dict[str, dict], item_ids: list[str]) -> tuple[dict, list[dict]]:
    """Cross-exam practice set: items from several banks, tagged with subject. Returns (exam, items)."""
    items = []
    for iid in item_ids:
        eid = iid.split("#", 1)[0]
        bank = banks.get(eid)
        if not bank:
            continue
        it = next((x for x in bank["items"] if x["id"] == iid), None)
        if it:
            items.append({**it, "subject": bank.get("subject")})
    return {"items": items, "subject_label": "練習"}, items
