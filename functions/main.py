"""Cloud Functions (Python, 2nd gen) for the exam practice app.

grade_attempt : Firestore trigger on students/{uid}/attempts/{aid}.
   status in_progress -> submitted : grade against answerKeys/{examId}, write result, queue email in mail/.
   status graded + manualGrades changed (parent graded essays in the app) : regrade, update result, queue a
   short follow-up email when nothing is pending any more.
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


def _load(db, exam_id: str):
    exam = db.document(f"exams/{exam_id}").get().to_dict()
    keys_doc = db.document(f"answerKeys/{exam_id}").get().to_dict() or {}
    return exam, keys_doc.get("items")


def _mail(db, uid: str, aid: str, exam_id: str, subject: str, html: str, now) -> None:
    student = db.document(f"students/{uid}").get().to_dict() or {}
    to = student.get("parentEmail") or PARENT_EMAIL.value
    db.collection("mail").add({
        "to": [to],
        "message": {"subject": subject, "html": html},
        "meta": {"uid": uid, "attemptId": aid, "examId": exam_id, "createdAt": now},
    })


@firestore_fn.on_document_written(document="students/{uid}/attempts/{aid}")
def grade_attempt(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot | None]]) -> None:
    after = event.data.after
    if after is None or not after.exists:
        return
    data = after.to_dict() or {}
    before_data = (event.data.before.to_dict() or {}) if (event.data.before is not None and event.data.before.exists) else {}
    status = data.get("status")

    submitted = status == "submitted" and before_data.get("status") != "submitted"
    regrade = status == "graded" and (data.get("manualGrades") or {}) != (before_data.get("manualGrades") or {})
    if not (submitted or regrade):
        return

    uid, aid = event.params["uid"], event.params["aid"]
    exam_id = data["examId"]
    db = firestore.client()
    exam, keys = _load(db, exam_id)
    if not exam or not keys:
        after.reference.update({"status": "error", "error": f"missing exam or answer key for {exam_id}"})
        return

    result = grade_submission(data.get("answers") or {}, keys, exam, data.get("itemIds"), data.get("manualGrades"))
    now = dt.datetime.now(dt.timezone.utc)
    update = {"status": "graded", "result": result, "score": result["score"], "max": result["max"],
              "percent": result["percent"], "pendingCount": result["pendingCount"]}
    if submitted:
        update["gradedAt"] = now
    else:
        update["regradedAt"] = now
    after.reference.update(update)

    student = db.document(f"students/{uid}").get().to_dict() or {}
    name = student.get("name") or student.get("displayName") or uid[:6]
    submitted_at, started_at = data.get("submittedAt"), data.get("startedAt")
    duration = None
    if isinstance(submitted_at, dt.datetime) and isinstance(started_at, dt.datetime):
        duration = int((submitted_at - started_at).total_seconds())
    subject, html = render_report(name, exam, result, APP_URL.value, aid, submitted_at, duration,
                                  grade_filter=data.get("gradeFilter"))
    if regrade:
        if result["pendingCount"] > 0:
            return  # wait until the parent finished grading
        subject = "[採点確定] " + subject.replace("[採点結果] ", "")
    _mail(db, uid, aid, exam_id, subject, html, now)
