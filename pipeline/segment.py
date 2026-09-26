"""Step 2: detect 大問 / 問 / 小問 regions in 問題 PDF -> out/segments/{exam_id}.json

Layout facts (kyoritsu, B5 516x729pt, horizontal subjects):
  - 大問 marker: single digit, font size >= 12, x < 70
  - sub markers at the left margin (x < 95): 問１． / （１） / ⑴ / ①
  - page number "− n −" at the bottom; "（問題はこれで終わりです）" trailer
Output (nested tree):
  {"exam_id": ..., "bigs": [
     {"no": 1, "regions": [...], "stem": {...}|null,
      "subs": [{"key": "1", "label": "問1", "rank": 1, "regions": [...], "stem": {...}|null,
                "subs": [{"key": "1", "label": "(1)", "rank": 2, "regions": [...], "subs": []}]}]}]}
A region = {"page": p, "y0": .., "y1": ..}. Multi-page nodes have several regions.
Manual fixes: pipeline/overrides/segments/{exam_id}.json  (replaces the node with the same path, e.g. {"bigs": {"3": {...}}})
"""
from __future__ import annotations

import re
import unicodedata

import fitz

from common import OUT, OVERRIDES, ROOT, Span, iter_spans, load_json, dump_json
from labels import parse_label, is_big_digit, RE_Q

BIG_MIN_SIZE = 12.0
BIG_MAX_X = 70
SUB_MAX_X = 95
TOP_MARGIN = 30
PAD_TOP = 1.5
PAD_BOTTOM = 4

RE_FOOTER = re.compile(r"^[−\-–—－]\s*(?:社|理|算|国)?\s*\d+\s*[−\-–—－]$")   # − 3 −, － 理4 －, － 社8 －
NOISE_TEXT = ("（問題はこれで終わりです）", "【問題は次のページにもあります】", "【問題は次のページに続きます】",
              "【計算用紙】", "【問題はこれで終わりです】")


def _is_footer(t: str) -> bool:
    """Page number decorated with dashes/symbols: '− 4 −', '－ 理4 －', '━ 00 ━4' (2018 shinagawa: hidden digits)."""
    if RE_FOOTER.match(t):
        return True
    core = "".join(c for c in t if not c.isspace() and unicodedata.category(c)[0] not in "PS")
    return core != t.replace(" ", "").replace("\u3000", "") and bool(re.fullmatch(r"(?:社|理|算|国)?\d{1,4}", core))


def _is_noise_block(text: str, y0: float | None = None, page_h: float | None = None) -> bool:
    """Footer test only near the page bottom (a '(1)' label block elsewhere must never count as noise)."""
    t = text.strip()
    if t in NOISE_TEXT:
        return True
    near_bottom = y0 is None or page_h is None or y0 > page_h - 60
    return near_bottom and _is_footer(t)


def page_content_bottom(page: fitz.Page, y_from: float, y_to: float | None = None) -> float:
    """Lowest y of real content in [y_from, y_to), ignoring page-number footer and page-sized frames."""
    y_to = y_to if y_to is not None else page.rect.height
    bottom = y_from
    clip = fitz.Rect(0, y_from, page.rect.width, y_to)
    blocks = [(b, "".join(s["text"] for l in b.get("lines", []) for s in l["spans"]))
              for b in page.get_text("dict", clip=clip)["blocks"]]
    # nothing meaningful sits below the page number / "次のページに続きます" trailer (stray ruby glyphs do)
    ph, pw = page.rect.height, page.rect.width
    for b, txt in blocks:
        if _is_noise_block(txt, b["bbox"][1], ph) and b["bbox"][1] > y_from + 20:
            y_to = min(y_to, b["bbox"][1])
    for b, txt in blocks:
        if _is_noise_block(txt, b["bbox"][1], ph) or b["bbox"][1] >= y_to:
            continue
        bottom = max(bottom, min(b["bbox"][3], y_to))
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if r.height > 0.5 * ph or r.width > 0.9 * pw:
            continue
        if r.x1 < 20 or r.x0 > pw - 20:      # printer's crop marks at the page edge
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


