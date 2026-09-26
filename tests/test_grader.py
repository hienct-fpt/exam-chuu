import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))

from grader import grade_submission  # noqa: E402

OUT = ROOT / "pipeline" / "out"
EXAM_ID = "kyoritsu_2026_2-1_math"


@pytest.fixture
def exam_and_keys():
    bank = OUT / "bank" / f"{EXAM_ID}.json"
    if not bank.exists():
        pytest.skip("run pipeline first")
    exam = json.loads(bank.read_text(encoding="utf-8"))
    all_keys = json.loads((OUT / "answers_all.json").read_text(encoding="utf-8"))
    keys = {iid.split("#", 1)[1]: k for iid, k in all_keys.items() if iid.startswith(EXAM_ID + "#")}
    return exam, keys


def test_perfect_submission(exam_and_keys):
    exam, keys = exam_and_keys
    answers = {sid: k["answer"] for sid, k in keys.items()}
    r = grade_submission(answers, keys, exam)
    assert r["score"] == r["max"] == 23
    assert r["percent"] == 100
    assert all(v["correct"] for v in r["perItem"].values())
    assert r["perBig"]["5"]["items"] == 8  # あ〜く


def test_partial_and_blank(exam_and_keys):
    exam, keys = exam_and_keys
    answers = {"1-1": "２３／１２０", "1-2": "35", "3-1": "2:4", "6-1": ["36", "41"]}
    r = grade_submission(answers, keys, exam)
    pi = r["perItem"]
    assert pi["1-1"]["correct"]
    assert not pi["1-2"]["correct"] and pi["1-2"]["answered"]
    assert pi["3-1"]["correct"]  # ratio reduces
    assert not pi["6-1"]["correct"] and pi["6-1"]["partsCorrect"] == [True, False]
    assert not pi["2-1"]["answered"]
    assert r["score"] == 2 and r["answeredCount"] == 4


def test_subset_grade5_only(exam_and_keys):
    exam, keys = exam_and_keys
    g5 = [it["id"].split("#", 1)[1] for it in exam["items"] if it.get("grade") == 5]
    assert g5 and len(g5) < len(exam["items"])
    answers = {sid: keys[sid]["answer"] for sid in g5}
    answers["3-1"] = keys["3-1"]["answer"]  # grade-6 item answered but not in subset -> ignored
    r = grade_submission(answers, keys, exam, item_ids=g5)
    assert r["itemCount"] == len(g5) == r["max"] == r["score"]
    assert set(r["perItem"]) == set(g5)
    assert set(r["perGrade"]) == {"5"}
    assert all(v["items"] > 0 for v in r["perTopic"].values())


def test_manual_grading_of_essays():
    """Essay / manual items are pending until the parent grades them; set/sequence auto-grade."""
    exam = {"items": [
        {"id": "x#1-1", "big": 1, "sub": 1, "label": "問1", "answer_type": "essay", "points": 1},
        {"id": "x#1-2", "big": 1, "sub": 2, "label": "問2", "answer_type": "set", "points": 1},
        {"id": "x#1-3", "big": 1, "sub": 3, "label": "問3", "answer_type": "sequence", "points": 1},
        {"id": "x#1-4", "big": 1, "sub": 4, "label": "問4", "answer_type": "manual", "points": 1},
    ]}
    keys = {"1-1": {"answer_type": "essay", "answer": "水が豊富なため。"},
            "1-2": {"answer_type": "set", "answer": ["A", "D"]},
            "1-3": {"answer_type": "sequence", "answer": "C→B→A"},
            "1-4": {"answer_type": "manual", "answer": None}}
    answers = {"1-1": "水がたくさんあるから", "1-2": "D・A", "1-3": "C, B, A", "1-4": ""}
    r = grade_submission(answers, keys, exam)
    assert r["perItem"]["1-2"]["correct"] and r["perItem"]["1-3"]["correct"]
    assert r["perItem"]["1-1"]["pending"] and r["pending"] == ["1-1"] and r["pendingCount"] == 1
    assert not r["perItem"]["1-4"]["pending"]  # blank drawing answer is just unanswered
    assert r["score"] == 2
    r2 = grade_submission(answers, keys, exam, manual_grades={"1-1": True})
    assert r2["pendingCount"] == 0 and r2["score"] == 3 and r2["perItem"]["1-1"]["manual"]
