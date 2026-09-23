"""Cloud Functions (Python, 2nd gen) for the exam practice app.

grade_attempt : Firestore trigger on students/{uid}/attempts/{aid}.
   in_progress -> submitted : grade (exam attempt against answerKeys/{examId}, or a cross-exam practice set
                              against several keys), write result, refresh students/{uid}/topicStats, mail the parent.
   graded + manualGrades changed : regrade; mail a 採点確定 report when nothing is pending any more.
weekly_digest : scheduled (Sunday 20:00 JST) — per student topic mastery table, weak topics, suggested practice.
"""
from __future__ import annotations

import datetime as dt

from firebase_admin import firestore, initialize_app
from firebase_functions import firestore_fn, options, params, scheduler_fn

from analytics import outcomes, topic_stats, weak_topics, weekly_series, subject_summary, item_history, practice_set
from grader import grade_submission, virtual_exam
from report import render_report, render_digest

initialize_app()
options.set_global_options(region="asia-northeast1", max_instances=5)

PARENT_EMAIL = params.StringParam("PARENT_EMAIL", default="parent@example.com",  # real value: functions/.env (git-ignored)
                                  description="Fallback recipient for result emails")
APP_URL = params.StringParam("APP_URL", default="https://REPLACE.web.app",
                             description="Public URL of the hosted web app (for image links)")


def _keys(db, exam_id: str) -> dict:
    return (db.document(f"answerKeys/{exam_id}").get().to_dict() or {}).get("items") or {}


def _mail(db, uid: str, exam_id: str | None, subject: str, html: str, now, kind: str, aid: str | None = None) -> None:
    student = db.document(f"students/{uid}").get().to_dict() or {}
    to = student.get("parentEmail") or PARENT_EMAIL.value
    db.collection("mail").add({
        "to": [to],
        "message": {"subject": subject, "html": html},
        "meta": {"uid": uid, "attemptId": aid, "examId": exam_id, "kind": kind, "createdAt": now},
    })


def _student_name(db, uid: str) -> str:
    student = db.document(f"students/{uid}").get().to_dict() or {}
    return student.get("name") or student.get("displayName") or uid[:6]


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


def _grade(db, data: dict) -> tuple[dict, dict]:
    """Returns (result, exam_meta_for_report)."""
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
        result = grade_submission(data.get("answers") or {}, keys, exam, ids, data.get("manualGrades"), full_ids=True)
        meta = {"school_name": "", "year": "", "session_label": "弱点練習" if data.get("topics") else "練習",
                "subject_label": "・".join(sorted({b.get("subject_label", "") for b in banks.values()})),
                "items": exam["items"]}
        return result, meta
    exam_id = data["examId"]
    exam = db.document(f"exams/{exam_id}").get().to_dict()
    keys = _keys(db, exam_id)
    if not exam or not keys:
        raise ValueError(f"missing exam or answer key for {exam_id}")
    result = grade_submission(data.get("answers") or {}, keys, exam, data.get("itemIds"), data.get("manualGrades"))
    return result, exam


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
        result, exam = _grade(db, data)
    except ValueError as e:
        after.reference.update({"status": "error", "error": str(e)})
        return
    now = dt.datetime.now(dt.timezone.utc)
    update = {"status": "graded", "result": result, "score": result["score"], "max": result["max"],
              "percent": result["percent"], "pendingCount": result["pendingCount"],
              ("gradedAt" if submitted else "regradedAt"): now}
    after.reference.update(update)
    refresh_topic_stats(db, uid)

    name = _student_name(db, uid)
    submitted_at, started_at = data.get("submittedAt"), data.get("startedAt")
    duration = None
    if isinstance(submitted_at, dt.datetime) and isinstance(started_at, dt.datetime):
        duration = int((submitted_at - started_at).total_seconds())
    subject, html = render_report(name, exam, result, APP_URL.value, aid, submitted_at, duration,
                                  grade_filter=data.get("gradeFilter"))
    if regrade:
        if result["pendingCount"] > 0:
            return
        subject = "[採点確定] " + subject.replace("[採点結果] ", "")
    _mail(db, uid, data.get("examId"), subject, html, now, "result", aid)


@scheduler_fn.on_schedule(schedule="every sunday 20:00", timezone=scheduler_fn.Timezone("Asia/Tokyo"))
def weekly_digest(event: scheduler_fn.ScheduledEvent) -> None:
    db = firestore.client()
    banks = {d.id: d.to_dict() for d in db.collection("exams").stream()}
    bank_items = [{**it, "subject": b.get("subject")} for b in banks.values() for it in b.get("items", [])]
    now = dt.datetime.now(dt.timezone.utc)
    for sdoc in db.collection("students").stream():
        uid = sdoc.id
        summary = refresh_topic_stats(db, uid)
        if not summary["attemptCount"]:
            continue
        hist = {k: {**v, "t": dt.datetime.fromisoformat(v["t"])} for k, v in summary["itemHistory"].items()}
        suggestions = {}
        for subj in summary["subjects"]:
            weak = [t for t, _ in weak_topics(summary["topics"], subj, k=3)]
            if weak:
                picked = practice_set(bank_items, set(weak), hist, n=10, subject=subj)
                suggestions[subj] = {"topics": weak, "count": len(picked)}
        subject, html = render_digest(_student_name(db, uid), summary, suggestions, APP_URL.value)
        _mail(db, uid, None, subject, html, now, "digest")
