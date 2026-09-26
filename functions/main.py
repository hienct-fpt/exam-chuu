"""Cloud Functions (Python, 2nd gen) for the exam practice app.

grade_attempt : Firestore trigger on students/{uid}/attempts/{aid}.
   in_progress -> submitted : grade (exam attempt against answerKeys/{examId}, or a cross-exam practice set
                              against several keys), write result, refresh students/{uid}/topicStats.
   graded + manualGrades changed : regrade.
redeem_invite : callable, child enters a parent's invite code -> link students/{child}.parents + students/{parent}.children.
create_child_account : callable, signed-out child opens the invite link -> new login-ID account, linked.
reset_child_password : callable, linked parent sets a login-ID child's password.
unlink_child  : callable, parent removes a linked child.
"""
from __future__ import annotations

import datetime as dt
import re

from firebase_admin import auth, firestore, initialize_app
from firebase_functions import firestore_fn, https_fn, options

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


def _fail(code: https_fn.FunctionsErrorCode, msg: str) -> https_fn.HttpsError:
    return https_fn.HttpsError(code, msg)


# Children without a Google account sign in with a login ID + password; Firebase Auth needs an email, so the ID is
# mapped to this reserved (.invalid, never deliverable) domain. Must match CHILD_EMAIL_DOMAIN in web/src/api.firebase.js.
CHILD_EMAIL_DOMAIN = "kids.exam-chuu.invalid"
LOGIN_ID_RE = re.compile(r"^[a-z0-9_]{3,20}$")


def _invite_code(data) -> str:
    code = str((data or {}).get("code") or "").strip().upper()
    if not code.isalnum():
        raise _fail(https_fn.FunctionsErrorCode.INVALID_ARGUMENT, "招待コードが正しくありません")
    return code


def _valid_invite(snap) -> dict:
    if not snap.exists:
        raise _fail(https_fn.FunctionsErrorCode.NOT_FOUND, "招待コードが見つかりません")
    inv = snap.to_dict()
    if inv["expiresAt"] < dt.datetime.now(dt.timezone.utc):
        raise _fail(https_fn.FunctionsErrorCode.FAILED_PRECONDITION, "招待コードの有効期限が切れています")
    return inv


def _link(db, code: str, child: str, child_fields: dict | None = None) -> str:
    """Consume invites/{code} and link child <-> its parent in one transaction. Returns the parent's name."""
    inv_ref = db.document(f"invites/{code}")

    @firestore.transactional
    def run(tx) -> str:
        inv = _valid_invite(inv_ref.get(transaction=tx))
        parent = inv["parentUid"]
        if parent == child:
            raise _fail(https_fn.FunctionsErrorCode.INVALID_ARGUMENT, "保護者自身のアカウントは登録できません")
        name = inv.get("parentName") or "保護者"
        tx.set(db.document(f"students/{child}"),
               {**(child_fields or {}), "parents": firestore.ArrayUnion([parent]), "parentNames": {parent: name}}, merge=True)
        tx.set(db.document(f"students/{parent}"), {"children": firestore.ArrayUnion([child])}, merge=True)
        tx.delete(inv_ref)
        return name

    return run(db.transaction())


@https_fn.on_call()
def redeem_invite(req: https_fn.CallableRequest) -> dict:
    """Signed-in child (e.g. own Google account) enters a single-use code from invites/{code} (24h expiry)."""
    if req.auth is None:
        raise _fail(https_fn.FunctionsErrorCode.UNAUTHENTICATED, "ログインしてください")
    return {"parentName": _link(firestore.client(), _invite_code(req.data), req.auth.uid)}


@https_fn.on_call()
def create_child_account(req: https_fn.CallableRequest) -> dict:
    """Child opened the parent's invite link while signed out: create a login-ID account and link it.
    Only possible with a valid invite, so there is no open sign-up."""
    data = req.data or {}
    code = _invite_code(data)
    login_id = str(data.get("loginId") or "").strip().lower()
    password = str(data.get("password") or "")
    name = str(data.get("name") or "").strip()
    if not LOGIN_ID_RE.match(login_id):
        raise _fail(https_fn.FunctionsErrorCode.INVALID_ARGUMENT, "ログインIDは半角英小文字・数字・_ で3〜20文字にしてください")
    if len(password) < 6:
        raise _fail(https_fn.FunctionsErrorCode.INVALID_ARGUMENT, "パスワードは6文字以上にしてください")
    if not 1 <= len(name) <= 20:
        raise _fail(https_fn.FunctionsErrorCode.INVALID_ARGUMENT, "名前を20文字以内で入力してください")
    db = firestore.client()
    _valid_invite(db.document(f"invites/{code}").get())  # fail before creating an Auth user for a bad code
    try:
        user = auth.create_user(email=f"{login_id}@{CHILD_EMAIL_DOMAIN}", password=password, display_name=name)
    except auth.EmailAlreadyExistsError:
        raise _fail(https_fn.FunctionsErrorCode.ALREADY_EXISTS, "このログインIDはすでに使われています")
    try:
        parent_name = _link(db, code, user.uid, {"name": name, "loginId": login_id,
                                                 "createdAt": dt.datetime.now(dt.timezone.utc)})
    except Exception:
        auth.delete_user(user.uid)  # code was used up concurrently (or expired) -> don't leave an orphan account
        raise
    return {"parentName": parent_name}


@https_fn.on_call()
def reset_child_password(req: https_fn.CallableRequest) -> dict:
    """Linked parent sets a new password for a login-ID child account (no email to reset through)."""
    if req.auth is None:
        raise _fail(https_fn.FunctionsErrorCode.UNAUTHENTICATED, "ログインしてください")
    child, password = str((req.data or {}).get("childUid") or ""), str((req.data or {}).get("password") or "")
    if len(password) < 6:
        raise _fail(https_fn.FunctionsErrorCode.INVALID_ARGUMENT, "パスワードは6文字以上にしてください")
    snap = firestore.client().document(f"students/{child}").get() if child else None
    d = snap.to_dict() if snap and snap.exists else {}
    if req.auth.uid not in (d.get("parents") or []):
        raise _fail(https_fn.FunctionsErrorCode.PERMISSION_DENIED, "この生徒とは連携していません")
    if not d.get("loginId") or not (auth.get_user(child).email or "").endswith("@" + CHILD_EMAIL_DOMAIN):
        raise _fail(https_fn.FunctionsErrorCode.FAILED_PRECONDITION, "Google アカウントの生徒はパスワードを変更できません")
    auth.update_user(child, password=password)
    return {"ok": True}


@https_fn.on_call()
def unlink_child(req: https_fn.CallableRequest) -> dict:
    if req.auth is None:
        raise _fail(https_fn.FunctionsErrorCode.UNAUTHENTICATED, "ログインしてください")
    parent, child = req.auth.uid, str((req.data or {}).get("childUid") or "")
    db = firestore.client()
    child_ref = db.document(f"students/{child}")
    snap = child_ref.get() if child else None
    if not snap or not snap.exists or parent not in (snap.to_dict().get("parents") or []):
        raise _fail(https_fn.FunctionsErrorCode.PERMISSION_DENIED, "この生徒とは連携していません")
    batch = db.batch()
    batch.update(child_ref, {"parents": firestore.ArrayRemove([parent]), f"parentNames.{parent}": firestore.DELETE_FIELD})
    batch.update(db.document(f"students/{parent}"), {"children": firestore.ArrayRemove([child])})
    batch.commit()
    return {"ok": True}
