"""Pure grading of a submitted attempt. No Firebase imports so it is unit-testable.

attempt.answers : {slotId: str | list[str]}          slotId = "1-1" (big-sub)
keys            : {slotId: {answer, variants, answer_type, parts, unit}}   (answerKeys/{examId}.items)
exam            : bank json for the exam (items with id "exam#1-1", big, label, unit, parts, points)
"""
from __future__ import annotations

from examcore.grading import grade


def slot_id(item_id: str) -> str:
    return item_id.split("#", 1)[1] if "#" in item_id else item_id


def _answered(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, tuple)):
        return any(str(x).strip() for x in v)
    return bool(str(v).strip())


def grade_submission(answers: dict, keys: dict, exam: dict) -> dict:
    per_item: dict[str, dict] = {}
    per_big: dict[str, dict] = {}
    earned = total = correct_n = answered_n = 0
    for it in exam["items"]:
        sid = slot_id(it["id"])
        key = keys.get(sid)
        student = answers.get(sid)
        points = int(it.get("points") or 1)
        total += points
        answered = _answered(student)
        res = grade(key, student) if (key and answered) else None
        correct = bool(res and res.correct)
        if correct:
            earned += points
            correct_n += 1
        if answered:
            answered_n += 1
        per_item[sid] = {
            "big": it["big"], "sub": it["sub"], "label": it.get("label", ""), "unit": it.get("unit", ""),
            "parts": it.get("parts"), "image": it.get("image"),
            "answered": answered, "correct": correct,
            "student": student if student is not None else "",
            "expected": key["answer"] if key else None,
            "variants": (key.get("variants") or []) if key else [],
            "partsCorrect": list(res.parts_correct) if res else [],
            "points": points, "earned": points if correct else 0,
        }
        b = per_big.setdefault(str(it["big"]), {"big": it["big"], "items": 0, "correct": 0, "points": 0, "earned": 0})
        b["items"] += 1
        b["points"] += points
        if correct:
            b["correct"] += 1
            b["earned"] += points
    return {
        "score": earned, "max": total, "percent": round(100 * earned / total) if total else 0,
        "correctCount": correct_n, "answeredCount": answered_n, "itemCount": len(exam["items"]),
        "perBig": per_big, "perItem": per_item,
    }
