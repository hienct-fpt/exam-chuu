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
                  submitted_at: datetime | None = None, duration_sec: int | None = None) -> tuple[str, str]:
    """Return (subject, html)."""
    title = f"{exam.get('school_name', '')} {exam.get('year', '')}年度 {exam.get('session_label', '')} {exam.get('subject_label', '')}"
    subject = f"[採点結果] {student_name} – {title} {result['score']}/{result['max']} ({result['percent']}%)"
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
<h2 style="margin-bottom:4px">{esc(title)}</h2>
<div style="color:#666">{esc(student_name)} · {esc(when)} {('· 所要 ' + esc(dur)) if dur else ''}</div>
<p style="font-size:28px;margin:16px 0"><b>{result['score']} / {result['max']}</b> 点 ({result['percent']}%) ·
正解 {result['correctCount']} / {result['itemCount']} 問 · 未回答 {result['itemCount'] - result['answeredCount']} 問</p>
<h3>大問別</h3>
<table style="border-collapse:collapse">{big_rows}</table>
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
