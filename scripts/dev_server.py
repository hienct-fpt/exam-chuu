"""Local stand-in for the Cloud Function so the SPA can be tested without Firebase.

POST /api/grade   {examId, answers, itemIds?, gradeFilter?, manualGrades?, studentName?, attemptId?}
                  -> {result, emailSubject, emailHtml}
GET  /api/health

usage: python scripts/dev_server.py [port=8790]     (Vite proxies /api here when VITE_MOCK=1)
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))
from grader import grade_submission  # noqa: E402
from report import render_report  # noqa: E402

OUT = ROOT / "pipeline" / "out"
ALL_KEYS = json.loads((OUT / "answers_all.json").read_text(encoding="utf-8"))


def keys_for(exam_id: str) -> dict:
    return {iid.split("#", 1)[1]: k for iid, k in ALL_KEYS.items() if iid.startswith(exam_id + "#")}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive, needed for the Vite proxy agent

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/health"):
            n = len(json.loads((OUT / "bank" / "index.json").read_text(encoding="utf-8")))
            return self._json(200, {"ok": True, "exams": n})
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/api/grade"):
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n) or b"{}")
        exam_id = req["examId"]
        exam = json.loads((OUT / "bank" / f"{exam_id}.json").read_text(encoding="utf-8"))
        result = grade_submission(req.get("answers") or {}, keys_for(exam_id), exam,
                                  req.get("itemIds"), req.get("manualGrades"))
        subject, html = render_report(req.get("studentName") or "テスト", exam, result,
                                      "http://localhost:5173", req.get("attemptId") or "local",
                                      grade_filter=req.get("gradeFilter"))
        self._json(200, {"result": result, "emailSubject": subject, "emailHtml": html})

    def log_message(self, fmt, *args) -> None:
        sys.stderr.write("[dev_server] " + fmt % args + "\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
    print(f"[dev_server] http://localhost:{port}/api/health")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
