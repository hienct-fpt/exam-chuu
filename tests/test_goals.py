import datetime as dt
import sys
from pathlib import Path

import pytest

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


def _schools(monkeypatch, kyoritsu: dict, shinagawa: dict):
    """Replace both target schools' rounds with test data (the real schools.json numbers change)."""
    monkeypatch.setitem(goals.CONFIG["schools"]["kyoritsu"], "sessions",
                        {"2-1": {"label": "2/1", "date": "02-01", **kyoritsu}})
    monkeypatch.setitem(goals.CONFIG["schools"]["shinagawa"], "sessions",
                        {"r1": {"label": "第1回", "date": "02-01", **shinagawa}})


@pytest.fixture
def unknown_schools(monkeypatch):
    _schools(monkeypatch, {"subjects": {}, "total": {}}, {"subjects": {}, "total": {}})


def test_targets_provisional_until_scores_known(unknown_schools):
    assert targets(PLAN)["math"] == {"target": goals.DEFAULT_TARGET, "provisional": True, "basis": None}


def test_targets_take_the_harder_school(monkeypatch):
    _schools(monkeypatch,
             {"subjects": {"math": {"max": 100, "line": 70}}, "total": {}},                  # line 70 + margin 5
             {"subjects": {"math": {"max": 100, "pass_avg": 80}, "social": {"max": 60, "pass_avg": 30}},
              "total": {"max": 320, "line": 192}})
    tg = targets(PLAN)
    assert tg["math"]["target"] == 0.8 and tg["math"]["basis"].endswith("第1回 合格者平均")
    assert tg["social"]["target"] == 0.5
    assert tg["japanese"]["provisional"]          # no 国語 data in either school's subjects
    # a round known only by its total 合格ライン -> line rate + margin for every subject
    _schools(monkeypatch, {"subjects": {}, "total": {"max": 400, "line": 240}}, {"subjects": {}, "total": {}})
    assert targets(PLAN)["japanese"]["target"] == 0.65
    # only 受験者平均 published (共立) -> + margin
    _schools(monkeypatch, {"subjects": {"math": {"max": 100, "examinee_avg": 61.0}}, "total": {}}, {"subjects": {}, "total": {}})
    assert targets(PLAN)["math"] == {"target": 0.66, "provisional": False, "basis": "共立女子 2/1 受験者平均+5%"}


def test_real_shinagawa_scores_loaded():
    """schools.json: 品川 第1回/第2回 合格者平均 (parent, 2026-10-19); the higher round counts."""
    tg = targets(PLAN)
    assert tg["math"]["target"] == 0.81 and not tg["math"]["provisional"]
    assert tg["social"]["basis"] == "共立女子 2/2入試 受験者平均+5%"      # 28.3/50 + 5% > 品川 36.5/60


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
    meta = {"kyoritsu_2026_2-1_math": {"school": "kyoritsu", "subject": "math", "item_count": 10,
                                       "grade_counts": {"5": 6, "6": 4}},
            "kumiwake_2026_r1_math": {"school": "kumiwake", "subject": "math", "item_count": 25, "grade_counts": {"5": 25}}}
    base = {"status": "graded", "submittedAt": "2026-10-10T00:00:00+00:00", "percent": 60}
    ids = lambda n: [str(i) for i in range(n)]  # noqa: E731
    atts = [{**base, "examId": "kyoritsu_2026_2-1_math"},
            # 小5 filter keeps every 組分け item -> the app's "practice" attempt still is the whole exam
            {**base, "examId": "kumiwake_2026_r1_math", "mode": "practice", "gradeFilter": 5, "itemIds": ids(25)},
            {**base, "examId": "kyoritsu_2026_2-1_math", "mode": "practice", "gradeFilter": 5, "itemIds": ids(6)},
            {**base, "examId": "kyoritsu_2026_2-1_math", "mode": "practice", "gradeFilter": 5, "itemIds": ids(3)},  # partial
            {**base, "examId": None, "mode": "practice", "items": ["x#1"], "redoOf": "kyoritsu_2026_2-1_math"}]
    official = [{"date": "2026-10-12", "scores": {"math": {"score": 120, "max": 200}}}]
    sc = exam_scores(atts, meta, PLAN, official)
    assert [(s["kind"], s["percent"]) for s in sc] == [("target", 0.6), ("kumiwake", 0.6), ("target", 0.6), ("official", 0.6)]


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


