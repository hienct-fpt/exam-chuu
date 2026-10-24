"""Adaptive weekly goals (今週の目標) toward the 2028 入試. Pure functions (Cloud Function, dev server, unit tests).

Every week (Monday 00:00 JST) each subject gets
  goalAccuracy : the accuracy to reach this week. Climbs from the student's current level toward the final target
                 (第一志望's 合格点 + margin) so that the target is reached DEADLINE_WEEKS before the exam; a missed
                 week is carried automatically because the next week starts from the (lower) measured level.
  goalItems    : questions to solve: median of the last 4 weeks, +10% after a missed week, clamped.
  focus        : weakest 分野 weighted by how often they appear in the target schools' past papers.
plus 今週の課題 (weekly_assignments): plan.weekly_minutes of work = new exams from a fixed queue (組分け -> 共立 /
品川 oldest first -> 栄東 / 中央; each school's latest year kept for the 直前期) + やり直し of done exams (the
items still wrong or left blank, at least a week after the last try).
Goals are computed only from data BEFORE the week starts, and main.py freezes them in weeklyGoals/{weekStart},
so plan vs actual stays comparable later. Inputs: analytics.outcomes(), exam_scores(), analytics.topic_stats().
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path
from statistics import median

JST = dt.timezone(dt.timedelta(hours=9))
SUBJECTS = ("math", "japanese", "science", "social")
GAP_FLOOR = 0.02      # やり直し share floor per subject (accuracy share added to its gap before weighting)
CONFIG = json.loads((Path(__file__).resolve().parent / "schools.json").read_text(encoding="utf-8"))

DEFAULT_TARGET = 0.70   # final target while the school's 合格点 is unknown (flagged 仮)
MAX_TARGET = 0.95
DEADLINE_WEEKS = 8      # reach the target this many weeks before the exam (過去問・直前期 buffer)
MAX_STEP = 0.03         # max accuracy increase asked per week; a larger need is flagged atRisk
LEVEL_WEEKS = 4         # item accuracy window
LEVEL_WEEK_WEIGHTS = (1.0, 0.8, 0.6, 0.4)   # newest week first
MIN_LEVEL_ITEMS = 10    # fewer graded items in the window -> item accuracy not used
EXAM_WINDOW_WEEKS = 12  # full-exam / 組分け scores older than this are ignored
SCORE_WEIGHT = {"items": 1.0, "target": 2.0, "school": 1.0, "kumiwake": 1.0, "official": 2.0}
DEFAULT_ITEMS, MIN_ITEMS, MAX_ITEMS = 20, 15, 80
FOCUS_K = 2


def week_start(t: dt.datetime) -> dt.datetime:
    """Monday 00:00 JST of the week containing t (aware datetime)."""
    j = t.astimezone(JST)
    return (j - dt.timedelta(days=j.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def plan_of(override: dict | None = None) -> dict:
    return {**CONFIG["plan"], **(override or {})}


def exam_date(plan: dict, school: str | None = None) -> dt.date:
    """Earliest 入試 day of the school (default: 第一志望) in plan.exam_year."""
    dates = [x["date"] for x in CONFIG["schools"][school or plan["first"]]["sessions"].values()]
    return min(dt.date(plan["exam_year"], int(d[:2]), int(d[3:])) for d in dates)


def _school_rates(school: str, subject: str, margin: float) -> list[tuple[float, str]]:
    """Candidate target rates from one school's rounds: 合格者平均 rate as is (already above the line), else the
    subject line, else the round's total line, else 受験者平均 (about half pass), + margin."""
    sch = CONFIG["schools"][school]
    out = []
    for x in sch["sessions"].values():
        if x.get("goal") is False:
            continue
        sub, tot = (x.get("subjects") or {}).get(subject) or {}, x.get("total") or {}
        if not (x.get("subjects") or {}) and not tot.get("line"):
            continue
        name = f"{sch['name']} {x.get('label', '')}"
        if sub.get("pass_avg") is not None and sub.get("max"):
            out.append((sub["pass_avg"] / sub["max"], f"{name} 合格者平均"))
        elif sub.get("line") is not None and sub.get("max"):
            out.append((sub["line"] / sub["max"] + margin, f"{name} 合格ライン+{round(margin * 100)}%"))
        elif not x.get("subjects") and tot.get("line") is not None and tot.get("max"):
            out.append((tot["line"] / tot["max"] + margin, f"{name} 合格ライン+{round(margin * 100)}%"))
        elif sub.get("examinee_avg") is not None and sub.get("max"):   # e.g. 共立: only 受験者平均 is published
            out.append((sub["examinee_avg"] / sub["max"] + margin, f"{name} 受験者平均+{round(margin * 100)}%"))
    return out


