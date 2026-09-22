"""Upload pipeline output to Firestore with the Admin SDK.

  exams/{examId}        <- pipeline/out/bank/{examId}.json   (public metadata + items, no answers)
  answerKeys/{examId}   <- pipeline/out/answers_all.json     ({items: {slotId: key}})

Auth: set GOOGLE_APPLICATION_CREDENTIALS to a service-account json, or run
  gcloud auth application-default login
usage: python scripts/import_bank.py [--project PROJECT_ID] [exam_id ...]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "out"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=None)
    ap.add_argument("exams", nargs="*")
    args = ap.parse_args()

    opts = {"projectId": args.project} if args.project else None
    firebase_admin.initialize_app(credentials.ApplicationDefault(), opts)
    db = firestore.client()

    index = json.loads((OUT / "bank" / "index.json").read_text(encoding="utf-8"))
    all_keys = json.loads((OUT / "answers_all.json").read_text(encoding="utf-8"))
    wanted = set(args.exams) or {e["id"] for e in index}

    batch = db.batch()
    n = 0
    for e in index:
        eid = e["id"]
        if eid not in wanted:
            continue
        bank = json.loads((OUT / "bank" / f"{eid}.json").read_text(encoding="utf-8"))
        keys = {iid.split("#", 1)[1]: k for iid, k in all_keys.items() if iid.startswith(eid + "#")}
        batch.set(db.document(f"exams/{eid}"), bank)
        batch.set(db.document(f"answerKeys/{eid}"), {"items": keys, "count": len(keys)})
        n += 2
        print(f"[import] {eid}: {len(bank['items'])} items, {len(keys)} keys")
        if n >= 400:
            batch.commit()
            batch = db.batch()
            n = 0
    if n:
        batch.commit()
    print("[import] done")


if __name__ == "__main__":
    main()