# which marker ranks a subject uses, and which ranks may appear directly under a 大問
SUBJECT_RULES = {
    "math":    {"ranks": {3}, "top": {3}},          # kyoritsu: ①②③ directly under 大問; （１）lists are text
    "science": {"ranks": {2, 3}, "top": {2}},       # （１）（２） then ①② inside
    "social":  {"ranks": {1, 2, 3}, "top": {1, 2}}, # 問１ then （１） then ①
    "shinagawa_math":    {"ranks": {2, 3}, "top": {2}},                   # ⑴⑵ then ①
    "shinagawa_science": {"ranks": {1, 2, 3}, "top": {1, 2}, "roman": True},  # Ⅰ/Ⅱ sections, ⑴, ①
    "shinagawa_social":  {"ranks": {1, 2, 3}, "top": {1, 2}},
    # chuo: 大問 box-digit sits at x0 up to ~76pt (kyoritsu's is <70); （１）（２） render as 3 spans
    # ("（" / digit / "）" in different fonts, since the digit reuses the equation-numeral font) -> merge them.
    "chuo_math":    {"ranks": {2}, "top": {2}, "big_max_x": 80, "merge_paren_digit": True},
    "chuo_science": {"ranks": {1}, "top": {1}, "big_max_x": 80},   # 〔問１〕 leaf questions, no sub-parts
    "chuo_social":  {"ranks": {1}, "top": {1}, "roman_big": True}, # 大問 = boxed Ⅰ/Ⅱ; 問１．leaf questions
}


BOLD_HINTS = ("-Bo", "Bold", "-He", "Heav", "ExHe", "-Med")


def _is_big_marker(s) -> bool:
    """kyoritsu: half-width digit >= 12pt. shinagawa 社会/理科: bold full-width digit (9-11pt) at the left margin."""
    t = s.text.strip()
    if s.size >= BIG_MIN_SIZE:
        return True
    fullwidth = all(ch in "０１２３４５６７８９" for ch in t)
    return fullwidth and s.size >= 9 and any(h in s.font for h in BOLD_HINTS)


ROMAN_BIG = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"
RE_BARE_DIGIT = re.compile(r"^[0-9０-９]{1,2}$")


def _merge_split_parens(spans: list) -> list:
    """chuo: "（１）" prints as 3 spans ("（", "１", "）") because the digit reuses the equation-numeral
    font. Splice them into one synthetic span so parse_label sees the whole marker, like elsewhere."""
    out = []
    i = 0
    while i < len(spans):
        s = spans[i]
        if s.text in ("(", "（") and s.x0 < 100 and i + 2 < len(spans):
            d, c = spans[i + 1], spans[i + 2]
            starts_close = c.text.startswith(")") or c.text.startswith("）")  # closing paren may run on into trailing prose in the same span
            if (d.page == s.page and c.page == s.page and starts_close
                    and RE_BARE_DIGIT.match(d.text) and abs(d.y0 - s.y0) < 3 and abs(c.y0 - s.y0) < 3
                    and -1 <= d.x0 - s.x1 < 15 and -1 <= c.x0 - d.x1 < 15):
                merged = Span(s.page, s.x0, s.y0, d.x1 + 2, max(s.y1, d.y1, c.y1), d.size, d.font, f"（{d.text}）")
                out.append(merged)
                i += 3
                continue
        out.append(s)
        i += 1
    return out


