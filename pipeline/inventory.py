"""Step 1: scan source folders -> out/exams.json

Exam id format: {school}_{year}_{session}_{subject}, e.g. kyoritsu_2026_2-1_math
"""
from __future__ import annotations

import re
from pathlib import Path

from common import ROOT, OUT, SUBJECT_MAP, KIND_MAP, nfkc, dump_json

KYORITSU = ROOT / "kyoritsu_past"
SHINAGAWA = ROOT / "shinagawa_past"

# kyoritsu_past/2026年度/2-1入試_算数_問題.pdf
RE_KYO = re.compile(r"^(?P<session>\d-\d)入試_(?P<subject>[^_]+)_(?P<kind>問題|模範解答|解答用紙)\.pdf$")
RE_YEAR = re.compile(r"(\d{4})年度")


def scan_kyoritsu() -> dict[str, dict]:
    exams: dict[str, dict] = {}
    for pdf in KYORITSU.rglob("*.pdf"):
        m = RE_KYO.match(pdf.name)
        ym = RE_YEAR.search(pdf.parent.name)
        if not m or not ym:
            continue
        subject = SUBJECT_MAP.get(m["subject"])
        if not subject:
            continue
        year = int(ym.group(1))
        session = m["session"]
        eid = f"kyoritsu_{year}_{session}_{subject}"
        ex = exams.setdefault(eid, {
            "id": eid,
            "school": "kyoritsu",
            "school_name": "共立女子中学校",
            "year": year,
            "session": session,
            "session_label": f"{session.replace('-', '/')}入試",
            "subject": subject,
            "subject_label": m["subject"],
            "time_limit_min": 45 if subject in ("math", "japanese") else 30,
            "files": {},
        })
        ex["files"][KIND_MAP[m["kind"]]] = str(pdf.relative_to(ROOT)).replace("\\", "/")
    return exams


def main(subjects: tuple[str, ...] | None = ("math",), schools: tuple[str, ...] = ("kyoritsu",)) -> dict:
    exams = {}
    if "kyoritsu" in schools:
        exams.update(scan_kyoritsu())
    if subjects:
        exams = {k: v for k, v in exams.items() if v["subject"] in subjects}
    ordered = dict(sorted(exams.items()))
    dump_json(OUT / "exams.json", ordered)
    print(f"[inventory] {len(ordered)} exams -> {OUT / 'exams.json'}")
    for e in ordered.values():
        missing = [k for k in ("question", "answer", "sheet") if k not in e["files"]]
        flag = f"  MISSING {missing}" if missing else ""
        print(f"  {e['id']}{flag}")
    return ordered


if __name__ == "__main__":
    import sys
    subs = tuple(sys.argv[1:]) or ("math",)
    main(subjects=None if subs == ("all",) else subs)
