"""Adaptive weekly goals (今週の目標) toward the 2028 入試. Pure functions (Cloud Function, dev server, unit tests).

Every week (Monday 00:00 JST) each subject gets
  goalAccuracy : the accuracy to reach this week. Climbs from the student's current level toward the final target
                 (第一志望's 合格点 + margin) so that the target is reached DEADLINE_WEEKS before the exam; a missed
                 week is carried automatically because the next week starts from the (lower) measured level.
  goalItems    : questions to solve: median of the last 4 weeks, +10% after a missed week, clamped.
  focus        : weakest 分野 weighted by how often they appear in the target schools' past papers.
Goals are computed only from data BEFORE the week starts, and main.py freezes them in weeklyGoals/{weekStart},
so plan vs actual stays comparable later. Inputs: analytics.outcomes(), exam_scores(), analytics.topic_stats().
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from statistics import median

JST = dt.timezone(dt.timedelta(hours=9))
SUBJECTS = ("math", "japanese", "science", "social")
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


def exam_scores(attempts: list[dict], exam_meta: dict[str, dict], plan: dict,
                official: list[dict] | None = None) -> list[dict]:
    """Whole-exam results as level signals: [{t, subject, percent (0-1), kind}].
    kind: target (第一/第二志望 past paper), school (other school), kumiwake (組分け done in the app),
    official (組分け score sent by the parent: {date, scores: {subject: {score, max}}})."""
    out = []
    for a in attempts:
        meta = exam_meta.get(a.get("examId") or "")
        if (not meta or a.get("status") != "graded" or a.get("mode") == "practice" or a.get("itemIds")
                or a.get("gradeFilter") or a.get("percent") is None):
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


def with_actuals(goals: dict, outs: list[dict]) -> dict:
    """Attach this week's live progress (questions / accuracy so far) to frozen goals."""
    ws = dt.datetime.fromisoformat(goals["weekStart"]).replace(tzinfo=JST)
    actual = {s: counts(outs, ws, ws + dt.timedelta(weeks=1), s) for s in SUBJECTS}
    return {**goals, "actual": actual}