def test_week_goals_on_track_climbs_toward_target(unknown_schools):
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


def test_week_goals_missed_week_bumps_volume_and_flags_risk(unknown_schools):
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


# --------------------------------------------------------------- 今週の課題

def _meta(school, year, session, subject, items=20, minutes=50, g6=0):
    return {"school": school, "year": year, "session": session, "subject": subject, "school_name": school,
            "session_label": session, "subject_label": subject, "time_limit_min": minutes,
            "item_count": items, "grade_counts": {"5": items - g6, **({"6": g6} if g6 else {})}}


META = {
    "kumiwake_2026_r1_math": _meta("kumiwake", 2026, "r1", "math"),
    "kumiwake_2026_r2_math": _meta("kumiwake", 2026, "r2", "math"),
    "kyoritsu_2024_2-1_math": _meta("kyoritsu", 2024, "2-1", "math", g6=10),
    "kyoritsu_2026_2-1_math": _meta("kyoritsu", 2026, "2-1", "math"),
    "shinagawa_2024_r1_math": _meta("shinagawa", 2024, "r1", "math"),
    "shinagawa_2025_r1_math": _meta("shinagawa", 2025, "r1", "math"),
    "chuo_2026_1_math": _meta("chuo", 2026, "1", "math"),
}


def test_exam_queue_order_and_reserved_latest_year():
    q = goals.exam_queue(META, PLAN, MON)
    assert q == ["kumiwake_2026_r1_math", "kumiwake_2026_r2_math", "kyoritsu_2024_2-1_math",
                 "shinagawa_2024_r1_math", "chuo_2026_1_math"]       # 共立 2026 / 品川 2025 (latest) held back
    late = goals.exam_queue(META, PLAN, dt.datetime(2027, 12, 6, tzinfo=JST))
    assert late[-2:] == ["shinagawa_2025_r1_math", "kyoritsu_2026_2-1_math"]   # 直前期: latest years last


def test_weekly_assignments_budget_review_and_grade():
    atts = [{"status": "graded", "examId": "kumiwake_2026_r1_math", "submittedAt": "2026-10-05T00:00:00+00:00"}]
    old = MON - dt.timedelta(days=10)
    outs = [{"t": old, "examId": "kumiwake_2026_r1_math", "itemId": f"kumiwake_2026_r1_math#{i}", "subject": "math",
             "correct": i < 12, "pending": False, "grade": 5} for i in range(20)]
    r = goals.weekly_assignments(outs, atts, META, PLAN, MON)
    assert r["grade"] == 5 and r["budget"] == 180
    kinds = [(i["kind"], i["examId"], i["minutes"]) for i in r["items"]]
    assert kinds[-1] == ("review", "kumiwake_2026_r1_math", 20)          # 8 wrong of 20 -> 50 * 8/20
    news = [k for k in kinds if k[0] == "new"]
    assert [k[1] for k in news] == ["kumiwake_2026_r2_math", "kyoritsu_2024_2-1_math", "shinagawa_2024_r1_math",
                                    "chuo_2026_1_math"]                  # 195 min: within the 10% overrun
    assert news[1][2] == 25                                              # 小5: 10 of 20 items -> 25 min
    assert sum(k[2] for k in kinds) <= 180 * goals.OVERRUN
    # a try within the last REVIEW_GAP_DAYS -> no やり直し yet
    recent = [{**o, "t": MON - dt.timedelta(days=2)} for o in outs]
    assert all(i["kind"] == "new" for i in goals.weekly_assignments(recent, atts, META, PLAN, MON)["items"])