def targets(plan: dict) -> dict[str, dict]:
    """Final target accuracy per subject: the highest known requirement of 第一志望 / 第二志望 (both must be
    passable), or DEFAULT_TARGET (provisional) while nothing is known."""
    out = {}
    for s in SUBJECTS:
        cands = [c for sch in (plan["first"], plan["second"]) for c in _school_rates(sch, s, plan["margin"])]
        if cands:
            rate, basis = max(cands)
            out[s] = {"target": round(min(MAX_TARGET, rate), 2), "provisional": False, "basis": basis}
        else:
            out[s] = {"target": DEFAULT_TARGET, "provisional": True, "basis": None}
    return out


def _t(v) -> dt.datetime:
    """analytics._ts, plus naive values (e.g. a bare "2026-10-12" 組分け date) read as JST."""
    from analytics import _ts
    t = _ts(v)
    return t if t.tzinfo else t.replace(tzinfo=JST)


def filtered_count(meta: dict, g: int | None) -> int:
    """Items of an exam a student at grade g answers (the 小g filter keeps items tagged grade <= g)."""
    if not g:
        return meta.get("item_count") or 0
    return sum(n for k, n in (meta.get("grade_counts") or {}).items() if str(k).isdigit() and int(k) <= g)


def whole_exam(a: dict, meta: dict) -> bool:
    """A graded exam attempt that covered every item of the exam -- or every item left by its 小N filter
    (the app stores filtered exam attempts with mode "practice" + itemIds). やり直し sets carry `items`."""
    if a.get("items") or not a.get("examId"):
        return False
    ids = a.get("itemIds")
    return not ids or len(ids) >= filtered_count(meta, a.get("gradeFilter"))


def exam_scores(attempts: list[dict], exam_meta: dict[str, dict], plan: dict,
                official: list[dict] | None = None) -> list[dict]:
    """Whole-exam results as level signals: [{t, subject, percent (0-1), kind}].
    kind: target (第一/第二志望 past paper), school (other school), kumiwake (組分け done in the app),
    official (組分け score sent by the parent: {date, scores: {subject: {score, max}}})."""
    out = []
    for a in attempts:
        meta = exam_meta.get(a.get("examId") or "")
        if not meta or a.get("status") != "graded" or a.get("percent") is None or not whole_exam(a, meta):
            continue
        school = meta.get("school")
        kind = "kumiwake" if school == "kumiwake" else "target" if school in (plan["first"], plan["second"]) else "school"
        out.append({"t": _t(a.get("submittedAt") or a.get("gradedAt")), "subject": meta.get("subject"),
                    "percent": a["percent"] / 100, "kind": kind})
    for o in official or []:
        for s, v in (o.get("scores") or {}).items():
            if v.get("max"):
                out.append({"t": _t(o.get("date")), "subject": s, "percent": v["score"] / v["max"], "kind": "official"})
    return sorted(out, key=lambda x: x["t"])


def counts(outs: list[dict], start: dt.datetime, end: dt.datetime, subject: str) -> dict:
    sel = [o for o in outs if start <= o["t"] < end and o["subject"] == subject and not o["pending"]]
    c = sum(1 for o in sel if o["correct"])
    return {"items": len(sel), "correct": c, "accuracy": round(c / len(sel), 3) if sel else None}


def current_level(outs: list[dict], scores: list[dict], cutoff: dt.datetime, subject: str) -> dict:
    """Weighted mix of recent item accuracy and the latest whole-exam scores, all strictly before cutoff."""
    parts = []
    num = den = 0.0
    for i, w in enumerate(LEVEL_WEEK_WEIGHTS[:LEVEL_WEEKS]):
        c = counts(outs, cutoff - dt.timedelta(weeks=i + 1), cutoff - dt.timedelta(weeks=i), subject)
        num += w * c["correct"]
        den += w * c["items"]
    n = sum(1 for o in outs if cutoff - dt.timedelta(weeks=LEVEL_WEEKS) <= o["t"] < cutoff
            and o["subject"] == subject and not o["pending"])
    if n >= MIN_LEVEL_ITEMS and den:
        parts.append(("items", num / den))
    since = cutoff - dt.timedelta(weeks=EXAM_WINDOW_WEEKS)
    latest: dict[str, float] = {}
    for s in scores:
        if s["subject"] == subject and since <= s["t"] < cutoff:
            latest[s["kind"]] = s["percent"]       # sorted by time -> keeps the newest per kind
    if "official" in latest:
        latest.pop("kumiwake", None)              # the parent's official 組分け score supersedes the app's grading
    parts += list(latest.items())
    if not parts:
        return {"level": None, "sources": []}
    tw = sum(SCORE_WEIGHT[k] for k, _ in parts)
    return {"level": round(sum(SCORE_WEIGHT[k] * v for k, v in parts) / tw, 3), "sources": sorted(k for k, _ in parts)}


