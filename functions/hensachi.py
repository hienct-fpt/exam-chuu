"""推定偏差値 and 合格可能性 for the target schools, estimated from the scores the child gets in the app.

Inputs per target 入試回 (schools.json sessions.*): each subject's max + 受験者平均, the 合格最低点 (`total.line`) or
受験者数 / 合格者数 (`applicants`), and 四谷大塚's 80% / 50% 偏差値 (`yotsuya`). Pure functions (Cloud Function +
scripts/dev_server.py).

Model (ESTIMATE — the app has no score distribution of the real applicants):
  child's expected score per subject = recency-weighted % of the latest whole-exam attempts on THAT school's past
      papers of the subject (any year / 回); a subject with no paper of the school falls back to all whole exams of the
      subject (any school, 組分け) and is flagged "other".
  applicants' spread: SD = SPREAD × max per subject, subjects correlated RHO -> SD of the total.
  pass line L = 合格最低点 when published, else 受験者平均 + z·SD with z from the pass rate (合格者 / 受験者).
  exam-day noise of the child: sigma_c = DAY_NOISE × SD_total.
  合格可能性 P = Φ((T − L) / sigma_c);  偏差値 Y = y50 + s·(T − L) / sigma_c  with s = (y80 − y50) / z(0.8),
      i.e. the score at the pass line reads as the 50% 偏差値 and P(Y) follows the 四谷 80% / 50% lines.
Trend: the same estimate at the end of each past week with data -> slope per month (least squares, last 12 points)
and the month the 80% line is reached at that pace.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from statistics import NormalDist

SPREAD = 0.18      # applicants' SD per subject as a share of its max (typical 中学入試 subject test)
RHO = 0.6          # correlation between subjects
DAY_NOISE = 0.5    # child's exam-day variation, share of the applicants' total SD
RECENT = 3         # latest whole exams per subject, weights 3:2:1
Z80 = NormalDist().inv_cdf(0.8)
POPULATION_FILE = Path(__file__).resolve().parent / "kumiwake_population.json"
KUMIWAKE_POP = json.loads(POPULATION_FILE.read_text(encoding="utf-8")) if POPULATION_FILE.exists() else {}
_N = NormalDist()


def _t(v) -> dt.datetime:
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    s = str(v or "1970-01-01")
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if "T" in s else dt.datetime.fromisoformat(s + "T00:00:00+00:00")
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def whole_results(attempts: list[dict], exam_meta: dict[str, dict]) -> list[dict]:
    """Graded whole-exam attempts (本番 or 小N filtered over all its items): [{t, school, subject, p}] oldest first."""
    out = []
    for a in attempts:
        meta = exam_meta.get(a.get("examId") or "")
        if not meta or a.get("status") != "graded" or a.get("percent") is None or a.get("items") or a.get("redoOf"):
            continue
        out.append({"t": _t(a.get("submittedAt") or a.get("gradedAt")), "school": meta.get("school"),
                    "subject": meta.get("subject"), "p": a["percent"] / 100})
    return sorted(out, key=lambda r: r["t"])


def _recent_mean(rows: list[dict]) -> float | None:
    last = rows[-RECENT:][::-1]
    if not last:
        return None
    w = [RECENT - i for i in range(len(last))]
    return sum(r["p"] * wi for r, wi in zip(last, w)) / sum(w)


def subject_levels(results: list[dict], school: str, subjects, cutoff: dt.datetime) -> dict[str, tuple[float, str]]:
    """{subject: (p, "school" | "other")} from results up to cutoff."""
    out = {}
    for s in subjects:
        upto = [r for r in results if r["t"] <= cutoff and r["subject"] == s]
        own = [r for r in upto if r["school"] == school]
        if own:
            out[s] = (_recent_mean(own), "school")
        elif upto:
            out[s] = (_recent_mean(upto), "other")
    return out


def session_model(sess: dict) -> dict | None:
    """Per 入試回: max / avg per subject, SD of the total, pass line, 四谷 lines. None without the needed data."""
    subs = {k: v for k, v in (sess.get("subjects") or {}).items() if v.get("max") and v.get("examinee_avg") is not None}
    yt = sess.get("yotsuya") or {}
    if not subs or yt.get("y80") is None or yt.get("y50") is None:
        return None
    sds = [SPREAD * v["max"] for v in subs.values()]
    var = sum(s * s for s in sds) + 2 * RHO * sum(sds[i] * sds[j] for i in range(len(sds)) for j in range(i + 1, len(sds)))
    sd_total = math.sqrt(var)
    total = sess.get("total") or {}
    avg_total = total.get("examinee_avg") if len(subs) > 1 else next(iter(subs.values()))["examinee_avg"]
    if avg_total is None:
        avg_total = sum(v["examinee_avg"] for v in subs.values())
    if total.get("line") is not None:
        line, basis = float(total["line"]), "合格最低点"
    else:
        ap = sess.get("applicants") or {}
        if not ap.get("examinees") or not ap.get("passed"):
            return None
        rate = min(0.99, max(0.01, ap["passed"] / ap["examinees"]))
        line, basis = avg_total + _N.inv_cdf(1 - rate) * sd_total, f"合格率 {round(rate * 100)}% から推定"
    return {"subjects": subs, "sd_total": sd_total, "line": line, "line_basis": basis,
            "max_total": sum(v["max"] for v in subs.values()), "y80": yt["y80"], "y50": yt["y50"]}


def estimate(model: dict, levels: dict[str, tuple[float, str]]) -> dict | None:
    """T, 偏差値, 合格可能性 from subject levels; None unless every subject of the 回 has a level."""
    if any(s not in levels for s in model["subjects"]):
        return None
    score = sum(levels[s][0] * v["max"] for s, v in model["subjects"].items())
    sigma_c = DAY_NOISE * model["sd_total"]
    z = (score - model["line"]) / sigma_c
    slope = (model["y80"] - model["y50"]) / Z80
    return {"score": round(score, 1), "line": round(model["line"], 1), "y": round(model["y50"] + slope * z, 1),
            "prob": round(_N.cdf(z), 3)}


def _slope_per_month(points: list[tuple[dt.datetime, float]]) -> float | None:
    pts = points[-12:]
    if len(pts) < 3 or (pts[-1][0] - pts[0][0]).days < 14:
        return None
    xs = [(t - pts[0][0]).days / 30.4 for t, _ in pts]
    ys = [y for _, y in pts]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den, 2) if den else None


def hensachi_report(attempts: list[dict], exam_meta: dict[str, dict], schools: dict, plan: dict,
                    now: dt.datetime) -> dict:
    """summary["hensachi"]: per target 入試回 (第一志望 first) the current estimate, weekly series, trend, 80% reach."""
    results = whole_results(attempts, exam_meta)
    sessions = []
    for school in [plan.get("first"), plan.get("second")]:
        sc = schools.get(school) or {}
        for key, sess in (sc.get("sessions") or {}).items():
            if sess.get("goal") is False:
                continue
            model = session_model(sess)
            if not model:
                continue
            lv = subject_levels(results, school, model["subjects"], now)
            cur = estimate(model, lv)
            # weekly series: end of each week (Sun, JST-ish) that had a new result, up to now
            series = []
            if results:
                week = results[0]["t"].date() - dt.timedelta(days=results[0]["t"].weekday())
                while dt.datetime.combine(week, dt.time(), dt.timezone.utc) <= now:
                    end = dt.datetime.combine(week + dt.timedelta(days=7), dt.time(), dt.timezone.utc)
                    if any(week <= r["t"].date() < week + dt.timedelta(days=7) for r in results):
                        e = estimate(model, subject_levels(results, school, model["subjects"], min(end, now)))
                        if e:
                            series.append({"week": week.isoformat(), "y": e["y"], "prob": e["prob"]})
                    week += dt.timedelta(days=7)
            slope = _slope_per_month([(_t(p["week"]), p["y"]) for p in series])
            reach = None
            if cur and slope and slope > 0 and cur["y"] < model["y80"]:
                months = (model["y80"] - cur["y"]) / slope
                reach = (now + dt.timedelta(days=30.4 * months)).date().isoformat()[:7]
            sessions.append({
                "school": school, "schoolName": sc.get("name", school), "session": key, "label": sess.get("label", key),
                "y80": model["y80"], "y50": model["y50"], "lineBasis": model["line_basis"],
                "estimate": cur, "series": series, "trendPerMonth": slope, "reach80": reach,
                "coverage": {s: (lv[s][1] if s in lv else None) for s in model["subjects"]},
                "first": school == plan.get("first"),
                # for the 偏差値シミュレーター (web/src/simulator.js recomputes estimate() with added points)
                "model": {"max": {s: v["max"] for s, v in model["subjects"].items()}, "line": round(model["line"], 2),
                          "sigmaC": round(DAY_NOISE * model["sd_total"], 3)},
                "levels": {s: round(lv[s][0], 4) for s in lv},
            })
    return {"sessions": sessions,
            "assumptions": {"spread": SPREAD, "rho": RHO, "dayNoise": DAY_NOISE, "recent": RECENT},
            "source": (schools.get(plan.get("first")) or {}).get("_yotsuya_source")}


# ---------------------------------------------------------------- 組分けテスト
# kumiwake_population.json (pipeline/seitouritsu.py): all test-takers' average score per round and subject
# (Σ 配点 × 正答率 of the 正答率一覧). 偏差値 = 50 + 10 · (score − mean) / SD with the same assumed SD (SPREAD × max).
# The 組分け population (四谷大塚 students) is not the 合不合 one behind the schools' 80% / 50% lines: shown apart.
def kumiwake_report(attempts: list[dict], exam_meta: dict[str, dict], population: dict) -> dict:
    """{"rounds": [{round, year, subjects: {s: {y, pct, meanPct}}, total}], "trend": {s | "total": per round}}.
    The FIRST graded whole attempt of each 組分け exam counts (closest to the real test; later ones are review)."""
    first: dict[str, dict] = {}
    for a in sorted(attempts, key=lambda a: str(a.get("submittedAt") or a.get("gradedAt") or "")):
        eid = a.get("examId") or ""
        meta = exam_meta.get(eid)
        if (not meta or meta.get("school") != "kumiwake" or a.get("status") != "graded" or a.get("percent") is None
                or a.get("items") or a.get("redoOf") or eid in first or eid not in population):
            continue
        first[eid] = a
    rounds: dict[tuple[str, int], dict] = {}
    for eid, a in first.items():
        parts = eid.split("_")          # kumiwake_2026_r1_math
        key = (parts[1], int(parts[2][1:]))
        pop = population[eid]
        sd = SPREAD * pop["max"]
        score = a["percent"] / 100 * pop["max"]
        r = rounds.setdefault(key, {"year": key[0], "round": key[1], "subjects": {}, "_raw": {}})
        r["subjects"][parts[3]] = {"y": round(50 + 10 * (score - pop["mean"]) / sd, 1), "pct": a["percent"],
                                   "meanPct": round(100 * pop["mean"] / pop["max"]),
                                   "max": pop["max"], "sd": round(sd, 2), "examId": eid}
        r["_raw"][parts[3]] = (score, pop["mean"], sd)
    out = []
    for key in sorted(rounds):
        r = rounds[key]
        raw = r.pop("_raw")
        r["total"] = None
        if len(raw) == 4:                # 4科: sum of scores against the sum of means, correlated SD
            sds = [v[2] for v in raw.values()]
            sd_t = math.sqrt(sum(s * s for s in sds) + 2 * RHO * sum(sds[i] * sds[j] for i in range(4) for j in range(i + 1, 4)))
            r["total"] = round(50 + 10 * (sum(v[0] for v in raw.values()) - sum(v[1] for v in raw.values())) / sd_t, 1)
            r["sdTotal"] = round(sd_t, 2)
        out.append(r)
    trend = {}
    for k in ["total", "math", "japanese", "science", "social"]:
        pts = [(i, (r["total"] if k == "total" else (r["subjects"].get(k) or {}).get("y"))) for i, r in enumerate(out)]
        pts = [(i, y) for i, y in pts if y is not None]
        if len(pts) >= 2:
            mx = sum(i for i, _ in pts) / len(pts)
            my = sum(y for _, y in pts) / len(pts)
            den = sum((i - mx) ** 2 for i, _ in pts)
            trend[k] = round(sum((i - mx) * (y - my) for i, y in pts) / den, 2) if den else None
    return {"rounds": out, "trend": trend}
