"""Step 1: scan source folders -> out/exams.json

Exam id: {school}_{year}_{session}_{subject}
  kyoritsu_2026_2-1_math          kyoritsu: 2-1 / 2-2 入試
  shinagawa_2026_r1_science       shinagawa: r1 / r2 (第1回 / 第2回), m1 (算数1教科)
Shinagawa 社会・理科 share one 問題 PDF; `page_range` (0-based, inclusive) selects the subject's pages.
Shinagawa 解答 are scanned images (answers are transcribed into pipeline/overrides/answers/*.json).
  kawasaki_2026_k1_social         kawasaki: k1 / k2 (適性検査Ⅰ / Ⅱ), one exam per subject (table: kawasaki_exams.json)
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz

from common import ROOT, OUT, SUBJECT_MAP, KIND_MAP, nfkc, dump_json, load_json

KYORITSU = ROOT / "kyoritsu_past"
SHINAGAWA = ROOT / "shinagawa_past"

RE_KYO = re.compile(r"^(?P<session>\d-\d)入試_(?P<subject>[^_]+)_(?P<kind>問題|模範解答|解答用紙)\.pdf$")
RE_YEAR = re.compile(r"(\d{4})年度")
SUBJECT_LABEL = {"math": "算数", "japanese": "国語", "science": "理科", "social": "社会"}


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
            "id": eid, "school": "kyoritsu", "school_name": "共立女子中学校",
            "year": year, "session": session, "session_label": f"{session.replace('-', '/')}入試",
            "subject": subject, "subject_label": m["subject"],
            "time_limit_min": 45 if subject in ("math", "japanese") else 30,
            "files": {},
        })
        ex["files"][KIND_MAP[m["kind"]]] = str(pdf.relative_to(ROOT)).replace("\\", "/")
    return exams


# --------------------------------------------------------------- shinagawa

SESSION = {"第１回": ("r1", "第1回"), "第２回": ("r2", "第2回"), "算数１教科": ("m1", "算数1教科")}
RE_SUBJ_PAGE = re.compile(r"(?:[－\-]\s*)?(社|理)\s*(\d+)\s*(?:[－\-])?")


def _subject_pages(pdf: Path) -> dict[str, tuple[int, int]]:
    """Detect 社会 / 理科 page ranges in a combined 問題 PDF via page markers 社1.. / 理1.."""
    doc = fitz.open(pdf)
    ranges: dict[str, list[int]] = {}
    for i, page in enumerate(doc):
        t = page.get_text()
        head, tail = t[:300], t[-200:]
        for chunk in (head, tail):
            m = re.search(r"(?:[－\-]\s*)(社|理)\s*(\d+)\s*[－\-]", chunk) or re.search(r"^\s*(?:━.*?━\s*)?(社|理)\s*(\d+)\b", chunk, re.M)
            if m:
                subj = "social" if m.group(1) == "社" else "science"
                ranges.setdefault(subj, []).append(i)
                break
    return {k: (min(v), max(v)) for k, v in ranges.items()}


def _first_content_page(pdf: Path) -> int:
    """0 when page 0 already holds questions (no 注意 cover), else 1."""
    t = nfkc(fitz.open(pdf)[0].get_text()).replace(" ", "").replace("\u3000", "")
    return 1 if "注意" in t[:400] else 0


def scan_shinagawa() -> dict[str, dict]:
    exams: dict[str, dict] = {}
    for folder in sorted(SHINAGAWA.glob("*年度_入試問題解答")):
        year = int(RE_YEAR.search(folder.name).group(1))
        sheets_dir = SHINAGAWA / f"{year}年度_解答用紙"
        for pdf in sorted(folder.glob("*.pdf")):
            name = pdf.stem
            sess_key = next((k for k in SESSION if name.startswith(k)), None)
            if not sess_key:
                continue  # 表現力･総合型, 第３回 試験Ⅰ etc.
            sess, sess_label = SESSION[sess_key]
            rest = name[len(sess_key):].lstrip("_")
            rel = str(pdf.relative_to(ROOT)).replace("\\", "/")

            def exam(subject: str) -> dict:
                eid = f"shinagawa_{year}_{sess}_{subject}"
                return exams.setdefault(eid, {
                    "id": eid, "school": "shinagawa", "school_name": "品川女子学院中等部",
                    "year": year, "session": sess, "session_label": sess_label,
                    "subject": subject, "subject_label": SUBJECT_LABEL[subject],
                    "time_limit_min": 50 if subject == "math" else 30,
                    "files": {},
                })

            if rest in ("算数問題", "問題", "算数問題解答用紙"):
                e = exam("math")
                e["files"]["question"] = rel
                e["page_range"] = [_first_content_page(pdf), len(fitz.open(pdf)) - 1]
            elif rest == "社会理科問題":
                pr = _subject_pages(pdf)
                for subj, rng in pr.items():
                    e = exam(subj)
                    e["files"]["question"] = rel
                    e["page_range"] = list(rng)
            elif rest == "解答":
                subjects = ("math",) if sess == "m1" else ("math", "science", "social")
                for subj in subjects:
                    exam(subj)["files"]["answer_scan"] = rel
            elif rest == "解答用紙":
                subjects = ("math",) if sess == "m1" else ("math", "science", "social")
                for subj in subjects:
                    exam(subj)["files"]["sheet_all"] = rel
        # per-subject blank sheets (2026 style)
        if sheets_dir.exists():
            for pdf in sheets_dir.glob("*.pdf"):
                m = re.match(r"^(第[１２2３]回|算数１教科)_(算数|理科|社会|解答用紙)", pdf.stem)
                if not m:
                    continue
                key = m.group(1).replace("第2回", "第２回")
                if key not in SESSION:
                    continue
                sess, _ = SESSION[key]
                subj = SUBJECT_MAP.get(m.group(2), "math")
                eid = f"shinagawa_{year}_{sess}_{subj}"
                if eid in exams:
                    exams[eid]["files"]["sheet"] = str(pdf.relative_to(ROOT)).replace("\\", "/")
    return {k: v for k, v in exams.items() if "question" in v["files"]}


# --------------------------------------------------------------- kawasaki

KAWASAKI_CONFIG = ROOT / "pipeline" / "kawasaki_exams.json"
KENSA_LABEL = {"k1": "適性検査Ⅰ", "k2": "適性検査Ⅱ"}


def scan_kawasaki() -> dict[str, dict]:
    """川崎市立川崎高等学校附属中 適性検査: each 45-min 検査 mixes subjects, so it is split by 問題 into subject
    exams (hand-made table in kawasaki_exams.json). `page_bigs` = {問題no: [first, last]} (0-based, inclusive):
    every 問題 is delivered as page images (scans, 縦書き, 資料 spread over pages), see segment.page_only_bigs."""
    cfg = load_json(KAWASAKI_CONFIG, {}) or {}
    exams: dict[str, dict] = {}
    for e in cfg.get("exams", []):
        if not (ROOT / e["pdf"]).exists():
            continue
        files = {"question": e["pdf"]}
        if e.get("answer_pdf"):
            files["answer"] = e["answer_pdf"]
        exams[e["id"]] = {
            "id": e["id"], "school": "kawasaki", "school_name": "川崎市立川崎高等学校附属中学校",
            "year": e["year"], "session": e["kensa"], "session_label": KENSA_LABEL[e["kensa"]],
            "subject": e["subject"], "subject_label": SUBJECT_LABEL[e["subject"]],
            "time_limit_min": e["time_limit_min"], "files": files, "page_bigs": e["bigs"],
        }
    return exams


SCANNERS = {"kyoritsu": scan_kyoritsu, "shinagawa": scan_shinagawa, "kawasaki": scan_kawasaki}


def main(subjects: tuple[str, ...] | None = None, schools: tuple[str, ...] = tuple(SCANNERS)) -> dict:
    # hand-maintained entries survive a re-scan: schools without a scanner (chuo, sakaehigashi) and anything
    # imported from pipeline/in/ (shinagawa 2023-25)
    exams = {k: v for k, v in (load_json(OUT / "exams.json", {}) or {}).items()
             if v.get("school") not in schools or v.get("files", {}).get("question", "").startswith("pipeline/in/")}
    for school in schools:
        exams.update({k: v for k, v in SCANNERS[school]().items() if not subjects or v["subject"] in subjects})
    ordered = dict(sorted(exams.items()))
    dump_json(OUT / "exams.json", ordered)
    print(f"[inventory] {len(ordered)} exams -> {OUT / 'exams.json'}")
    for e in ordered.values():
        extra = f" pages={e['page_range']}" if e.get("page_range") else ""
        missing = [k for k in ("question",) if k not in e["files"]]
        print(f"  {e['id']}{extra}{'  MISSING ' + str(missing) if missing else ''}")
    return ordered


if __name__ == "__main__":
    import sys
    subs = tuple(a for a in sys.argv[1:] if a != "all")
    main(subjects=subs or None)