def topic_frequency(items: list[dict], plan: dict) -> dict[str, dict[str, float]]:
    """Share of each 分野 in the target schools' past papers per subject (第二志望 counts half).
    items: [{school, subject, topic}]"""
    w = {plan["first"]: 1.0, plan["second"]: 0.5}
    tot: dict[str, dict[str, float]] = {}
    for it in items:
        if it.get("school") in w and it.get("topic"):
            d = tot.setdefault(it["subject"], {})
            d[it["topic"]] = d.get(it["topic"], 0.0) + w[it["school"]]
    return {s: {t: round(v / sum(d.values()), 4) for t, v in d.items()} for s, d in tot.items()}


def focus_topics(stats: dict[str, dict], freq: dict[str, float], k: int = FOCUS_K) -> list[dict]:
    """Highest (1 - mastery) x exam frequency first; never-practised 分野 count as mastery 0.5."""
    rows = []
    for t, f in freq.items():
        m = (stats.get(t) or {}).get("mastery")
        rows.append({"topic": t, "mastery": m, "freq": f, "score": round((1 - (0.5 if m is None else m)) * f, 4)})
    rows.sort(key=lambda r: (-r["score"], r["topic"]))
    return rows[:k]


def week_goals(outs: list[dict], scores: list[dict], stats: dict[str, dict], freq: dict[str, dict[str, float]],
               plan: dict, now: dt.datetime, prev: dict | None = None) -> dict:
    """Goals for the week containing `now`. prev = last week's frozen goals (for the missed-week bump)."""
    ws = week_start(now)
    edate = exam_date(plan)
    deadline = edate - dt.timedelta(weeks=DEADLINE_WEEKS)
    weeks_left = max(1, math.ceil((deadline - ws.date()).days / 7))
    tg = targets(plan)
    subjects = {}
    for s in SUBJECTS:
        lvl = current_level(outs, scores, ws, s)
        vols = [counts(outs, ws - dt.timedelta(weeks=i + 1), ws - dt.timedelta(weeks=i), s)["items"] for i in range(4)]
        last = counts(outs, ws - dt.timedelta(weeks=1), ws, s)
        pg = ((prev or {}).get("subjects") or {}).get(s) or {}
        behind = bool(pg) and (last["items"] < (pg.get("goalItems") or 0)
                               or (pg.get("goalAccuracy") is not None and last["accuracy"] is not None
                                   and last["accuracy"] < pg["goalAccuracy"]))
        base = median(vols) if any(vols) else DEFAULT_ITEMS
        goal_items = max(MIN_ITEMS, min(MAX_ITEMS, round(base * (1.1 if behind else 1.0))))
        target = tg[s]["target"]
        goal_acc, at_risk = None, False
        if lvl["level"] is not None:
            need = max(0.0, target - lvl["level"]) / weeks_left
            at_risk = need > MAX_STEP
            goal_acc = round(min(target, lvl["level"] + min(need, MAX_STEP)), 2) if need else target
        subjects[s] = {"target": target, "provisional": tg[s]["provisional"], "basis": tg[s]["basis"], "level": lvl["level"],
                       "levelSources": lvl["sources"], "goalAccuracy": goal_acc, "goalItems": goal_items,
                       "behind": behind, "atRisk": at_risk,
                       "focus": focus_topics({t: v for t, v in stats.items() if v.get("subject") == s}, freq.get(s) or {})}
    return {"weekStart": ws.date().isoformat(), "examDate": edate.isoformat(), "deadline": deadline.isoformat(),
            "weeksLeft": weeks_left, "first": plan["first"], "second": plan["second"],
            "firstName": CONFIG["schools"][plan["first"]]["name"], "secondName": CONFIG["schools"][plan["second"]]["name"],
            "subjects": subjects}


def with_actuals(goals: dict, outs: list[dict], attempts: list[dict] | None = None) -> dict:
    """Attach this week's live progress (questions / accuracy so far, assignments done) to frozen goals."""
    ws = dt.datetime.fromisoformat(goals["weekStart"]).replace(tzinfo=JST)
    actual = {s: counts(outs, ws, ws + dt.timedelta(weeks=1), s) for s in SUBJECTS}
    out = {**goals, "actual": actual}
    if goals.get("assignments"):
        out["assignmentsDone"] = assignment_status(goals["assignments"], attempts or [], goals["weekStart"])
    return out


