"""Email report rendering (HTML). Pure, unit-testable."""
from __future__ import annotations

import html
from datetime import datetime


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, (list, tuple)):
        return " / ".join(str(x) if str(x).strip() else "—" for x in v)
    return str(v) if str(v).strip() else "—"


def render_report(student_name: str, exam: dict, result: dict, app_url: str, attempt_id: str,
                  submitted_at: datetime | None = None, duration_sec: int | None = None,
                  grade_filter: int | str | None = None) -> tuple[str, str]:
    """Return (subject, html)."""
    title = f"{exam.get('school_name', '')} {exam.get('year', '')}年度 {exam.get('session_label', '')} {exam.get('subject_label', '')}"
    scope = f" [小{grade_filter}まで]" if grade_filter else ""
    subject = f"[採点結果] {student_name} – {title}{scope} {result['score']}/{result['max']} ({result['percent']}%)"
    esc = html.escape
    app_url = app_url.rstrip("/")
    when = submitted_at.strftime("%Y-%m-%d %H:%M") if submitted_at else ""
    dur = f"{duration_sec // 60}分{duration_sec % 60}秒" if duration_sec is not None else ""

    big_rows = "".join(
        f"<tr><td style='padding:4px 10px;border:1px solid #ddd'>大問 {b['big']}</td>"
        f"<td style='padding:4px 10px;border:1px solid #ddd;text-align:right'>{b['correct']} / {b['items']}</td>"
        f"<td style='padding:4px 10px;border:1px solid #ddd;text-align:right'>{round(100 * b['correct'] / b['items']) if b['items'] else 0}%</td></tr>"
        for b in sorted(result["perBig"].values(), key=lambda x: x["big"])
    )

    def item_row(sid: str, it: dict) -> str:
        mark = "○" if it["correct"] else ("×" if it["answered"] else "－")
        color = "#2e7d32" if it["correct"] else ("#c62828" if it["answered"] else "#999")
        exp = _fmt(it["expected"])
        if it.get("variants"):
            exp += " (" + ", ".join(map(str, it["variants"])) + ")"
        parts = f" [{' / '.join(it['parts'])}]" if it.get("parts") else ""
        return (f"<tr><td style='padding:4px 8px;border:1px solid #ddd;color:{color};font-weight:bold'>{mark}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd'>大問{it['big']} {esc(it.get('label') or '')}{esc(parts)}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd'>{esc(_fmt(it['student']))} {esc(it.get('unit') or '')}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd'>{esc(exp)}</td></tr>")

    topic_rows = "".join(
        f"<tr><td style='padding:4px 10px;border:1px solid #ddd'>{esc(t)}</td>"
        f"<td style='padding:4px 10px;border:1px solid #ddd;text-align:right'>{v['correct']} / {v['items']}</td>"
        f"<td style='padding:4px 10px;border:1px solid #ddd;text-align:right'>{round(100 * v['correct'] / v['items']) if v['items'] else 0}%</td></tr>"
        for t, v in sorted(result.get("perTopic", {}).items(), key=lambda kv: (kv[1]['correct'] / max(kv[1]['items'], 1), kv[0]))
    )
    items_sorted = sorted(result["perItem"].items(), key=lambda kv: (kv[1]["big"], kv[1]["sub"]))
    item_rows = "".join(item_row(sid, it) for sid, it in items_sorted)
    wrong = [(sid, it) for sid, it in items_sorted if not it["correct"]]
    wrong_imgs = "".join(
        f"<div style='margin:12px 0'><div style='font-weight:bold'>大問{it['big']} {esc(it.get('label') or '')} — "
        f"回答: {esc(_fmt(it['student']))} / 正答: {esc(_fmt(it['expected']))}</div>"
        f"<img src='{app_url}/{it['image']}' style='max-width:640px;width:100%;border:1px solid #ccc'></div>"
        for sid, it in wrong if it.get("image")
    )
    link = f"{app_url}/#/result/{attempt_id}"
    body = f"""<!doctype html><html><body style="font-family:sans-serif;color:#222;max-width:720px">
<h2 style="margin-bottom:4px">{esc(title)}{esc(scope)}</h2>
<div style="color:#666">{esc(student_name)} · {esc(when)} {('· 所要 ' + esc(dur)) if dur else ''}</div>
<p style="font-size:28px;margin:16px 0"><b>{result['score']} / {result['max']}</b> 点 ({result['percent']}%) ·
正解 {result['correctCount']} / {result['itemCount']} 問 · 未回答 {result['itemCount'] - result['answeredCount']} 問</p>
<h3>大問別</h3>
<table style="border-collapse:collapse">{big_rows}</table>
<h3>分野別（正答率の低い順）</h3>
<table style="border-collapse:collapse">{topic_rows}</table>
<h3>全問</h3>
<table style="border-collapse:collapse;font-size:14px">
<tr><th style="border:1px solid #ddd;padding:4px 8px"></th><th style="border:1px solid #ddd;padding:4px 8px">問</th>
<th style="border:1px solid #ddd;padding:4px 8px">回答</th><th style="border:1px solid #ddd;padding:4px 8px">正答</th></tr>
{item_rows}</table>
<h3>間違えた問題 ({len(wrong)})</h3>
{wrong_imgs or '<p>なし 🎉</p>'}
<p><a href="{link}">アプリで結果を見る</a></p>
</body></html>"""
    return subject, body


