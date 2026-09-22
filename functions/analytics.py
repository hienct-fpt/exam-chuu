"""Topic mastery analytics and practice-set selection. Pure functions (used by the Cloud Function,
the weekly digest, the local dev server and unit tests).

Inputs are graded attempts: {"submittedAt": iso str | datetime, "examId", "mode", "result": {perItem...}}.
perItem entries carry topic / grade / correct / answered / pending (see grader.py).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

DECAY = 0.85          # weight of an outcome one attempt older
MIN_CONFIDENT = 3     # outcomes needed before a mastery value is trusted
WEAK_THRESHOLD = 0.6  # mastery below this = weak topic


def _ts(v) -> dt.datetime:
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    if isinstance(v, str) and v:
        try:
            return dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            pass
    return dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def outcomes(attempts: list[dict], subject_of: dict[str, str] | None = None) -> list[dict]:
    """Flatten graded attempts into per-item outcomes, oldest first.
    [{t, examId, sid, subject, topic, grade, correct, pending, answered}]"""
    out = []
    for a in attempts:
        r = a.get("result") or {}
        if a.get("status") not in (None, "graded") or not r.get("perItem"):
            continue
        t = _ts(a.get("submittedAt") or a.get("gradedAt"))
        for key, it in r["perItem"].items():
            exam_id = it.get("examId") or a.get("examId") or (key.split("#")[0] if "#" in key else "")
            sid = it.get("sid") or (key.split("#")[1] if "#" in key else key)
            subject = it.get("subject") or (subject_of or {}).get(exam_id) or ""
            out.append({
                "t": t, "examId": exam_id, "sid": sid, "itemId": f"{exam_id}#{sid}",
                "subject": subject, "topic": it.get("topic") or "未分類", "grade": it.get("grade"),
                "correct": bool(it.get("correct")), "pending": bool(it.get("pending")),
                "answered": bool(it.get("answered")),
            })
    out.sort(key=lambda o: o["t"])
    return out


def topic_stats(outs: list[dict]) -> dict[str, dict]:
    """Per topic: attempts, correct, pending, mastery (recency-weighted accuracy), confident, lastSeen, streak.
    Pending (unmarked essays) are excluded from mastery."""
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for o in outs:
        by_topic[o["topic"]].append(o)
    stats = {}
    for topic, lst in by_topic.items():
        graded = [o for o in lst if not o["pending"]]
        n = len(graded)
        correct = sum(1 for o in graded if o["correct"])
        num = den = 0.0
        for rank, o in enumerate(reversed(graded)):  # newest first
            w = DECAY ** rank
            num += w * (1.0 if o["correct"] else 0.0)
            den += w
        mastery = round(num / den, 3) if den else None
        streak = 0
        for o in reversed(graded):
            if o["correct"]:
                streak += 1
            else:
                break
        stats[topic] = {
            "subject": next((o["subject"] for o in lst if o["subject"]), ""),
            "attempts": n, "correct": correct, "pending": sum(1 for o in lst if o["pending"]),
            "accuracy": round(correct / n, 3) if n else None,
            "mastery": mastery, "confident": n >= MIN_CONFIDENT,
            "weak": mastery is not None and n >= MIN_CONFIDENT and mastery < WEAK_THRESHOLD,
            "lastSeen": max(o["t"] for o in lst).isoformat(), "streak": streak,
            "grade": next((o["grade"] for o in lst if o.get("grade")), None),
        }
    return stats


def weak_topics(stats: dict[str, dict], subject: str | None = None, k: int = 3) -> list[tuple[str, dict]]:
    """Weakest topics first. Confident topics under the threshold come first, then low-sample low-accuracy ones."""
    rows = [(t, s) for t, s in stats.items() if (subject is None or s["subject"] == subject) and s["mastery"] is not None]
    rows.sort(key=lambda ts: (not ts[1]["confident"], ts[1]["mastery"], -ts[1]["attempts"]))
    return rows[:k]


def item_history(outs: list[dict]) -> dict[str, dict]:
    """Latest outcome per item id: {itemId: {correct, t, tries}}"""
    hist: dict[str, dict] = {}
    for o in outs:
        h = hist.setdefault(o["itemId"], {"tries": 0, "correct": False, "t": o["t"]})
        h["tries"] += 1
        h["correct"] = o["correct"] and not o["pending"]
        h["t"] = o["t"]
    return hist


def practice_set(bank_items: list[dict], topics: set[str] | None, hist: dict[str, dict], n: int = 10,
                 grade_filter: int | None = None, subject: str | None = None,
                 include_pending_types: bool = False, now: dt.datetime | None = None) -> list[dict]:
    """Pick items for practice: wrong before > never seen > correct long ago > correct recently.
    Items sharing one image (あ〜く fill-ins) are pulled in together so the crop is not shown half-answered."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cands = []
    for it in bank_items:
        if subject and it.get("subject") != subject:
            continue
        if topics is not None and (it.get("topic") or "未分類") not in topics:
            continue
        if grade_filter and not (it.get("grade") and it["grade"] <= grade_filter):
            continue
        if not include_pending_types and it.get("answer_type") in ("essay", "manual"):
            continue
        h = hist.get(it["id"])
        if h is None:
            prio, age = 1, 0.0
        elif not h["correct"]:
            prio, age = 0, (now - h["t"]).total_seconds()
        else:
            prio, age = 2, (now - h["t"]).total_seconds()
        cands.append((prio, -age, it))
    cands.sort(key=lambda c: (c[0], c[1], c[2]["id"]))
    picked: list[dict] = []
    picked_ids: set[str] = set()
    by_image: dict[str, list[dict]] = defaultdict(list)
    for it in bank_items:
        if it.get("shared_image"):
            by_image[(it.get("exam_id"), it.get("image"))].append(it)
    for _, _, it in cands:
        if it["id"] in picked_ids:
            continue
        group = by_image.get((it.get("exam_id"), it.get("image"))) if it.get("shared_image") else None
        for g in (group or [it]):
            if g["id"] not in picked_ids and (not topics or (g.get("topic") or "未分類") in topics):
                picked.append(g)
                picked_ids.add(g["id"])
        if len(picked) >= n:
            break
    return picked


def weekly_series(outs: list[dict], weeks: int = 8, now: dt.datetime | None = None) -> list[dict]:
    """[{weekStart iso, attempts, correct, accuracy}] for the last `weeks` weeks (Monday start)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    start_this = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    buckets = []
    for i in range(weeks - 1, -1, -1):
        ws = start_this - dt.timedelta(weeks=i)
        we = ws + dt.timedelta(weeks=1)
        sel = [o for o in outs if ws <= o["t"] < we and not o["pending"]]
        c = sum(1 for o in sel if o["correct"])
        buckets.append({"weekStart": ws.date().isoformat(), "attempts": len(sel), "correct": c,
                        "accuracy": round(c / len(sel), 3) if sel else None})
    return buckets


def subject_summary(stats: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for t, s in stats.items():
        subj = s["subject"] or "?"
        d = out.setdefault(subj, {"topics": 0, "attempts": 0, "correct": 0, "weak": []})
        d["topics"] += 1
        d["attempts"] += s["attempts"]
        d["correct"] += s["correct"]
        if s["weak"]:
            d["weak"].append(t)
    for d in out.values():
        d["accuracy"] = round(d["correct"] / d["attempts"], 3) if d["attempts"] else None
    return out