def find_markers(doc: fitz.Document, subject: str = "math", page_range: tuple[int, int] | None = None) -> list[dict]:
    """All markers in reading order: [{page, y, rank, key, label, big}]; rank 0 = 大問.
    Kana (あいう) are never markers here: they are fill-in slots inside the text.
    page_range (inclusive) restricts to a subject's pages inside a combined PDF (its first page is content)."""
    rules = SUBJECT_RULES.get(subject, SUBJECT_RULES["science"])
    big_max_x = rules.get("big_max_x", BIG_MAX_X)
    first, last = page_range if page_range else (1, len(doc) - 1)
    spans = list(iter_spans(doc))
    if rules.get("merge_paren_digit"):
        spans = _merge_split_parens(spans)
    raw = []
    for s in spans:
        if s.page < first or s.page > last or s.y0 < TOP_MARGIN:
            continue
        if s.x0 < big_max_x and (n := is_big_digit(s.text)) is not None and _is_big_marker(s):
            raw.append({"page": s.page, "y": s.y0, "rank": 0, "key": str(n), "label": str(n), "no": n})
            continue
        if rules.get("roman_big") and s.x0 < big_max_x and s.text.strip() in ROMAN_BIG and s.size >= BIG_MIN_SIZE:
            n = ROMAN_BIG.index(s.text.strip()) + 1
            raw.append({"page": s.page, "y": s.y0, "rank": 0, "key": str(n), "label": s.text.strip(), "no": n})
            continue
        if s.x0 < SUB_MAX_X:
            lab = parse_label(s.text)
            if lab and lab.kind == "ROMAN" and rules.get("roman"):
                raw.append({"page": s.page, "y": s.y0, "rank": 1, "key": lab.text, "label": lab.text})
                continue
            if lab and lab.rank in rules["ranks"] and lab.kind != "K":
                raw.append({"page": s.page, "y": s.y0, "rank": lab.rank, "key": lab.key, "label": lab.text})
                if lab.kind == "Q" and 2 in rules["ranks"]:
                    # "問２　⑴ …" in one span (shinagawa 社会): the ⑴ is a second marker just below 問２
                    rest = s.text.strip()[RE_Q.match(s.text.strip()).end():].strip()
                    sub = parse_label(rest)
                    if sub and sub.rank == 2:
                        raw.append({"page": s.page, "y": s.y0 + 0.01, "rank": 2, "key": sub.key, "label": sub.text})
    raw.sort(key=lambda m: (m["page"], m["y"]))
    # structural filter: a marker is valid only if its would-be parent is a 大問 (and rank allowed at top)
    # or a marker of exactly one rank higher (no skipping levels) -> drops list bullets in passages
    out = []
    stack: list[int] = []            # ranks of open nodes
    seen: list[set[str]] = []        # keys already used at each stack depth (siblings)
    for m in raw:
        r = m["rank"]
        if r == 0:
            out.append(m)
            stack = [0]
            seen = [set()]
            continue
        if not stack:
            continue
        while len(stack) > 1 and stack[-1] >= r:
            stack.pop()
            seen.pop()
        parent = stack[-1]
        ok = (parent == 0 and r in rules["top"]) or (parent > 0 and r > parent and (r - parent == 1 or parent == 1 and r == 2))
        if not ok:
            continue
        if m["key"] in seen[-1]:     # same marker repeated under one parent = a reference in the text, not a new question
            continue
        seen[-1].add(m["key"])
        out.append(m)
        stack.append(r)
        seen.append(set())
    return out


def _regions(doc: fitz.Document, start: dict, end: dict | None, last_page: int) -> list[dict]:
    """Regions from start marker down to end marker (exclusive) or to content end."""
    sp, sy = start["page"], start["y"]
    ep = end["page"] if end else last_page
    ey = end["y"] if end else None
    regions = []
    for p in range(sp, ep + 1):
        y0 = sy - PAD_TOP if p == sp else TOP_MARGIN
        limit = ey - PAD_TOP if (p == ep and ey is not None) else None
        if limit is not None and limit - y0 < 8 and p == ep:
            continue
        y1 = page_content_bottom(doc[p], y0, limit)
        if y1 - y0 > 8:
            regions.append({"page": p, "y0": round(y0, 1), "y1": round(y1, 1)})
    return regions