def render_digest(student_name: str, summary: dict, suggestions: dict, app_url: str) -> tuple[str, str]:
    """Weekly digest: per-subject accuracy, topic table (weakest first), weekly trend, suggested practice."""
    esc = html.escape
    app_url = app_url.rstrip("/")
    SUBJ = {"math": "算数", "japanese": "国語", "science": "理科", "social": "社会"}
    weekly = summary.get("weekly") or []
    this_week = weekly[-1] if weekly else {"attempts": 0, "correct": 0}
    subject = f"[週報] {student_name} – 今週 {this_week['attempts']}問 正解{this_week['correct']} · 弱点 " + \
              "、".join(t for s in suggestions.values() for t in s["topics"][:1]) if suggestions else f"[週報] {student_name} – 今週 {this_week['attempts']}問"
    trend = "".join(
        f"<tr><td style='padding:3px 8px;border:1px solid #ddd'>{w['weekStart']}〜</td>"
        f"<td style='padding:3px 8px;border:1px solid #ddd;text-align:right'>{w['attempts']}</td>"
        f"<td style='padding:3px 8px;border:1px solid #ddd;text-align:right'>{('%d%%' % round(100 * w['accuracy'])) if w['accuracy'] is not None else '—'}</td></tr>"
        for w in weekly)
    sections = []
    for subj, d in sorted(summary.get("subjects", {}).items()):
        rows = [(t, s) for t, s in summary["topics"].items() if s["subject"] == subj]
        rows.sort(key=lambda ts: (ts[1]["mastery"] if ts[1]["mastery"] is not None else 2))
        trs = "".join(
            f"<tr style='{'background:#fef2f2' if s['weak'] else ''}'><td style='padding:3px 8px;border:1px solid #ddd'>{esc(t)}</td>"
            f"<td style='padding:3px 8px;border:1px solid #ddd;text-align:right'>{s['correct']} / {s['attempts']}</td>"
            f"<td style='padding:3px 8px;border:1px solid #ddd;text-align:right'>{('%d%%' % round(100 * s['mastery'])) if s['mastery'] is not None else '—'}"
            f"{'' if s['confident'] else ' <small>(少)</small>'}</td></tr>" for t, s in rows)
        sug = suggestions.get(subj)
        sug_html = (f"<p>おすすめ練習: <b>{esc('、'.join(sug['topics']))}</b> ({sug['count']}問) "
                    f"<a href='{app_url}/#/practice/{subj}?weak=1'>開く</a></p>") if sug else "<p>弱点なし 🎉</p>"
        acc = d.get("accuracy")
        sections.append(f"<h3>{SUBJ.get(subj, subj)} · 正答率 {('%d%%' % round(100 * acc)) if acc is not None else '—'} ({d['attempts']}問)</h3>"
                        f"<table style='border-collapse:collapse;font-size:14px'><tr><th style='border:1px solid #ddd;padding:3px 8px'>分野</th>"
                        f"<th style='border:1px solid #ddd;padding:3px 8px'>正解</th><th style='border:1px solid #ddd;padding:3px 8px'>習熟度</th></tr>{trs}</table>{sug_html}")
    body = f"""<!doctype html><html><body style="font-family:sans-serif;color:#222;max-width:720px">
<h2>週間レポート — {esc(student_name)}</h2>
<p>今週: {this_week['attempts']} 問 / 正解 {this_week['correct']}。累計 {summary.get('attemptCount', 0)} 回受験。</p>
<h3>週ごとの推移</h3><table style="border-collapse:collapse;font-size:14px">{trend}</table>
{''.join(sections)}
<p><a href="{app_url}/#/dashboard">ダッシュボードを見る</a></p>
</body></html>"""
    return subject, body
