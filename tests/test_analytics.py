import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))

from analytics import outcomes, topic_stats, weak_topics, item_history, practice_set, weekly_series, subject_summary  # noqa: E402
from grader import grade_submission, virtual_exam  # noqa: E402

OUT = ROOT / "pipeline" / "out"


def _attempt(day: int, exam: str, per_item: dict) -> dict:
    return {"status": "graded", "examId": exam, "submittedAt": f"2026-09-{day:02d}T10:00:00+00:00",
            "result": {"perItem": per_item}}


def _pi(topic, correct, grade=5, pending=False, subject="math"):
    return {"topic": topic, "correct": correct, "answered": True, "pending": pending, "grade": grade, "subject": subject}


def test_topic_stats_and_weakness():
    a1 = _attempt(1, "e1", {"1-1": _pi("計算", True), "2-1": _pi("速さ", False), "2-2": _pi("速さ", False)})
    a2 = _attempt(8, "e2", {"1-1": _pi("計算", True), "2-1": _pi("速さ", False), "3-1": _pi("図形", True, pending=True)})
    a3 = _attempt(15, "e3", {"1-1": _pi("計算", False), "2-1": _pi("速さ", True)})
    outs = outcomes([a1, a2, a3])
    assert len(outs) == 8
    st = topic_stats(outs)
    assert st["計算"]["attempts"] == 3 and st["計算"]["correct"] == 2 and st["計算"]["confident"]
    assert st["速さ"]["weak"] is True          # 1/4 correct
    assert st["図形"]["attempts"] == 0 and st["図形"]["pending"] == 1 and st["図形"]["mastery"] is None
    assert st["計算"]["mastery"] < st["計算"]["accuracy"]  # newest outcome (wrong) weighs most
    weak = weak_topics(st, "math", k=2)
    assert weak[0][0] == "速さ"
    summ = subject_summary(st)
    assert summ["math"]["weak"] == ["速さ"]
    series = weekly_series(outs, weeks=4, now=dt.datetime(2026, 9, 16, tzinfo=dt.timezone.utc))
    assert len(series) == 4 and series[-1]["attempts"] == 2


def test_practice_set_priority_and_shared_groups():
    bank = [
        {"id": "e#1-1", "exam_id": "e", "subject": "math", "topic": "速さ", "grade": 5, "answer_type": "number", "image": "a", "shared_image": False},
        {"id": "e#1-2", "exam_id": "e", "subject": "math", "topic": "速さ", "grade": 6, "answer_type": "number", "image": "b", "shared_image": False},
        {"id": "e#2-1", "exam_id": "e", "subject": "math", "topic": "速さ", "grade": 5, "answer_type": "number", "image": "c", "shared_image": True},
        {"id": "e#2-2", "exam_id": "e", "subject": "math", "topic": "速さ", "grade": 5, "answer_type": "number", "image": "c", "shared_image": True},
        {"id": "e#3-1", "exam_id": "e", "subject": "math", "topic": "速さ", "grade": 5, "answer_type": "essay", "image": "d", "shared_image": False},
        {"id": "e#4-1", "exam_id": "e", "subject": "science", "topic": "速さ", "grade": 5, "answer_type": "number", "image": "e", "shared_image": False},
    ]
    now = dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc)
    hist = {"e#1-1": {"tries": 1, "correct": True, "t": now - dt.timedelta(days=1)},
            "e#2-1": {"tries": 1, "correct": False, "t": now - dt.timedelta(days=3)}}
    picked = practice_set(bank, {"速さ"}, hist, n=3, grade_filter=5, subject="math", now=now)
    ids = [p["id"] for p in picked]
    assert ids[0] == "e#2-1" and "e#2-2" in ids          # wrong-before first, shared sibling pulled in
    assert "e#1-2" not in ids and "e#3-1" not in ids and "e#4-1" not in ids  # grade 6, essay, other subject excluded
    assert ids[-1] == "e#1-1"                             # correct recently comes last


def test_cross_exam_grading_with_real_bank():
    bank_dir = OUT / "bank"
    if not (bank_dir / "kyoritsu_2026_2-1_math.json").exists():
        return
    banks = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in bank_dir.glob("kyoritsu_2026_2-*_math.json")}
    keys_all = json.loads((OUT / "answers_all.json").read_text(encoding="utf-8"))
    ids = ["kyoritsu_2026_2-1_math#1-1", "kyoritsu_2026_2-2_math#1-1", "kyoritsu_2026_2-2_math#2-2"]
    exam, items = virtual_exam(banks, ids)
    assert [i["id"] for i in items] == ids
    answers = {ids[0]: keys_all[ids[0]]["answer"], ids[1]: "wrong", ids[2]: keys_all[ids[2]]["answer"]}
    r = grade_submission(answers, {i: keys_all[i] for i in ids}, exam, ids, full_ids=True)
    assert r["score"] == 2 and r["max"] == 3
    assert r["perItem"][ids[1]]["examId"] == "kyoritsu_2026_2-2_math" and r["perItem"][ids[1]]["sid"] == "1-1"
    assert set(r["perBig"]) == {"kyoritsu_2026_2-1_math#1", "kyoritsu_2026_2-2_math#1", "kyoritsu_2026_2-2_math#2"}
