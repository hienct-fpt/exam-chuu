"""End-to-end (no HTTP): the dev server's grade() and stats() helpers over the real bank."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

if not (ROOT / "pipeline" / "out" / "bank" / "index.json").exists():
    pytest.skip("run pipeline first", allow_module_level=True)

import dev_server as ds  # noqa: E402


def test_practice_grade_and_stats_digest():
    keys = ds.ALL_KEYS
    ids = [i for i in keys if i.startswith("kyoritsu_2026_2-1_math#")][:4] + \
          [i for i in keys if i.startswith("kyoritsu_2026_2-2_math#")][:3]
    answers = {i: keys[i]["answer"] for i in ids[:5]}      # 5 right, 2 blank
    out = ds.grade({"mode": "practice", "items": ids, "answers": answers, "topics": ["計算"], "attemptId": "p1"})
    r = out["result"]
    assert r["max"] == 7 and r["score"] == 5
    assert "弱点練習" in out["emailSubject"]
    assert len({v["examId"] for v in r["perItem"].values()}) == 2

    attempts = [{"status": "graded", "examId": None, "mode": "practice", "submittedAt": "2026-09-20T09:00:00+00:00", "result": r}]
    st = ds.stats({"attempts": attempts, "digest": True, "studentName": "共子"})
    assert st["attemptCount"] == 1
    assert st["subjects"]["math"]["attempts"] == 7
    assert any(t["subject"] == "math" for t in st["topics"].values())
    assert "週間レポート" in st["digestHtml"] and "共子" in st["digestSubject"]
    # items answered wrong/blank come first in a practice suggestion for their topic
    hist = st["itemHistory"]
    assert all(k in keys for k in hist)


def test_exam_grade_still_works():
    eid = "kyoritsu_2026_2-1_science"
    ks = ds.keys_for(eid)
    answers = {sid: k["answer"] for sid, k in ks.items() if k["answer_type"] not in ("essay", "manual")}
    out = ds.grade({"examId": eid, "answers": answers})
    r = out["result"]
    assert r["correctCount"] == len(answers)
    assert r["pendingCount"] == 0 and r["max"] == len(ks)