def test_6th_grade_brings_filtered_exams_back():
    atts = [{"status": "graded", "examId": "kyoritsu_2024_2-1_math", "gradeFilter": 5, "itemIds": ["x"] * 10,
             "submittedAt": "2026-10-05T00:00:00+00:00"}]
    may = dt.datetime(2027, 5, 3, tzinfo=JST)
    assert "kyoritsu_2024_2-1_math" in goals.done_exams(atts, META, 5)
    assert "kyoritsu_2024_2-1_math" not in goals.done_exams(atts, META, goals.grade_now(PLAN, may))


def test_assignment_status():
    asg = {"items": [{"kind": "new", "examId": "a"}, {"kind": "review", "examId": "b"}, {"kind": "new", "examId": "c"}]}
    atts = [{"status": "graded", "examId": "a", "submittedAt": "2026-10-20T00:00:00+00:00"},
            {"status": "graded", "examId": None, "items": ["b#1"], "redoOf": "b", "submittedAt": "2026-10-21T00:00:00+00:00"},
            {"status": "graded", "examId": "c", "submittedAt": "2026-10-10T00:00:00+00:00"}]     # before the week
    assert goals.assignment_status(asg, atts, "2026-10-19") == [True, True, False]


def test_next_week_only_when_all_done_and_counts_early_work():
    week = goals.weekly_assignments([], [], META, PLAN, MON)
    out = {"weekStart": "2026-10-19", "assignments": week,
           "assignmentsDone": goals.assignment_status(week, [], "2026-10-19")}
    assert goals.next_week(out, [], [], META, PLAN, MON) is None            # nothing done yet
    first = [{"status": "graded", "examId": it["examId"], "submittedAt": "2026-10-21T00:00:00+00:00"}
             for it in week["items"]]
    out["assignmentsDone"] = goals.assignment_status(week, first, "2026-10-19")
    assert goals.all_done(out)
    wed = dt.datetime(2026, 10, 21, 12, tzinfo=JST)
    nxt = goals.next_week(out, [], first, META, PLAN, wed)
    assert nxt["weekStart"] == "2026-10-26"
    assert not {i["examId"] for i in nxt["assignments"]["items"]} & {i["examId"] for i in week["items"]}
    # work done ahead (Thursday, before next Monday) counts toward next week's frozen list
    eid = nxt["assignments"]["items"][0]["examId"]
    early = first + [{"status": "graded", "examId": eid, "submittedAt": "2026-10-22T00:00:00+00:00"}]
    assert goals.assignment_status(nxt["assignments"], early, "2026-10-26")[0] is True
    again = goals.next_week(out, [], early, META, PLAN, wed, existing=nxt["assignments"])
    assert again["assignments"] is nxt["assignments"]                       # frozen list reused


# --------------------------------------------------------------- 全体計画

@pytest.fixture
def no_upcoming(monkeypatch):
    monkeypatch.setitem(goals.CONFIG, "upcoming", {})


def test_roadmap_projects_queue_and_6th_grade_return(no_upcoming):
    r = goals.roadmap([], META, PLAN, MON)
    assert r["weeks"][0]["weekStart"] == "2026-10-19" and r["weeks"][-1]["weekStart"] < r["examDate"]
    assert r["newBudget"] == round(180 * (1 - PLAN["review_share"]))
    first = [i["examId"] for w in r["weeks"] for i in w["items"]]
    assert first[:2] == ["kumiwake_2026_r1_math", "kumiwake_2026_r2_math"]
    # 共立 2024 has 6年 items: assigned filtered at 小5, again in full at 6年; 組分け (all 小5) only once
    assert first.count("kyoritsu_2024_2-1_math") == 2 and first.count("kumiwake_2026_r1_math") == 1
    w6 = next(w for w in r["weeks"] if any(i["examId"] == "kyoritsu_2024_2-1_math" for i in w["items"]) and w["grade"] is None)
    assert w6["weekStart"] >= PLAN["grade6_from"] and w6["phase"] == "6年 前期"
    # reserved latest years only in the 直前期
    late = [w for w in r["weeks"] if any(i["examId"] == "kyoritsu_2026_2-1_math" for i in w["items"])]
    assert late and all(w["weekStart"] >= "2027-11-29" for w in late) and late[0]["phase"] in ("6年 後期", "直前期")
    assert [m["label"] for m in r["milestones"] if m.get("exam")] == ["入試：栄東", "入試：共立女子・品川女子学院中等部"]


