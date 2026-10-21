"""functions/hensachi.py: 推定偏差値 / 合格可能性 from in-app scores against the 四谷大塚 80% / 50% lines."""
import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))

from hensachi import Z80, estimate, hensachi_report, session_model  # noqa: E402
from goals import CONFIG  # noqa: E402

SCHOOLS = CONFIG["schools"]
PLAN = {"first": "kyoritsu", "second": "shinagawa"}
META = {f"k{y}_{s}": {"school": "kyoritsu", "subject": s} for y in (2024, 2025, 2026) for s in ("math", "japanese", "science", "social")}
META.update({f"s_{s}": {"school": "shinagawa", "subject": s} for s in ("math", "japanese", "science", "social")})
META["kumi_math"] = {"school": "kumiwake", "subject": "math"}


def att(eid, pct, day):
    return {"examId": eid, "status": "graded", "percent": pct, "submittedAt": f"2026-{day}T10:00:00Z", "mode": "exam"}


def test_pass_line_from_pass_rate_or_published_minimum():
    k = session_model(SCHOOLS["kyoritsu"]["sessions"]["2-1"])
    assert k["line_basis"].startswith("合格率 45%")
    assert k["sd_total"] == pytest.approx(45.5, abs=0.1)          # 18/18/9/9 with rho 0.6
    assert k["line"] == pytest.approx(170.0 + 0.135 * 45.5, abs=0.3)
    s = session_model(SCHOOLS["shinagawa"]["sessions"]["r1"])
    assert s["line"] == 192 and s["line_basis"] == "合格最低点"
    assert session_model(SCHOOLS["kyoritsu"]["sessions"]["2-3e"]) is None   # no 四谷 line for that 回


def test_score_at_the_line_reads_as_the_50_percent_hensachi():
    m = session_model(SCHOOLS["kyoritsu"]["sessions"]["2-1"])
    total_max = m["max_total"]
    at_line = {s: (m["line"] / total_max, "school") for s in m["subjects"]}
    e = estimate(m, at_line)
    assert e["y"] == pytest.approx(46, abs=0.05) and e["prob"] == pytest.approx(0.5, abs=0.005)
    up = (m["line"] + Z80 * 0.5 * m["sd_total"]) / total_max
    e80 = estimate(m, {s: (up, "school") for s in m["subjects"]})
    assert e80["y"] == pytest.approx(50, abs=0.05) and e80["prob"] == pytest.approx(0.8, abs=0.005)
    assert estimate(m, {"math": (0.9, "school")}) is None            # every subject of the 回 is needed


def test_report_uses_own_school_papers_first_and_tracks_the_trend():
    now = dt.datetime(2026, 10, 22, tzinfo=dt.timezone.utc)
    attempts = []
    for i, (day, pct) in enumerate([("09-01", 45), ("09-15", 50), ("09-29", 55), ("10-13", 62)]):
        y = 2024 + min(i, 2)
        attempts += [att(f"k{y}_{s}", pct, day) for s in ("math", "japanese", "science", "social")]
    attempts.append(att("kumi_math", 99, "10-14"))                     # other source: ignored while own papers exist
    rep = hensachi_report(attempts, META, SCHOOLS, PLAN, now)
    k21 = next(s for s in rep["sessions"] if s["school"] == "kyoritsu" and s["session"] == "2-1")
    assert k21["first"] and k21["coverage"] == {"japanese": "school", "math": "school", "social": "school", "science": "school"}
    assert len(k21["series"]) == 4 and k21["trendPerMonth"] > 0
    assert k21["estimate"]["y"] == k21["series"][-1]["y"]
    shin = next(s for s in rep["sessions"] if s["school"] == "shinagawa" and s["session"] == "r1")
    assert set(shin["coverage"].values()) == {"other"}                  # no 品川 paper yet -> other results, flagged
    assert rep["assumptions"]["spread"] == 0.18
    assert hensachi_report([], META, SCHOOLS, PLAN, now)["sessions"][0]["estimate"] is None
