"""Cloud Functions (Python, 2nd gen) for the exam practice app.

grade_attempt : Firestore trigger on students/{uid}/attempts/{aid}.
   in_progress -> submitted : grade (exam attempt against answerKeys/{examId}, or a cross-exam practice set
                              against several keys), write result, refresh students/{uid}/topicStats.
   graded + manualGrades changed : regrade.
"""
from __future__ import annotations

import datetime as dt

from firebase_admin import firestore, initialize_app
from firebase_functions import firestore_fn, options

from analytics import outcomes, topic_stats, weekly_series, subject_summary, item_history
from grader import grade_submission, virtual_exam

initialize_app()
options.set_global_options(region="asia-northeast1", max_instances=5)


def _keys(db, exam_id: str) -> dict:
    return (db.document(f"answerKeys/{exam_id}").get().to_dict() or {}).get("items") or {}


def _graded_attempts(db, uid: str) -> list[dict]:
    docs = db.collection(f"students/{uid}/attempts").where("status", "==", "graded").stream()
    return [{**d.to_dict(), "id": d.id} for d in docs]


def refresh_topic_stats(db, uid: str) -> dict:
    """Recompute from all graded attempts (a few hundred at most) -> students/{uid}/topicStats/summary."""
    attempts = _graded_attempts(db, uid)
    exams = {d.id: d.to_dict() for d in db.collection("exams").select(["subject"]).stream()}
    subject_of = {eid: e.get("subject") for eid, e in exams.items()}
    outs = outcomes(attempts, subject_of)
    stats = topic_stats(outs)
    doc = {
        "topics": stats,
        "subjects": subject_summary(stats),
        "weekly": weekly_series(outs),
        "itemHistory": {k: {"tries": v["tries"], "correct": v["correct"], "t": v["t"].isoformat()}
                        for k, v in item_history(outs).items()},
        "updatedAt": dt.datetime.now(dt.timezone.utc),
        "attemptCount": len(attempts),
    }
    db.document(f"students/{uid}/topicStats/summary").set(doc)
    return doc


def _grade(db, data: dict) -> dict:
    if data.get("mode") == "practice" and data.get("items"):
        ids = list(data["items"])
        exam_ids = sorted({i.split("#", 1)[0] for i in ids})
        banks = {eid: db.document(f"exams/{eid}").get().to_dict() for eid in exam_ids}
        banks = {k: v for k, v in banks.items() if v}
        keys = {}
        for eid in banks:
            for sid, k in _keys(db, eid).items():
                keys[f"{eid}#{sid}"] = k
        exam, _ = virtual_exam(banks, ids)
        return grade_submission(data.get("answers") or {}, keys, exam, ids, data.get("manualGrades"), full_ids=True)
    exam_id = data["examId"]
    exam = db.document(f"exams/{exam_id}").get().to_dict()
    keys = _keys(db, exam_id)
    if not exam or not keys:
        raise ValueError(f"missing exam or answer key for {exam_id}")
    return grade_submission(data.get("answers") or {}, keys, exam, data.get("itemIds"), data.get("manualGrades"))


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
    db = firestore.client()
    try:
        result = _grade(db, data)
    except ValueError as e:
        after.reference.update({"status": "error", "error": str(e)})
        return
    now = dt.datetime.now(dt.timezone.utc)
    update = {"status": "graded", "result": result, "score": result["score"], "max": result["max"],
              "percent": result["percent"], "pendingCount": result["pendingCount"],
              ("gradedAt" if submitted else "regradedAt"): now}
    after.reference.update(update)
    refresh_topic_stats(db, uid)
