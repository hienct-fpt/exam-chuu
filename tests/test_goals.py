import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))

import goals  # noqa: E402
from goals import (JST, counts, current_level, exam_date, exam_scores, focus_topics, plan_of, targets,  # noqa: E402
                   topic_frequency, week_goals, week_start, with_actuals)

PLAN = plan_of()
MON = dt.datetime(2026, 10, 19, tzinfo=JST)          # a Monday 00:00 JST


def _outs(week_offset: int, n: int, correct: int, subject="math", topic="速さ"):
    """n graded outcomes on the Wednesday of the week `week_offset` weeks before MON (0 = MON's week)."""
    t = MON - dt.timedelta(weeks=week_offset) + dt.timedelta(days=2)
    return [{"t": t, "subject": subject, "topic": topic, "correct": i < correct, "pending": False,
             "itemId": f"e#{week_offset}-{i}", "examId": "e", "sid": str(i), "grade": 5, "answered": True}
            for i in range(n)]


def test_week_start_is_monday_jst():
    sun_utc = dt.datetime(2026, 10, 18, 16, 0, tzinfo=dt.timezone.utc)   # Mon 01:00 JST
    assert week_start(sun_utc) == MON
    assert week_start(MON - dt.timedelta(seconds=1)) == MON - dt.timedelta(weeks=1)


def test_plan_defaults_and_dates():
    assert PLAN["first"] == "kyoritsu" and PLAN["second"] == "shinagawa" and PLAN["exam_year"] == 2028
    assert exam_date(PLAN) == dt.date(2028, 2, 1)
    assert exam_date(PLAN, "sakaehigashi") == dt.date(2028, 1, 10)       # 栄東 is in January


def test_targets_provisional_until_pass_line_known(monkeypatch):
    tg = targets(PLAN)
    assert tg["math"] == {"target": goals.DEFAULT_TARGET, "provisional": True}
    monkeypatch.setitem(goals.CONFIG["schools"]["kyoritsu"]["subjects"], "math", {"pass": 65, "max": 100})
    assert targets(PLAN)["math"] == {"target": 0.70, "provisional": False}   # 65% + margin 5%


def test_current_level_mixes_items_and_exam_scores():
    outs = _outs(1, 10, 5) + _outs(2, 10, 5)                    # 50% on items
    lvl = current_level(outs, [], MON, "math")
    assert lvl == {"level": 0.5, "sources": ["items"]}
    scores = [{"t": MON - dt.timedelta(days=3), "subject": "math", "percent": 0.8, "kind": "target"}]
    assert current_level(outs, scores, MON, "math")["level"] == round((0.5 + 2 * 0.8) / 3, 3)
    # data from the week itself is ignored (goals only look back)
    assert current_level(_outs(0, 30, 30), [], MON, "math")["level"] is None


def test_official_kumiwake_supersedes_app_grading():
    scores = [{"t": MON - dt.timedelta(days=5), "subject": "math", "percent": 0.4, "kind": "kumiwake"},
              {"t": MON - dt.timedelta(days=4), "subject": "math", "percent": 0.6, "kind": "official"}]
    assert current_level([], scores, MON, "math") == {"level": 0.6, "sources": ["official"]}


def test_exam_scores_only_whole_exams():
    meta = {"kyoritsu_2026_2-1_math": {"school": "kyoritsu", "subject": "math"},
            "kumiwake_2026_r1_math": {"school": "kumiwake", "subject": "math"}}
    base = {"status": "graded", "submittedAt": "2026-10-10T00:00:00+00:00", "percent": 60}
    atts = [{**base, "examId": "kyoritsu_2026_2-1_math"},
            {**base, "examId": "kumiwake_2026_r1_math"},
            {**base, "examId": "kyoritsu_2026_2-1_math", "gradeFilter": 5},       # partial -> skipped
            {**base, "examId": None, "mode": "practice"}]
    official = [{"date": "2026-10-12", "scores": {"math": {"score": 120, "max": 200}}}]
    sc = exam_scores(atts, meta, PLAN, official)
    assert [(s["kind"], s["percent"]) for s in sc] == [("target", 0.6), ("kumiwake", 0.6), ("official", 0.6)]


def test_topic_frequency_and_focus():
    items = ([{"school": "kyoritsu", "subject": "math", "topic": "速さ"}] * 3
             + [{"school": "kyoritsu", "subject": "math", "topic": "計算"}]
             + [{"school": "shinagawa", "subject": "math", "topic": "立体図形"}] * 2
             + [{"school": "chuo", "subject": "math", "topic": "場合の数"}] * 9)       # not a target school
    freq = topic_frequency(items, PLAN)["math"]
    assert set(freq) == {"速さ", "計算", "立体図形"} and freq["速さ"] == 0.6
    stats = {"速さ": {"mastery": 0.9}, "計算": {"mastery": 0.1}}
    top = focus_topics(stats, freq)
    # 計算 (1-0.1)*0.2=0.18 > 立体図形 unseen (1-0.5)*0.2=0.10 > 速さ (1-0.9)*0.6=0.06
    assert [(r["topic"], r["score"]) for r in top] == [("計算", 0.18), ("立体図形", 0.1)]


def test_week_goals_on_track_climbs_toward_target():
    outs = [o for w in range(1, 5) for o in _outs(w, 20, 10)]   # 50%, 20 items/week
    g = week_goals(outs, [], {}, {}, PLAN, MON + dt.timedelta(days=3))
    assert g["weekStart"] == "2026-10-19" and g["examDate"] == "2028-02-01" and g["deadline"] == "2027-12-07"
    m = g["subjects"]["math"]
    weeks = g["weeksLeft"]
    assert weeks == 60                                          # 414 days to 2027-12-07
    assert m["level"] == 0.5 and m["goalItems"] == 20 and not m["behind"] and not m["atRisk"]
    assert m["goalAccuracy"] == round(0.5 + 0.2 / weeks, 2)
    s = g["subjects"]["science"]                                 # no data at all
    assert s["level"] is None and s["goalAccuracy"] is None and s["goalItems"] == goals.DEFAULT_ITEMS


def test_week_goals_missed_week_bumps_volume_and_flags_risk():
    outs = [o for w in range(1, 5) for o in _outs(w, 40, 10)]   # 25%, 40 items/week
    prev = {"subjects": {"math": {"goalItems": 50, "goalAccuracy": 0.3}}}
    late = dt.datetime(2027, 11, 1, tzinfo=JST)
    outs_late = [{**o, "t": o["t"] + (late - MON)} for o in outs]
    g = week_goals(outs_late, [], {}, {}, PLAN, late, prev)
    m = g["subjects"]["math"]
    assert m["behind"] and m["goalItems"] == 44                 # 40 * 1.1
    assert m["atRisk"] and m["goalAccuracy"] == 0.28   # 0.45 gap in 6 weeks > MAX_STEP 3%/week


def test_with_actuals_counts_only_this_week():
    g = week_goals([], [], {}, {}, PLAN, MON)
    outs = _outs(0, 8, 6) + _outs(1, 5, 5)
    a = with_actuals(g, outs)["actual"]["math"]
    assert a == {"items": 8, "correct": 6, "accuracy": 0.75}
    assert counts(outs, MON - dt.timedelta(weeks=1), MON, "math")["items"] == 5
