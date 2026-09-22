"""Step 2: detect 大問 / 小問 regions in 問題 PDF -> out/segments/{exam_id}.json

Kyoritsu layout facts (B5, 516x729pt):
  - 大問 marker: digit, font size >= 12, x < 70
  - 小問 marker: ①②③ / ⑴⑵ at x ~ 79
  - Page header "− n −" at top, no footer
Output per exam:
  {
    "exam_id": ...,
    "bigs": [
      {"no": 1, "regions": [{"page":1,"y0":..,"y1":..}],        # whole 大問 (all pages)
       "stem": {"page":1,"y0":..,"y1":..} | null,               # text before first 小問
       "subs": [{"no":1,"label":"①","regions":[...]}, ...]}
    ]
  }
Manual fixes: pipeline/overrides/segments/{exam_id}.json (deep-merged by big no / sub no).
"""
from __future__ import annotations

import re

import fitz

from common import OUT, OVERRIDES, ROOT, Span, iter_spans, sub_index, load_json, dump_json

BIG_MIN_SIZE = 12.0
BIG_MAX_X = 70
SUB_MAX_X = 95
TOP_MARGIN = 30      # skip page header "− 1 −"
PAD_TOP = 6
PAD_BOTTOM = 4
LEFT = 40
RIGHT = 480


def find_markers(doc: fitz.Document) -> tuple[list[tuple[int, int, float]], list[tuple[int, int, float]]]:
    """Return (bigs, subs) as lists of (page, no, y)."""
    bigs: list[tuple[int, int, float]] = []
    subs: list[tuple[int, int, float]] = []
    for s in iter_spans(doc):
        if s.page == 0:  # cover page
            continue
        if s.y0 < TOP_MARGIN:
            continue
        if s.size >= BIG_MIN_SIZE and s.x0 < BIG_MAX_X and s.text.isdigit():
            bigs.append((s.page, int(s.text), s.y0))
        elif s.x0 < SUB_MAX_X and (idx := sub_index(s.text[0])) is not None:
            subs.append((s.page, idx, s.y0))
    bigs.sort(key=lambda t: (t[0], t[2]))
    subs.sort(key=lambda t: (t[0], t[2]))
    return bigs, subs


RE_FOOTER = re.compile(r"^[−\-–—]\s*\d+\s*[−\-–—]$")
NOISE_TEXT = ("（問題はこれで終わりです）",)


def _is_noise_block(text: str) -> bool:
    t = text.strip()
    return bool(RE_FOOTER.match(t)) or t in NOISE_TEXT


def page_content_bottom(page: fitz.Page, y_from: float, y_to: float | None = None) -> float:
    """Lowest y of real content in [y_from, y_to) (text, drawings, images), ignoring page-number footer."""
    y_to = y_to if y_to is not None else page.rect.height
    bottom = y_from
    clip = fitz.Rect(0, y_from, page.rect.width, y_to)
    for b in page.get_text("dict", clip=clip)["blocks"]:
        txt = "".join(s["text"] for l in b.get("lines", []) for s in l["spans"])
        if _is_noise_block(txt):
            continue
        bottom = max(bottom, min(b["bbox"][3], y_to))
    ph, pw = page.rect.height, page.rect.width
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if r.height > 0.5 * ph or r.width > 0.9 * pw:  # page frame / background, not content
            continue
        if r.y1 > y_from and r.y0 < y_to and r.width > 1:
            bottom = max(bottom, min(r.y1, y_to))
    for im in page.get_image_info():
        r = fitz.Rect(im["bbox"])
        if r.y1 > y_from and r.y0 < y_to:
            bottom = max(bottom, min(r.y1, y_to))
    return min(bottom + PAD_BOTTOM, y_to)


def is_blank_page(page: fitz.Page) -> bool:
    return not page.get_text().strip() and not page.get_image_info()