# --------------------------------------------------------------- 今週の課題 (weekly assignments)

SUBJECT_ORDER = {s: i for i, s in enumerate(("math", "japanese", "science", "social"))}
REVIEW_GAP_DAYS = 6     # redo an exam's wrong items at least this long after the last try
MIN_MINUTES = 10
OVERRUN = 1.1         # a new exam may push the week up to 10% over plan.weekly_minutes


def grade_now(plan: dict, ws: dt.datetime) -> int | None:
    """小5 filter until the child becomes 6年 (plan.grade6_from), then whole exams."""
    return 5 if ws.date() < dt.date.fromisoformat(plan["grade6_from"]) else None


def minutes(meta: dict, n: int) -> int:
    """Time for n of the exam's items, scaled from its 制限時間, rounded to 5 minutes."""
    total = meta.get("item_count") or n or 1
    return max(MIN_MINUTES, round((meta.get("time_limit_min") or 50) * n / total / 5) * 5)


def label(meta: dict) -> str:
    if meta.get("school") == "kumiwake":
        return f"組分け {meta.get('session_label', '')} {meta.get('subject_label', '')}".strip()
    return f"{meta.get('school_name', '')} {meta.get('year', '')}年度 {meta.get('session_label', '')} {meta.get('subject_label', '')}".strip()


def exam_queue(exam_meta: dict[str, dict], plan: dict, ws: dt.datetime) -> list[str]:
    """New-exam order: 組分け rounds, then 第一/第二志望 interleaved by year (oldest first), then the extra
    schools; each target school's latest year only from plan.reserve_from (直前期). Subjects of one set together."""
    def sets(school):
        rows = [(m.get("year") or 0, str(m.get("session") or ""), SUBJECT_ORDER.get(m.get("subject"), 9), eid)
                for eid, m in exam_meta.items()
                if m.get("school") == school and (not m.get("available") or m["available"] <= ws.date().isoformat())]
        return sorted(rows)
    reserve_open = ws.date() >= dt.date.fromisoformat(plan["reserve_from"])
    queue = [r[3] for r in sets("kumiwake")]
    target, reserved = [], []
    for rank, school in enumerate((plan["first"], plan["second"])):
        rows = sets(school)
        latest = max((r[0] for r in rows), default=None)
        for r in rows:
            (reserved if r[0] == latest else target).append((r[0], rank, r[1], r[2], r[3]))
    queue += [r[4] for r in sorted(target)]
    for school in plan.get("extra_schools", []):
        queue += [r[3] for r in sets(school)]
    if reserve_open:
        queue += [r[4] for r in sorted(reserved)]
    return queue


def done_exams(attempts: list[dict], exam_meta: dict[str, dict], g: int | None) -> set[str]:
    """Exams already done at the current grade: at 小5 any graded attempt; at 6年 only one that covered the
    whole exam (a 小5-filtered attempt of an exam with 6年 items comes back as new)."""
    done = set()
    for a in attempts:
        meta = exam_meta.get(a.get("examId") or "")
        if not meta or a.get("status") != "graded" or a.get("items"):
            continue
        if g or not a.get("itemIds") or len(a["itemIds"]) >= (meta.get("item_count") or 0):
            done.add(a["examId"])
    return done


def review_units(outs: list[dict], exam_meta: dict[str, dict], g: int | None, ws: dt.datetime) -> list[dict]:
    """やり直し candidates per done exam: items whose latest outcome is wrong / blank (grade <= g), lowest
    accuracy first; skipped if the exam was touched within REVIEW_GAP_DAYS."""
    latest: dict[str, dict] = {}
    for o in outs:
        if o["examId"] in exam_meta and o["t"] < ws and not o["pending"]:
            latest[o["itemId"]] = o
    by_exam: dict[str, list[dict]] = {}
    for o in latest.values():
        by_exam.setdefault(o["examId"], []).append(o)
    units = []
    for eid, lst in by_exam.items():
        if max(o["t"] for o in lst) > ws - dt.timedelta(days=REVIEW_GAP_DAYS):
            continue
        wrong = sorted(o["itemId"] for o in lst if not o["correct"] and (not g or not o.get("grade") or o["grade"] <= g))
        if wrong:
            acc = sum(1 for o in lst if o["correct"]) / len(lst)
            units.append({"kind": "review", "examId": eid, "subject": exam_meta[eid].get("subject"),
                          "label": label(exam_meta[eid]), "items": wrong, "minutes": minutes(exam_meta[eid], len(wrong)),
                          "accuracy": round(acc, 3)})
    units.sort(key=lambda u: (u["accuracy"], u["examId"]))
    return units