def test_roadmap_keeps_frozen_weeks(no_upcoming):
    r = goals.roadmap([], META, PLAN, MON, scheduled={"2026-10-19": ["chuo_2026_1_math"]})
    assert [i["examId"] for i in r["weeks"][0]["items"]] == ["chuo_2026_1_math"]
    assert "chuo_2026_1_math" not in [i["examId"] for w in r["weeks"][1:] for i in w["items"]]


def test_history_assigned_vs_done():
    docs = [{"weekStart": "2026-10-12", "assignments": {"items": [
                {"kind": "new", "examId": "a", "label": "A", "minutes": 50},
                {"kind": "new", "examId": "b", "label": "B", "minutes": 30}]}},
            {"weekStart": "2026-10-19", "assignments": {"items": [{"kind": "new", "examId": "c", "label": "C", "minutes": 10}]}}]
    atts = [{"status": "graded", "examId": "a", "submittedAt": "2026-10-14T00:00:00+00:00"}]
    h = goals.history(docs, atts, before="2026-10-19")
    assert h == [{"weekStart": "2026-10-12", "items": 2, "done": 1, "minutes": 80, "doneMinutes": 50, "missed": ["B"]}]


def test_upcoming_planned_material(monkeypatch):
    monkeypatch.setitem(goals.CONFIG, "upcoming", {
        "kumiwake": {"day": 22, "rounds": [{"month": "2026-10", "label": "5年 第6回"}, {"month": "2026-11", "label": "5年 第7回"},
                                           {"month": "2027-03", "label": "6年 第1回"}]},
        "papers": [{"school": "kyoritsu", "year": 2027, "available": "2027-02-15"},
                   {"school": "shinagawa", "year": 2025, "available": "2027-02-15"}]})     # 2025 already real
    meta = {**META, "kumiwake_2026_r6_math": {**_meta("kumiwake", 2026, "r6", "math"), "session_label": "第6回 (10月)"}}
    up = goals.upcoming_meta(meta)
    assert sorted(k for k in up if "kumiwake" in k) == ["planned:kumiwake_202611_math", "planned:kumiwake_202703_math"]  # 10月 is real
    assert up["planned:kumiwake_202703_math"]["session_label"] == "6年 第1回 (3月・予定)"
    assert up["planned:kumiwake_202611_math"]["available"] == "2026-11-22"
    assert sorted(k for k in up if "kyoritsu" in k) == ["planned:kyoritsu_2027_2-1_math"]   # modelled on the latest real year
    assert not any("shinagawa" in k for k in up)
    r = goals.roadmap([], meta, PLAN, MON)
    weeks = {i["examId"]: w["weekStart"] for w in r["weeks"] for i in w["items"]}
    assert weeks["planned:kumiwake_202611_math"] >= "2026-11-16"        # not before it exists (week of 11/22)
    assert all(i.get("planned") for w in r["weeks"] for i in w["items"] if i["examId"].startswith("planned:"))
    # once 共立 2027 exists it is the reserved latest year; 2026 moves into the normal queue
    assert weeks["planned:kyoritsu_2027_2-1_math"] >= PLAN["reserve_from"][:8]
    assert weeks["kyoritsu_2026_2-1_math"] < PLAN["reserve_from"]


def test_phases_follow_juku_terms():
    assert [goals.phase_of(PLAN, dt.date.fromisoformat(d)) for d in
            ("2026-12-28", "2027-01-04", "2027-05-31", "2027-06-07", "2027-12-06")] ==         ["5年", "6年 前期", "6年 前期", "6年 後期", "直前期"]
    labels = [m["label"] for m in goals.milestones(PLAN)]
    assert labels[:2] == ["6年 前期スタート（過去問は全問で）", "6年 後期スタート（過去問を本番形式で）"]