def build_tree(doc: fitz.Document, markers: list[dict], last_page: int) -> list[dict]:
    """Nest markers by rank; a marker closes every open node with rank >= its own."""
    # first pass: node list with next-marker (any rank) for leaf regions
    nodes = []
    for i, m in enumerate(markers):
        nxt = markers[i + 1] if i + 1 < len(markers) else None
        nodes.append({**m, "_next_any": nxt, "subs": []})
    # end marker for each node = next marker with rank <= own rank
    for i, n in enumerate(nodes):
        end = None
        for m in markers[i + 1:]:
            if m["rank"] <= n["rank"]:
                end = m
                break
        n["_end"] = end
    bigs: list[dict] = []
    stack: list[dict] = []
    for n in nodes:
        while stack and stack[-1]["rank"] >= n["rank"]:
            stack.pop()
        node = {"key": n["key"], "label": n["label"], "rank": n["rank"],
                "regions": _regions(doc, n, n["_end"], last_page), "stem": None, "subs": []}
        if n["rank"] == 0:
            node["no"] = n["no"]
            bigs.append(node)
        elif stack:
            stack[-1]["subs"].append(node)
        else:
            # sub marker before any big marker (rare) -> attach to last big
            if bigs:
                bigs[-1]["subs"].append(node)
        # stem = from this marker to its first child marker
        first_child = n["_next_any"] if (n["_next_any"] and n["_next_any"]["rank"] > n["rank"]) else None
        if first_child and node["regions"]:
            stem_regions = _regions(doc, n, first_child, last_page)
            node["stem"] = stem_regions[0] if len(stem_regions) == 1 else (stem_regions or None)
            if isinstance(node["stem"], dict) and node["stem"]["y1"] - node["stem"]["y0"] < 8:
                node["stem"] = None
        stack.append(node)
    return bigs


def segment(doc: fitz.Document, subject: str = "math", page_range: tuple[int, int] | None = None) -> list[dict]:
    markers = find_markers(doc, subject, page_range)
    last_page = page_range[1] if page_range else len(doc) - 1
    while last_page > 0 and is_blank_page(doc[last_page]):
        last_page -= 1
    return build_tree(doc, markers, last_page)


def apply_overrides(exam_id: str, bigs: list[dict]) -> list[dict]:
    ov = load_json(OVERRIDES / "segments" / f"{exam_id}.json")
    if not ov:
        return bigs
    if isinstance(ov.get("bigs"), list):
        # full manual replacement (no per-big patch merge) -- used when auto-detection can't run at all
        return sorted(ov["bigs"], key=lambda b: b["no"])
    by_no = {str(b["no"]): b for b in bigs}
    for no, patch in (ov.get("bigs") or {}).items():
        if patch is None:
            by_no.pop(no, None)
        elif no in by_no:
            by_no[no].update(patch)
        else:
            by_no[no] = {"no": int(no), "key": no, "label": no, "rank": 0, "regions": [], "stem": None, "subs": [], **patch}
    return sorted(by_no.values(), key=lambda b: b["no"])


def _summary(node: dict) -> str:
    if not node["subs"]:
        return ""
    return "(" + ",".join(f"{s['label']}{_summary(s)}" for s in node["subs"]) + ")"


def main() -> None:
    exams = load_json(OUT / "exams.json", {})
    for eid, ex in exams.items():
        qpath = ex["files"].get("question")
        if not qpath:
            print(f"[segment] {eid}: no question pdf, skip")
            continue
        doc = fitz.open(ROOT / qpath)
        if ex["subject"] == "japanese":
            import japanese
            bigs = apply_overrides(eid, japanese.segment(doc))
            dump_json(OUT / "segments" / f"{eid}.json", {"exam_id": eid, "bigs": bigs})
            print(f"[segment] {eid}: " + " ".join(f"{b['no']}[{len(b['regions'])}p]" for b in bigs))
            continue
        rule = f"{ex['school']}_{ex['subject']}" if ex["school"] != "kyoritsu" else ex["subject"]
        pr = tuple(ex["page_range"]) if ex.get("page_range") else None
        bigs = apply_overrides(eid, segment(doc, rule, pr))
        dump_json(OUT / "segments" / f"{eid}.json", {"exam_id": eid, "bigs": bigs})
        print(f"[segment] {eid}: " + " ".join(f"{b['no']}{_summary(b)}" for b in bigs))


if __name__ == "__main__":
    main()