def in_focus(plan: dict, ws: dt.datetime) -> bool:
    """過去問集中 window (plan.focus): weeks with spare time get whole past papers again."""
    f = plan.get("focus")
    return bool(f) and f["from"] <= ws.date().isoformat() <= f["until"]


def last_done(attempts: list[dict], exam_meta: dict[str, dict]) -> dict[str, tuple[dt.datetime, float]]:
    """{examId: (last graded attempt time, its percent)} for exams done as an exam (not a やり直し set)."""
    out: dict[str, tuple[dt.datetime, float]] = {}
    for a in attempts:
        eid = a.get("examId")
        if eid in exam_meta and a.get("status") == "graded" and not a.get("items"):
            t = _t(a.get("submittedAt") or a.get("gradedAt"))
            if eid not in out or t > out[eid][0]:
                out[eid] = (t, a.get("percent") or 0)
    return out


def retake_order(last: dict[str, tuple[dt.datetime, float]], exam_meta: dict[str, dict], plan: dict,
                 ws: dt.datetime, exclude: set[str]) -> list[str]:
    """2回目 candidates: school past papers (第一/第二志望 first, then extra_schools) last done at least
    focus.retake_gap_weeks ago, longest ago first, lower score first; the reserved latest year stays reserved."""
    rank = {plan["first"]: 0, plan["second"]: 0, **{s: 1 for s in plan.get("extra_schools", [])}}
    gap = dt.timedelta(weeks=(plan.get("focus") or {}).get("retake_gap_weeks", 8))
    allowed = set(exam_queue(exam_meta, plan, ws))
    rows = [(rank[exam_meta[e].get("school")], t, pct, e) for e, (t, pct) in last.items()
            if e in allowed and exam_meta[e].get("school") in rank and e not in exclude and t <= ws - gap]
    return [r[3] for r in sorted(rows)]


def subject_gaps(goal_subjects: dict | None) -> dict[str, float]:
    """{subject: target − current level} (accuracy share, ≥ 0) from week_goals()["subjects"]; no level -> left out."""
    return {s: round(max(0.0, v["target"] - v["level"]), 4) for s, v in (goal_subjects or {}).items()
            if v.get("level") is not None and v.get("target") is not None}


def review_shares(gaps: dict[str, float], subjects) -> dict[str, float]:
    """Share of the やり直し time per subject ∝ its gap to the target (+ a small floor, so no subject with
    wrong answers gets nothing; a subject without a level counts as the average gap)."""
    known = [gaps[s] for s in subjects if s in gaps]
    avg = sum(known) / len(known) if known else 0.0
    w = {s: (gaps.get(s, avg) + GAP_FLOOR) for s in subjects}
    tot = sum(w.values()) or 1.0
    return {s: round(v / tot, 3) for s, v in w.items()}


def pick_review(units: list[dict], minutes_budget: int, gaps: dict[str, float] | None) -> list[dict]:
    """やり直し within the budget. Without gaps: lowest accuracy first. With gaps: each subject first gets its
    gap-weighted share (its own units, lowest accuracy first), then the time left goes to the biggest gaps."""
    if not gaps:
        out, used = [], 0
        for u in units:
            if used + u["minutes"] <= minutes_budget:
                out.append(u)
                used += u["minutes"]
        return out
    shares = review_shares(gaps, sorted({u["subject"] for u in units}))
    out, used, spent = [], 0, {}
    for u in units:                                       # pass 1: each subject within its share
        s = u["subject"]
        if spent.get(s, 0) + u["minutes"] <= shares.get(s, 0) * minutes_budget and used + u["minutes"] <= minutes_budget:
            out.append(u)
            used += u["minutes"]
            spent[s] = spent.get(s, 0) + u["minutes"]
    rest = sorted((u for u in units if u not in out), key=lambda u: (-gaps.get(u["subject"], 0), u["accuracy"], u["examId"]))
    for u in rest:                                        # pass 2: leftover time, biggest gap first
        if used + u["minutes"] <= minutes_budget:
            out.append(u)
            used += u["minutes"]
    return out


