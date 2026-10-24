"""Step 1: scan source folders -> out/exams.json

Exam id: {school}_{year}_{session}_{subject}
  kyoritsu_2026_2-1_math          kyoritsu: 2-1 / 2-2 入試
  shinagawa_2026_r1_science       shinagawa: r1 / r2 (第1回 / 第2回), m1 (算数1教科)
Shinagawa 社会・理科 share one 問題 PDF; `page_range` (0-based, inclusive) selects the subject's pages.
Shinagawa 解答 are scanned images (answers are transcribed into pipeline/overrides/answers/*.json).
  kumiwake_2026_r1_math           kumiwake: 四谷大塚 公開組分けテスト 5年 r1..r6 (第1〜6回)
  chuo_2026_1_math                chuo: 1 / 2 (第1回 / 第２回)           chuo_past/{year}年度/
  sakaehigashi_2025_a_math        sakaehigashi: a (A日程)               sakaehigashi_past/{year}年度/
Every school keeps its source PDFs in {school}_past/ (git-ignored); each entry here is derived from the file names.
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz

from common import ROOT, OUT, SUBJECT_MAP, KIND_MAP, nfkc, dump_json, load_json

KYORITSU = ROOT / "kyoritsu_past"
SHINAGAWA = ROOT / "shinagawa_past"

RE_KYO = re.compile(r"^(?P<session>\d-\d)入試_(?P<subject>[^_]+)_(?P<kind>問題|模範解答|解答用紙)\.pdf$")
# older years come as `sansu-mondai.pdf` / `sansu-kaito.pdf`: scanned 問題 (2-page spreads, 解答用紙 on the last
# page) + a text-layer 解答; no session in the name -> KYO_ROMAJI_SESSION, read off the 問題 cover
RE_KYO_ROMAJI = re.compile(r"^(?P<subject>sansu|kokugo|rika|shakai)-(?P<kind>mondai|kaito)\.pdf$")
ROMAJI_SUBJECT = {"sansu": "算数", "kokugo": "国語", "rika": "理科", "shakai": "社会"}
ROMAJI_KIND = {"mondai": "問題", "kaito": "模範解答"}
KYO_ROMAJI_SESSION = {2023: "2-1"}
RE_YEAR = re.compile(r"(\d{4})年度")
SUBJECT_LABEL = {"math": "算数", "japanese": "国語", "science": "理科", "social": "社会"}


def _kyo_match(pdf: Path, year: int) -> tuple[str, str, str] | None:
    """(session, 教科, kind) of a kyoritsu file name, either naming scheme."""
    if m := RE_KYO.match(pdf.name):
        return m["session"], m["subject"], m["kind"]
    if (m := RE_KYO_ROMAJI.match(pdf.name)) and year in KYO_ROMAJI_SESSION:
        return KYO_ROMAJI_SESSION[year], ROMAJI_SUBJECT[m["subject"]], ROMAJI_KIND[m["kind"]]
    return None


def scan_kyoritsu() -> dict[str, dict]:
    exams: dict[str, dict] = {}
    for pdf in KYORITSU.rglob("*.pdf"):
        ym = RE_YEAR.search(pdf.parent.name)
        if not ym or not (m := _kyo_match(pdf, int(ym.group(1)))):
            continue
        session, label, kind = m
        subject = SUBJECT_MAP.get(label)
        if not subject:
            continue
        year = int(ym.group(1))
        eid = f"kyoritsu_{year}_{session}_{subject}"
        ex = exams.setdefault(eid, {
            "id": eid, "school": "kyoritsu", "school_name": "共立女子中学校",
            "year": year, "session": session, "session_label": f"{session.replace('-', '/')}入試",
            "subject": subject, "subject_label": label,
            "time_limit_min": 45 if subject in ("math", "japanese") else 30,
            "files": {},
        })
        ex["files"][KIND_MAP[kind]] = str(pdf.relative_to(ROOT)).replace("\\", "/")
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
    exams.update(_scan_shinagawa_scanned())
    return {k: v for k, v in exams.items() if "question" in v["files"]}


# 2023-25 第1回 came as scans named `品川女子学院_2023年算数問題.pdf` / `..回答.pdf` (one PDF per subject, no
# 解答用紙); kept apart from the 解答用紙 folders on purpose (no `sheet`). Segments/answers: full override lists.
RE_SHINA_SCAN = re.compile(r"^品川女子学院_(?P<year>\d{4})年(?P<subject>算数|理科|社会)(?P<kind>問題|回答)\.pdf$")


def _scan_shinagawa_scanned() -> dict[str, dict]:
    exams: dict[str, dict] = {}
    for pdf in sorted(SHINAGAWA.glob("*年度_入試問題解答/品川女子学院_*.pdf")):
        if not (m := RE_SHINA_SCAN.match(pdf.name)):
            continue
        year, subject = int(m["year"]), SUBJECT_MAP[m["subject"]]
        eid = f"shinagawa_{year}_r1_{subject}"
        ex = exams.setdefault(eid, {
            "id": eid, "school": "shinagawa", "school_name": "品川女子学院中等部",
            "year": year, "session": "r1", "session_label": "第1回",
            "subject": subject, "subject_label": m["subject"],
            "time_limit_min": 45 if subject == "math" else 30,
            "files": {},
        })
        ex["files"]["question" if m["kind"] == "問題" else "answer"] = str(pdf.relative_to(ROOT)).replace("\\", "/")
    return exams


# --------------------------------------------------------------- chuo / sakaehigashi

CHUO = ROOT / "chuo_past"
RE_CHUO = re.compile(r"^中央大学附属_(?P<year>\d{4})年度_(?P<label>第(?P<round>[1-9１-９])回)_(?P<subject>算数|国語|理科|社会)問題\.pdf$")
SAKAEHIGASHI = ROOT / "sakaehigashi_past"
RE_SAKAE = re.compile(r"^栄東中学校_(?P<year>\d{4})年(?P<subject>算数|国語|理科|社会)(?P<kind>問題|回答)\.pdf$")


def scan_chuo() -> dict[str, dict]:
    """中央大学附属: 問題 only (no 解答 PDF) -- keys are in overrides/answers as full slot lists."""
    exams: dict[str, dict] = {}
    for pdf in sorted(CHUO.glob("*年度/*.pdf")):
        if not (m := RE_CHUO.match(pdf.name)):
            continue
        year, subject, rnd = int(m["year"]), SUBJECT_MAP[m["subject"]], nfkc(m["round"])
        eid = f"chuo_{year}_{rnd}_{subject}"
        exams[eid] = {
            "id": eid, "school": "chuo", "school_name": "中央大学附属中学校",
            "year": year, "session": rnd, "session_label": m["label"],
            "subject": subject, "subject_label": m["subject"],
            "time_limit_min": 50 if subject in ("math", "japanese") else 30,
            "files": {"question": str(pdf.relative_to(ROOT)).replace("\\", "/")},
        }
    return exams


def scan_sakaehigashi() -> dict[str, dict]:
    """栄東 A日程: scanned 問題 + 回答 (2026: 問題 only). Segments/answers: full override lists."""
    exams: dict[str, dict] = {}
    for pdf in sorted(SAKAEHIGASHI.glob("*年度/*.pdf")):
        if not (m := RE_SAKAE.match(pdf.name)):
            continue
        year, subject = int(m["year"]), SUBJECT_MAP[m["subject"]]
        eid = f"sakaehigashi_{year}_a_{subject}"
        ex = exams.setdefault(eid, {
            "id": eid, "school": "sakaehigashi", "school_name": "栄東中学校",
            "year": year, "session": "a", "session_label": "A日程",
            "subject": subject, "subject_label": m["subject"],
            "time_limit_min": 45 if subject in ("math", "japanese") else 30,
            "files": {},
        })
        ex["files"]["question" if m["kind"] == "問題" else "answer"] = str(pdf.relative_to(ROOT)).replace("\\", "/")
    return {k: v for k, v in exams.items() if "question" in v["files"]}


# --------------------------------------------------------------- kumiwake

KUMIWAKE = ROOT / "kumiwake_past"
# matched against the NFKC file name: "2026年3月 公開組分けテスト5年 第1回算数問題.pdf"
RE_KUMI = re.compile(r"^(?P<year>\d{4})年(?P<month>\d{1,2})月\s*公開組分けテスト(?P<grade>\d)年\s*第(?P<round>\d)回"
                     r"(?P<subject>算数|国語|理科|社会)(?P<kind>問題|回答)\.pdf$")


def scan_kumiwake() -> dict[str, dict]:
    """四谷大塚 公開組分けテスト (5年, 第1〜6回; 第6回 has no 回答 sheets). The 回答 PDFs are the child's own scored answer sheets (handwriting,
    ○/✓, name), NOT 模範解答: kept as `scored_sheet` for slot layout checks only, never shipped or read as answers.
    The keys come from the round's 結果.pdf (`result`)."""
    exams: dict[str, dict] = {}
    for pdf in sorted(KUMIWAKE.glob("*.pdf")):
        m = RE_KUMI.match(nfkc(pdf.name))
        if not m:
            continue
        year, rnd, subject = int(m["year"]), int(m["round"]), SUBJECT_MAP[m["subject"]]
        eid = f"kumiwake_{year}_r{rnd}_{subject}"
        rel = str(pdf.relative_to(ROOT)).replace("\\", "/")
        ex = exams.setdefault(eid, {
            "id": eid, "school": "kumiwake", "school_name": "四谷大塚 公開組分けテスト",
            "year": year, "session": f"r{rnd}", "session_label": f"第{rnd}回 ({int(m['month'])}月)",
            "subject": subject, "subject_label": m["subject"],
            "time_limit_min": 50 if subject in ("math", "japanese") else 35,
            "files": {},
        })
        if m["kind"] == "問題":
            ex["files"]["question"] = rel
            cover = re.sub(r"\s+", "", fitz.open(pdf)[0].get_text())
            if t := re.search(r"試験時間(\d+)分", cover):
                ex["time_limit_min"] = int(t.group(1))
        else:
            ex["files"]["scored_sheet"] = rel
    # 結果.pdf (one per round, all subjects): 解答と解説 + 正答率一覧 (配点, 領域・内容) -- the keys were transcribed
    # from it into overrides/answers + tags; it also holds the child's scores, so it is never shipped either
    for pdf in sorted(KUMIWAKE.glob("*結果.pdf")):
        if m := re.search(r"第(\d)回", nfkc(pdf.name)):
            for ex in exams.values():
                if ex["session"] == f"r{m.group(1)}":
                    ex["files"]["result"] = str(pdf.relative_to(ROOT)).replace("\\", "/")
    return {k: v for k, v in exams.items() if "question" in v["files"]}


SCANNERS = {"kyoritsu": scan_kyoritsu, "shinagawa": scan_shinagawa, "kumiwake": scan_kumiwake,
            "chuo": scan_chuo, "sakaehigashi": scan_sakaehigashi}


def main(subjects: tuple[str, ...] | None = None, schools: tuple[str, ...] = tuple(SCANNERS)) -> dict:
    # entries of schools not re-scanned this run survive; the scanned schools are rebuilt from their folders
    exams = {k: v for k, v in (load_json(OUT / "exams.json", {}) or {}).items() if v.get("school") not in schools}
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
