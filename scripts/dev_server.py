"""Local stand-in for the Cloud Functions so the SPA can be tested without Firebase.

POST /api/grade   exam:     {examId, answers, itemIds?, gradeFilter?, manualGrades?, studentName?, attemptId?}
                  practice: {mode:"practice", items:[full item ids], answers, manualGrades?, topics?, ...}
                  -> {result}
POST /api/stats   {attempts:[graded attempts]} -> topicStats summary (same shape as students/{uid}/topicStats/summary)
                  + suggestions per subject
GET  /api/health

usage: python scripts/dev_server.py [port=8790]     (Vite proxies /api here when VITE_MOCK=1)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))
from analytics import outcomes, topic_stats, weak_topics, weekly_series, subject_summary, item_history, practice_set  # noqa: E402
from grader import grade_submission, virtual_exam  # noqa: E402

OUT = ROOT / "pipeline" / "out"
ALL_KEYS = json.loads((OUT / "answers_all.json").read_text(encoding="utf-8"))
INDEX = json.loads((OUT / "bank" / "index.json").read_text(encoding="utf-8"))
BANKS = {e["id"]: json.loads((OUT / "bank" / f"{e['id']}.json").read_text(encoding="utf-8")) for e in INDEX}
SUBJECT_OF = {e["id"]: e["subject"] for e in INDEX}
BANK_ITEMS = [{**it, "subject": b["subject"]} for b in BANKS.values() for it in b["items"]]


def keys_for(exam_id: str) -> dict:
    return {iid.split("#", 1)[1]: k for iid, k in ALL_KEYS.items() if iid.startswith(exam_id + "#")}


def grade(req: dict) -> dict:
    if req.get("mode") == "practice" and req.get("items"):
        ids = list(req["items"])
        exam, _ = virtual_exam(BANKS, ids)
        keys = {i: ALL_KEYS[i] for i in ids if i in ALL_KEYS}
        result = grade_submission(req.get("answers") or {}, keys, exam, ids, req.get("manualGrades"), full_ids=True)
    else:
        exam_id = req["examId"]
        exam = BANKS[exam_id]
        result = grade_submission(req.get("answers") or {}, keys_for(exam_id), exam,
                                  req.get("itemIds"), req.get("manualGrades"))
    return {"result": result}


def stats(req: dict) -> dict:
    outs = outcomes(req.get("attempts") or [], SUBJECT_OF)
    st = topic_stats(outs)
    hist = item_history(outs)
    summary = {
        "topics": st, "subjects": subject_summary(st), "weekly": weekly_series(outs),
        "itemHistory": {k: {"tries": v["tries"], "correct": v["correct"], "t": v["t"].isoformat()} for k, v in hist.items()},
        "attemptCount": len(req.get("attempts") or []),
    }
    suggestions = {}
    for subj in summary["subjects"]:
        weak = [t for t, _ in weak_topics(st, subj, k=3)]
        if weak:
            picked = practice_set(BANK_ITEMS, set(weak), hist, n=10, subject=subj)
            suggestions[subj] = {"topics": weak, "count": len(picked), "items": [p["id"] for p in picked]}
    summary["suggestions"] = suggestions
    return summary


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/health"):
            return self._json(200, {"ok": True, "exams": len(INDEX), "items": len(BANK_ITEMS)})
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n) or b"{}")
        try:
            if self.path.startswith("/api/grade"):
                return self._json(200, grade(req))
            if self.path.startswith("/api/stats"):
                return self._json(200, stats(req))
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"error": repr(e)})
        self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args) -> None:
        sys.stderr.write("[dev_server] " + fmt % args + "\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
    print(f"[dev_server] http://localhost:{port}/api/health  ({len(INDEX)} exams, {len(BANK_ITEMS)} items)")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