def gap_order(queue: list[str], exam_meta: dict[str, dict], gaps: dict[str, float] | None) -> list[str]:
    """Keep the queue order of the sets (組分け round / school year+回), but inside one set put the subject with the
    biggest gap first — if the week's time runs out mid-set, the subject furthest from its target is not the one cut."""
    if not gaps:
        return queue
    key = lambda e: (exam_meta[e].get("school"), exam_meta[e].get("year"), str(exam_meta[e].get("session")))
    out, i = [], 0
    while i < len(queue):
        j = i
        while j < len(queue) and key(queue[j]) == key(queue[i]):
            j += 1
        out += sorted(queue[i:j], key=lambda e: -gaps.get(exam_meta[e].get("subject"), 0))   # stable within ties
        i = j
    return out


def weekly_assignments(outs: list[dict], attempts: list[dict], exam_meta: dict[str, dict], plan: dict,
                       now: dt.datetime, created: dt.datetime | None = None, gaps: dict[str, float] | None = None) -> dict:
    """This week's work within plan.weekly_minutes: やり直し up to review_share of the time, the rest new exams
    in queue order (an unfinished assignment stays at the head of the queue next week). `gaps` (subject_gaps of the
    week's goals) weights the やり直し time by each subject's gap to its target and orders subjects inside a set."""
    ws = week_start(now)
    g = grade_now(plan, ws)
    budget = plan["weekly_minutes"]
    units = review_units(outs, exam_meta, g, ws)
    review = pick_review(units, round(budget * plan["review_share"]), gaps)
    used = sum(u["minutes"] for u in review)
    done = done_exams(attempts, exam_meta, g)
    new, nused = [], 0
    pending = gap_order([eid for eid in exam_queue(exam_meta, plan, ws) if eid not in done], exam_meta, gaps)
    for eid in pending:
        m = minutes(exam_meta[eid], filtered_count(exam_meta[eid], g) or exam_meta[eid].get("item_count") or 1)
        if used + nused + m > budget * OVERRUN and new:
            break
        if used + nused + m <= budget * OVERRUN or not new:
            new.append({"kind": "new", "examId": eid, "subject": exam_meta[eid].get("subject"),
                        "label": label(exam_meta[eid]), "minutes": m})
            nused += m
    if in_focus(plan, ws):        # 過去問集中: fill the rest of the week with whole past papers again (2回目)
        for eid in retake_order(last_done(attempts, exam_meta), exam_meta, plan, ws, {i["examId"] for i in new}):
            m = minutes(exam_meta[eid], exam_meta[eid].get("item_count") or 1)
            if used + nused + m > budget * OVERRUN:
                break
            new.append({"kind": "retake", "examId": eid, "subject": exam_meta[eid].get("subject"),
                        "label": label(exam_meta[eid]), "minutes": m})
            nused += m
    out = {"grade": g, "budget": budget, "items": new + review,
           "remaining": len(pending) - len(new), "queue": len(pending),
           "createdAt": (created or ws).isoformat()}
    if gaps:   # shown on 今週の課題: why the やり直し time is split the way it is
        out["gaps"] = gaps
        out["reviewShares"] = review_shares(gaps, sorted({u["subject"] for u in units})) if units else {}
    return out


def assignment_status(assign: dict, attempts: list[dict], week_start_iso: str) -> list[bool]:
    """Done flags for this week's assignments: a graded attempt of the exam (new) or a graded やり直し set
    (redoOf = exam) submitted since the list was made (week start, or earlier for a week worked ahead)."""
    ws = (dt.datetime.fromisoformat(assign["createdAt"]) if assign.get("createdAt")
          else dt.datetime.fromisoformat(week_start_iso).replace(tzinfo=JST))
    graded = [a for a in attempts if a.get("status") == "graded" and _t(a.get("submittedAt") or a.get("gradedAt")) >= ws]
    out = []
    for it in assign.get("items") or []:
        if it["kind"] in ("new", "retake"):
            out.append(any(a.get("examId") == it["examId"] and not a.get("items") for a in graded))
        else:
            out.append(any(a.get("redoOf") == it["examId"] for a in graded))
    return out


def all_done(goals_out: dict) -> bool:
    items = (goals_out.get("assignments") or {}).get("items") or []
    return bool(items) and all(goals_out.get("assignmentsDone") or [False])


def next_week(goals_out: dict, outs: list[dict], attempts: list[dict], exam_meta: dict[str, dict], plan: dict,
              now: dt.datetime, existing: dict | None = None) -> dict | None:
    """Once this week's 課題 are all done: next week's list so the child can work ahead. `existing` = the list
    already frozen for next week (main.py stores it on first use, so early work counts toward it)."""
    if not all_done(goals_out):
        return None
    nws = dt.datetime.fromisoformat(goals_out["weekStart"]).replace(tzinfo=JST) + dt.timedelta(weeks=1)
    asg = existing or weekly_assignments(outs, attempts, exam_meta, plan, nws, created=now,
                                         gaps=subject_gaps(goals_out.get("subjects")))
    return {"weekStart": nws.date().isoformat(), "assignments": asg,
            "assignmentsDone": assignment_status(asg, attempts, nws.date().isoformat())}


