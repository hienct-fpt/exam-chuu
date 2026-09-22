import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))

from grader import grade_submission  # noqa: E402
from report import render_report  # noqa: E402

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


def test_report_html(exam_and_keys):
    exam, keys = exam_and_keys
    answers = {sid: k["answer"] for sid, k in keys.items()}
    answers["2-1"] = "80"
    r = grade_submission(answers, keys, exam)
    subject, html = render_report("共子", exam, r, "https://x.web.app/", "abc123")
    assert "22/23" in subject and "共子" in subject
    assert "https://x.web.app/q/kyoritsu_2026_2-1_math/q2-1.png" in html
    assert "#/result/abc123" in html
    assert html.count("<tr>") >= 23 + 6
