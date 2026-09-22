"""Cloud Functions (Python, 2nd gen) for the exam practice app.

grade_attempt : Firestore trigger. When students/{uid}/attempts/{aid}.status becomes "submitted",
                grade against answerKeys/{examId}, write result back, queue an email in mail/.
"""
from __future__ import annotations

import datetime as dt

from firebase_admin import firestore, initialize_app
from firebase_functions import firestore_fn, options, params

from grader import grade_submission
from report import render_report

initialize_app()
options.set_global_options(region="asia-northeast1", max_instances=5)

PARENT_EMAIL = params.StringParam("PARENT_EMAIL", default="hienct@fpt.com",
                                  description="Fallback recipient for result emails")
APP_URL = params.StringParam("APP_URL", default="https://REPLACE.web.app",
                             description="Public URL of the hosted web app (for image links)")


@firestore_fn.on_document_written(document="students/{uid}/attempts/{aid}")
def grade_attempt(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot | None]]) -> None:
    after = event.data.after
    if after is None or not after.exists:
        return
    data = after.to_dict() or {}
    if data.get("status") != "submitted":
        return
    before = event.data.before
    if before is not None and before.exists and (before.to_dict() or {}).get("status") == "submitted":
        return  # already being handled

    uid = event.params["uid"]
    aid = event.params["aid"]
    exam_id = data["examId"]
    db = firestore.client()

    exam = db.document(f"exams/{exam_id}").get().to_dict()
    keys_doc = db.document(f"answerKeys/{exam_id}").get().to_dict() or {}
    if not exam or not keys_doc.get("items"):
        after.reference.update({"status": "error", "error": f"missing exam or answer key for {exam_id}"})
        return

    result = grade_submission(data.get("answers") or {}, keys_doc["items"], exam, data.get("itemIds"))
    now = dt.datetime.now(dt.timezone.utc)
    after.reference.update({
        "status": "graded", "result": result, "score": result["score"], "max": result["max"],
        "percent": result["percent"], "gradedAt": now,
    })

    student = db.document(f"students/{uid}").get().to_dict() or {}
    to = student.get("parentEmail") or PARENT_EMAIL.value
    name = student.get("name") or student.get("displayName") or uid[:6]
    submitted_at = data.get("submittedAt")
    started_at = data.get("startedAt")
    duration = None
    if isinstance(submitted_at, dt.datetime) and isinstance(started_at, dt.datetime):
        duration = int((submitted_at - started_at).total_seconds())
    subject, html = render_report(name, exam, result, APP_URL.value, aid, submitted_at, duration,
                                  grade_filter=data.get("gradeFilter"))
    db.collection("mail").add({
        "to": [to],
        "message": {"subject": subject, "html": html},
        "meta": {"uid": uid, "attemptId": aid, "examId": exam_id, "createdAt": now},
    })