# --------------------------------------------------------------- 全体計画 (roadmap to the exam)

def term2_from(plan: dict) -> dt.date:
    """6年 後期 (juku second term, 過去問 season)."""
    return dt.date.fromisoformat(plan["term2_from"])


def phase_of(plan: dict, day: dt.date) -> str:
    """Juku terms: 5年 -> 6年 前期 (grade6_from) -> 6年 後期 (term2_from, 過去問) -> 直前期 (reserve_from)."""
    if day < dt.date.fromisoformat(plan["grade6_from"]):
        return "5年"
    if day < term2_from(plan):
        return "6年 前期"
    if day < dt.date.fromisoformat(plan["reserve_from"]):
        return "6年 後期"
    return "直前期"


def milestones(plan: dict) -> list[dict]:
    """Key dates: 6年, 直前期, the target deadline, each school's 入試 (schools on the same day share a row)."""
    edate = exam_date(plan)
    focus = [{"date": plan["focus"]["from"], "label": "過去問集中（2回目・やり直し）〜" + plan["focus"]["until"][5:].replace("-", "/")}] \
        if plan.get("focus") else []
    rows = focus + [{"date": plan["grade6_from"], "label": "6年 前期スタート（過去問は全問で）"},
            {"date": term2_from(plan).isoformat(), "label": "6年 後期スタート（過去問を本番形式で）"},
            {"date": plan["reserve_from"], "label": "直前期（各校の最新年度の過去問）"},
            {"date": (edate - dt.timedelta(weeks=DEADLINE_WEEKS)).isoformat(), "label": "最終目標の正答率に到達"}]
    by_day: dict[str, list[str]] = {}
    for s in (plan["first"], plan["second"], *plan.get("extra_schools", [])):
        if s not in CONFIG["schools"]:       # no 入試 data (e.g. 中央 is only practice material)
            continue
        by_day.setdefault(exam_date(plan, s).isoformat(), []).append(CONFIG["schools"].get(s, {}).get("name", s))
    rows += [{"date": d, "label": "入試：" + "・".join(names), "exam": True} for d, names in by_day.items()]
    return sorted(rows, key=lambda r: r["date"])


RE_MONTH = re.compile(r"\((\d{1,2})月\)")


def _kumiwake_month(meta: dict) -> str | None:
    """Calendar YYYY-MM of a real 組分け round ("第6回 (10月)"; the round's year is the school year from March)."""
    m = RE_MONTH.search(meta.get("session_label") or "")
    if not m:
        return None
    month = int(m.group(1))
    return f"{(meta.get('year') or 0) + (1 if month < 3 else 0)}-{month:02d}"


def upcoming_meta(exam_meta: dict[str, dict]) -> dict[str, dict]:
    """Planned (予定) exams for the projection: a monthly 組分け round and the schools' next papers, sized like the
    latest real exam of the same kind. Skipped once the real exam is in the bank."""
    up = CONFIG.get("upcoming") or {}
    out: dict[str, dict] = {}
    real = exam_meta.values()
    kc = up.get("kumiwake")
    if kc:
        have = {_kumiwake_month(m) for m in real if m.get("school") == "kumiwake"}
        tmpl = {}
        for m in sorted((m for m in real if m.get("school") == "kumiwake"), key=lambda m: (m.get("year") or 0, str(m.get("session")))):
            tmpl[m.get("subject")] = m
        for rnd in kc.get("rounds") or []:
            ym = rnd["month"]
            if ym in have:
                continue
            y, mo = int(ym[:4]), int(ym[5:])
            for subj, t in tmpl.items():
                out[f"planned:kumiwake_{y}{mo:02d}_{subj}"] = {
                    **{k: t.get(k) for k in ("school", "school_name", "subject", "subject_label", "time_limit_min",
                                             "item_count", "grade_counts")},
                    "year": y, "session": f"~{ym}", "session_label": f"{rnd.get('label', '')} ({mo}月・予定)",
                    "available": f"{ym}-{kc.get('day', 22):02d}", "planned": True}
    for pc in up.get("papers") or []:
        rows = [m for m in real if m.get("school") == pc["school"]]
        if not rows or any(m.get("year") == pc["year"] for m in rows):
            continue
        latest = max(m.get("year") or 0 for m in rows)
        for m in rows:
            if m.get("year") == latest:
                out[f"planned:{pc['school']}_{pc['year']}_{m.get('session')}_{m.get('subject')}"] = {
                    **m, "year": pc["year"], "available": pc["available"], "planned": True,
                    "session_label": f"{m.get('session_label', '')}（予定）"}
    return out