def segment(doc: fitz.Document) -> list[dict]:
    bigs, subs = find_markers(doc)
    n_pages = len(doc)
    # usable pages: 1..last non-blank
    last_page = n_pages - 1
    while last_page > 0 and is_blank_page(doc[last_page]):
        last_page -= 1

    # Build ordered cut points: each big marker is a hard cut; each big spans until next big marker.
    result = []
    for i, (bp, bno, by) in enumerate(bigs):
        if i + 1 < len(bigs):
            ep, _, ey = bigs[i + 1]
        else:
            ep, ey = last_page, None
        regions = []
        for p in range(bp, ep + 1):
            y0 = by - PAD_TOP if p == bp else TOP_MARGIN
            limit = ey - PAD_TOP if (p == ep and ey is not None) else None
            y1 = page_content_bottom(doc[p], y0, limit)
            if y1 - y0 > 8:
                regions.append({"page": p, "y0": round(y0, 1), "y1": round(y1, 1)})
        # subs inside this big
        my_subs = [(sp, sno, sy) for (sp, sno, sy) in subs
                   if (sp, sy) > (bp, by) and (ey is None or (sp, sy) < (ep, ey))]
        sub_entries = []
        for j, (sp, sno, sy) in enumerate(my_subs):
            if j + 1 < len(my_subs):
                nep, _, ney = my_subs[j + 1]
            else:
                nep, ney = ep, ey
            sregions = []
            for p in range(sp, nep + 1):
                y0 = sy - PAD_TOP if p == sp else TOP_MARGIN
                limit = ney - PAD_TOP if (p == nep and ney is not None) else None
                y1 = page_content_bottom(doc[p], y0, limit)
                if y1 - y0 > 8:
                    sregions.append({"page": p, "y0": round(y0, 1), "y1": round(y1, 1)})
            sub_entries.append({"no": sno, "label": _label(sno), "regions": sregions})
        stem = None
        if my_subs:
            sp, _, sy = my_subs[0]
            limit = sy - PAD_TOP if sp == bp else None
            stem = {"page": bp, "y0": round(by - PAD_TOP, 1),
                    "y1": round(page_content_bottom(doc[bp], by - PAD_TOP, limit), 1)}
            if stem["y1"] - stem["y0"] < 8:
                stem = None
        result.append({"no": bno, "regions": regions, "stem": stem, "subs": sub_entries})
    return result


def _label(n: int) -> str:
    return "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"[n - 1]


def apply_overrides(exam_id: str, bigs: list[dict]) -> list[dict]:
    ov = load_json(OVERRIDES / "segments" / f"{exam_id}.json")
    if not ov:
        return bigs
    by_no = {b["no"]: b for b in bigs}
    for ob in ov.get("bigs", []):
        b = by_no.get(ob["no"])
        if b is None:
            by_no[ob["no"]] = ob
            continue
        for k in ("regions", "stem"):
            if k in ob:
                b[k] = ob[k]
        if "subs" in ob:
            sub_by_no = {s["no"]: s for s in b["subs"]}
            for os_ in ob["subs"]:
                if os_.get("delete"):
                    sub_by_no.pop(os_["no"], None)
                    continue
                s = sub_by_no.setdefault(os_["no"], {"no": os_["no"], "label": _label(os_["no"]), "regions": []})
                s.update({k: v for k, v in os_.items() if k != "no"})
            b["subs"] = sorted(sub_by_no.values(), key=lambda s: s["no"])
    return sorted(by_no.values(), key=lambda b: b["no"])


def main() -> None:
    exams = load_json(OUT / "exams.json", {})
    for eid, ex in exams.items():
        qpath = ex["files"].get("question")
        if not qpath:
            print(f"[segment] {eid}: no question pdf, skip")
            continue
        doc = fitz.open(ROOT / qpath)
        bigs = apply_overrides(eid, segment(doc))
        dump_json(OUT / "segments" / f"{eid}.json", {"exam_id": eid, "bigs": bigs})
        summary = ", ".join(f"{b['no']}({len(b['subs'])})" for b in bigs)
        print(f"[segment] {eid}: 大問 x{len(bigs)} -> {summary}")


if __name__ == "__main__":
    main()
