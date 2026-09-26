import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))

from examcore.grading import grade, parse_number, parse_ratio, normalize  # noqa: E402
from fractions import Fraction  # noqa: E402


@pytest.mark.parametrize("s,expect", [
    ("23/120", Fraction(23, 120)),
    ("１　３/２２", Fraction(25, 22)),
    ("1と3/22", Fraction(25, 22)),
    ("25/22", Fraction(25, 22)),
    ("7.2", Fraction(36, 5)),
    ("７．２", Fraction(36, 5)),
    ("40,440", Fraction(40440)),
    ("132秒後", Fraction(132)),
    ("43.96 m2", Fraction(4396, 100)),
    ("ウ", None),
    ("", None),
    ("3/0", None),
])
def test_parse_number(s, expect):
    assert parse_number(s) == expect


def test_parse_ratio_reduces():
    assert parse_ratio("2:4") == parse_ratio("1：2")
    assert parse_ratio("5 : 4 : 6") == (Fraction(5), Fraction(4), Fraction(6))
    assert parse_ratio("0.5:0.75") == (Fraction(2), Fraction(3))
    assert parse_ratio("8") is None


def test_grade_number_variants():
    key = {"answer_type": "fraction", "answer": "25/22", "variants": ["1 3/22"]}
    assert grade(key, "1 3/22").correct
    assert grade(key, "１と３／２２").correct
    assert grade(key, "25/22").correct
    assert not grade(key, "25/23").correct
    key2 = {"answer_type": "number", "answer": "7.2", "variants": ["7 1/5", "36/5"]}
    assert grade(key2, "36/5").correct
    assert grade(key2, "7.20").correct


def test_grade_ratio():
    key = {"answer_type": "ratio", "answer": "1:2"}
    assert grade(key, "2:4").correct
    assert grade(key, "1 : 2").correct
    assert not grade(key, "2:1").correct


def test_grade_text_and_choice():
    assert grade({"answer_type": "text", "answer": "ウ"}, "ｳ").correct  # 半角カナ -> NFKC
    assert grade({"answer_type": "text", "answer": "9:40"}, "９：４０").correct
    assert not grade({"answer_type": "text", "answer": "9:40"}, "9:4").correct


def test_grade_multi():
    key = {"answer_type": "multi", "answer": ["36", "42"], "parts": ["AD", "BC"]}
    r = grade(key, ["36", "42"])
    assert r.correct and r.parts_correct == [True, True]
    r = grade(key, ["36", "41"])
    assert not r.correct and r.parts_correct == [True, False]
    r = grade(key, "36, 42")
    assert r.correct
    key2 = {"answer_type": "multi", "answer": ["1", "12"], "parts": ["分", "秒"]}
    assert grade(key2, ["１", "12秒"]).correct


def test_grade_multi_part_set_and_alternatives():
    key = {"answer_type": "multi", "answer": ["イ", "ア・ウ"], "parts": ["変えた条件", "同じにした条件"]}
    assert grade(key, ["イ", "ウ・ア"]).correct          # choice-letter list is order-free
    assert not grade(key, ["イ", "ア"]).correct
    key2 = {"answer_type": "multi", "answer": ["360÷24|360/24", "15"], "parts": ["く", "け"]}
    assert grade(key2, ["360/24", "15"]).correct
    assert grade(key2, ["360÷24", "15"]).correct
    assert not grade(key2, ["24", "15"]).correct
    key3 = {"answer_type": "multi", "answer": ["××・○×", "1"], "parts": ["a", "b"]}
    assert not grade(key3, ["○×・××", "1"]).correct      # non-choice lists keep their order


def test_all_bank_answers_grade_themselves():
    """Every extracted answer must be accepted when the student types it verbatim."""
    p = ROOT / "pipeline" / "out" / "answers_all.json"
    if not p.exists():
        pytest.skip("run pipeline first")
    keys = json.loads(p.read_text(encoding="utf-8"))
    bad = []
    for iid, k in keys.items():
        if k.get("answer_type") in ("essay", "manual"):
            assert grade(k, k["answer"] or "x").pending
            continue
        typed = k["answer"]
        if k.get("answer_type") == "multi" and isinstance(typed, list):
            typed = [str(e).split("|")[0] for e in typed]  # "a|b" = accepted alternatives
        r = grade(k, typed)
        if not r.correct:
            bad.append((iid, k["answer"]))
        for v in k.get("variants") or []:
            if not grade(k, v).correct:
                bad.append((iid, v))
    assert not bad, bad