def roadmap(attempts: list[dict], exam_meta: dict[str, dict], plan: dict, now: dt.datetime,
            scheduled: dict[str, list[str]] | None = None) -> dict:
    """Projected new-exam schedule from now to the exam, assuming each week's plan is done: per week the
    queue fills plan.weekly_minutes x (1 - review_share) (the rest stays for やり直し). Weeks whose list is
    already frozen (`scheduled` = {weekStart: [examId]}) are taken as is. 小5-filtered work comes back at 6年."""
    scheduled = scheduled or {}
    exam_meta = {**exam_meta, **upcoming_meta(exam_meta)}
    ws = week_start(now)
    end = exam_date(plan)
    new_budget = round(plan["weekly_minutes"] * (1 - plan["review_share"]))
    sim: set[tuple[str, int | None]] = set()      # (examId, grade filter) assumed done by the plan
    last = last_done(attempts, exam_meta)           # examId -> (last time done, percent), advanced by the plan
    weeks = []
    while ws.date() < end:
        g = grade_now(plan, ws)
        key = ws.date().isoformat()
        done = done_exams(attempts, exam_meta, g) | {
            e for e, sg in sim if g or sg is None or filtered_count(exam_meta[e], sg) >= (exam_meta[e].get("item_count") or 0)}
        if key in scheduled:
            items = [e for e in scheduled[key] if e in exam_meta]
        else:
            items, used = [], 0
            for eid in exam_queue(exam_meta, plan, ws):
                if eid in done:
                    continue
                m = minutes(exam_meta[eid], filtered_count(exam_meta[eid], g) or exam_meta[eid].get("item_count") or 1)
                if used + m > new_budget * OVERRUN and items:
                    break
                items.append(eid)
                used += m
        retakes = []
        if key not in scheduled and in_focus(plan, ws):
            for eid in retake_order(last, exam_meta, plan, ws, set(items)):
                m = minutes(exam_meta[eid], exam_meta[eid].get("item_count") or 1)
                if used + m > new_budget * OVERRUN:
                    break
                retakes.append(eid)
                used += m
        sim |= {(e, g) for e in items}
        for e in items + retakes:
            last[e] = (ws, (last.get(e) or (ws, 0))[1])
        weeks.append({"weekStart": key, "grade": g, "phase": phase_of(plan, ws.date()),
                      "items": [{"examId": e, "label": label(exam_meta[e]), "subject": exam_meta[e].get("subject"),
                                 **({"planned": True} if exam_meta[e].get("planned") else {}),
                                 "minutes": minutes(exam_meta[e], filtered_count(exam_meta[e], g) or exam_meta[e].get("item_count") or 1)}
                                for e in items]
                               + [{"examId": e, "label": label(exam_meta[e]), "subject": exam_meta[e].get("subject"),
                                   "retake": True, "minutes": minutes(exam_meta[e], exam_meta[e].get("item_count") or 1),
                                   **({"planned": True} if exam_meta[e].get("planned") else {})} for e in retakes]})
        ws += dt.timedelta(weeks=1)
    last = max((i for i, w in enumerate(weeks) if w["items"]), default=None)
    return {"weeks": weeks, "milestones": milestones(plan), "examDate": end.isoformat(),
            "newBudget": new_budget, "finishWeek": weeks[last]["weekStart"] if last is not None else None,
            "totalExams": sum(1 for w in weeks for i in w["items"] if not i.get("retake")),
            "retakes": sum(1 for w in weeks for i in w["items"] if i.get("retake")),
            "focus": plan.get("focus")}


def history(weekly_docs: list[dict], attempts: list[dict], before: str) -> list[dict]:
    """Past weeks' 課題: assigned vs done (from the frozen weeklyGoals docs)."""
    out = []
    for d in sorted(weekly_docs, key=lambda d: d.get("weekStart", "")):
        asg = d.get("assignments") or {}
        if not d.get("weekStart") or d["weekStart"] >= before or not asg.get("items"):
            continue
        done = assignment_status(asg, attempts, d["weekStart"])
        out.append({"weekStart": d["weekStart"], "items": len(asg["items"]), "done": sum(done),
                    "minutes": sum(i["minutes"] for i in asg["items"]),
                    "doneMinutes": sum(i["minutes"] for i, x in zip(asg["items"], done) if x),
                    "missed": [i["label"] for i, x in zip(asg["items"], done) if not x]})
    return out
