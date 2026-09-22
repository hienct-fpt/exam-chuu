"""国語 (vertical text) support.

Questions : 大問 markers are horizontal digits (size ~12) at the top-right of the page where the 大問 starts.
            Items are not cropped per 問 (vertical columns); each 大問 is delivered as its page images.
Sheet     : 大問 digit (19.8pt) at the right of a header row; small digits above each answer column,
            numbered right-to-left (1 is right-most; half- or full-width). Narrow cells hold one answer;
            wide 記述 cells span several character columns and may extend under neighbouring narrow cells.
            Part labels inside a cell: Ⅰ/Ⅱ, A/B (side by side) or はじめ/終わり (stacked).
Model     : answers are large characters (>= 16pt); labels are reprinted (full-width 大問 digits, half-width
            column digits), so the same table model is rebuilt from the model's own labels.
"""
from __future__ import annotations

import re
import unicodedata

import fitz

from common import Span, iter_spans, nfkc
from sheet import _hlines

TOP = 30
BOTTOM_PAD = 6
PART_WORDS = {"Ⅰ", "Ⅱ", "Ⅲ", "A", "B", "C", "Ａ", "Ｂ", "Ｃ", "はじめ", "終わり", "X", "Y"}
FULLWIDTH = "１２３４５６７８９"


# ------------------------------------------------------------------ questions

def find_bigs(doc: fitz.Document) -> list[tuple[int, int]]:
    """[(big_no, page_index)] for pages that start a 大問."""
    out = []
    for s in iter_spans(doc):
        if s.page == 0 or s.y0 > 70 or s.x0 < 350:
            continue
        t = s.text.strip()
        if s.size >= 11.5 and len(t) == 1 and t in "123456789":
            out.append((int(t), s.page))
    out.sort(key=lambda t: t[1])
    dedup, seen = [], set()
    for no, p in out:
        if no not in seen:
            seen.add(no)
            dedup.append((no, p))
    return dedup


def _content_bottom(page: fitz.Page) -> float:
    ph, pw = page.rect.height, page.rect.width
    bottom = TOP
    for b in page.get_text("dict")["blocks"]:
        txt = "".join(s["text"] for l in b.get("lines", []) for s in l["spans"]).strip()
        if re.fullmatch(r"[−\-–—]\s*\d+\s*[−\-–—]", txt):
            continue
        bottom = max(bottom, b["bbox"][3])
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if r.height > 0.5 * ph or r.width > 0.9 * pw:
            continue
        bottom = max(bottom, r.y1)
    return min(bottom + BOTTOM_PAD, ph - 10)


def segment(doc: fitz.Document) -> list[dict]:
    bigs = find_bigs(doc)
    last = len(doc) - 1
    while last > 0 and not doc[last].get_text().strip() and not doc[last].get_image_info():
        last -= 1
    out = []
    for i, (no, p0) in enumerate(bigs):
        p1 = bigs[i + 1][1] - 1 if i + 1 < len(bigs) else last
        regions = [{"page": p, "y0": TOP, "y1": round(_content_bottom(doc[p]), 1)} for p in range(p0, p1 + 1)
                   if doc[p].get_text().strip()]
        out.append({"no": no, "key": str(no), "label": str(no), "rank": 0, "regions": regions,
                    "page_regions": regions, "stem": None, "subs": []})
    return out


# ------------------------------------------------------------------ spans

def _spans(doc: fitz.Document) -> list[Span]:
    return [s for s in iter_spans(doc) if s.page == 0]


def _char_spans(page: fitz.Page) -> list[Span]:
    """One Span per character (vertical answers get merged into horizontal spans otherwise)."""
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for line in b.get("lines", []):
            for sp in line["spans"]:
                for ch in sp["chars"]:
                    c = ch["c"]
                    if c.isspace() or c == "　":
                        continue
                    x0, y0, x1, y1 = ch["bbox"]
                    out.append(Span(0, x0, y0, x1, y1, sp["size"], sp["font"], c))
    return out


def _digit_spans(spans: list[Span]) -> list[Span]:
    return [s for s in spans if len(s.text.strip()) == 1 and nfkc(s.text).strip() in "123456789"]


def _bigs(spans: list[Span]) -> list[Span]:
    """大問 labels. Sheet: the big (>=15pt) digits. Model: full-width digits (column labels are half-width)."""
    digits = [d for d in _digit_spans(spans) if d.y0 < 850]
    large = [d for d in digits if d.size >= 15]
    if large:
        return sorted(large, key=lambda s: (s.y0, -s.x0))
    return sorted([d for d in digits if d.text.strip() in FULLWIDTH], key=lambda s: (s.y0, -s.x0))


def _vlines(page: fitz.Page) -> list[tuple[float, float, float]]:
    """Vertical rules as (x, y0, y1), short collinear segments merged."""
    segs = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                if abs(p1.x - p2.x) < 1.5 and abs(p1.y - p2.y) > 1:
                    segs.append(((p1.x + p2.x) / 2, min(p1.y, p2.y), max(p1.y, p2.y)))
            elif it[0] == "re":
                r = it[1]
                if r.height > 1 and r.width < 5:
                    segs.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                elif r.height > 15 and r.width > 5:
                    segs.append((r.x0, r.y0, r.y1))
                    segs.append((r.x1, r.y0, r.y1))
    segs.sort(key=lambda t: (round(t[0]), t[1]))
    merged: list[list[float]] = []
    for x, y0, y1 in segs:
        if merged and abs(merged[-1][0] - x) <= 1 and y0 <= merged[-1][2] + 6:
            merged[-1][2] = max(merged[-1][2], y1)
            merged[-1][1] = min(merged[-1][1], y0)
        else:
            merged.append([x, y0, y1])
    return [(x, y0, y1) for x, y0, y1 in merged if y1 - y0 > 8]


def _snap(x: float, y: float, vlines, tol: float = 8.0) -> float | None:
    cands = [vx for (vx, y0, y1) in vlines if y0 - 4 <= y <= y1 + 4 and abs(vx - x) <= tol]
    return min(cands, key=lambda vx: abs(vx - x)) if cands else None


def _cell_bounds(labels, x_left: float, x_right: float, vlines) -> tuple[list[tuple[float, float]], float]:
    """(left, right) x-bounds per column label (labels sorted right-to-left) and the narrow cell width w."""
    n = len(labels)
    if n == 0:
        return [], 28.0
    xs = [l.cx for l in labels]
    gaps = [xs[i] - xs[i + 1] for i in range(n - 1)]
    normal = sorted(g for g in gaps if g < 60) or [28.0]
    w = normal[len(normal) // 2]
    wide = [g > 1.6 * w for g in gaps]
    y_row = labels[0].y1 + 12
    rights = []
    for i in range(n):
        if i == 0:
            rights.append(x_right)
            continue
        if not wide[i - 1]:
            mid = (xs[i - 1] + xs[i]) / 2
            rights.append(_snap(mid, y_row, vlines) or mid)
            continue
        right_label_wide = (i - 2 >= 0 and wide[i - 2])
        me_wide = (i < n - 1 and wide[i])
        cand_a = xs[i - 1] - w / 2
        cand_b = xs[i] + w / 2
        if me_wide and not right_label_wide:
            rights.append(_snap(cand_a, y_row, vlines) or cand_a)
        elif right_label_wide and not me_wide:
            rights.append(_snap(cand_b, y_row, vlines) or cand_b)
        else:
            sa, sb = _snap(cand_a, y_row, vlines), _snap(cand_b, y_row, vlines)
            rights.append(sa if sa is not None else (sb if sb is not None else cand_a))
    lefts = [rights[i + 1] if i + 1 < n else None for i in range(n)]
    last = labels[-1]
    if n >= 2 and wide[-1] and not (n >= 3 and wide[-2]):
        lefts[-1] = x_left
    else:
        lefts[-1] = _snap(last.cx - w / 2, y_row, vlines) or max(x_left, last.cx - w / 2)
    return [(lefts[i], rights[i]) for i in range(n)], w


def _cell_bottom(x: float, y_from: float, y_max: float, hlines) -> float:
    below = [y for (y, x0, x1) in hlines if x0 - 2 <= x <= x1 + 2 and y > y_from + 6]
    return min(below) if below else y_max


def _table(spans: list[Span], page: fitz.Page, footer_y: float) -> list[dict]:
    """Per 大問: region + cells [{no, x0, x1, y0, y1, wide, width, parts:[{text,x0,x1,y0,y1}]}]."""
    hl = _hlines(page)
    vl = _vlines(page)
    bigs = _bigs(spans)
    out = []
    for b in bigs:
        same_row = [o for o in bigs if abs(o.y0 - b.y0) < 25 and o is not b]
        left_neighbors = [o.x0 for o in same_row if o.x0 < b.x0]
        x_left = max(left_neighbors) + 30 if left_neighbors else 30
        x_right = b.x0 - 2
        below = [o.y0 for o in bigs if o.y0 > b.y0 + 25]
        y_top = b.y0 - 12
        y_bot = min(below) - 12 if below else footer_y
        labels = [s for s in _digit_spans(spans) if s is not b and s.size < 15
                  and x_left <= s.x0 < x_right and abs(s.cy - b.cy) < 22]
        labels.sort(key=lambda s: -s.x0)
        bounds, w = _cell_bounds(labels, x_left, x_right, vl)
        cells = []
        for lab, (x0, x1) in zip(labels, bounds):
            wide = (x1 - x0) > 1.6 * w
            y0 = lab.y1
            y1 = y_bot if wide else _cell_bottom((x0 + x1) / 2, y0, y_bot, hl)
            parts = [s for s in spans if s.text.strip() in PART_WORDS and s.size < 12
                     and x0 - 2 <= s.cx <= x1 + 2 and y0 - 2 <= s.y0 <= y1]
            side_by_side = len({round(p.x0 / 15) for p in parts}) > 1
            parts.sort(key=lambda s: ((-s.x0) if side_by_side else 0, s.y0))
            cells.append({"no": int(nfkc(lab.text)), "x0": x0, "x1": x1, "y0": y0, "y1": y1, "wide": wide,
                          "width": max(1, round((x1 - x0) / w)) if w else 1,
                          "parts": [{"text": nfkc(p.text.strip()), "x0": p.x0, "x1": p.x1, "y0": p.y0, "y1": p.y1} for p in parts]})
        out.append({"no": int(nfkc(b.text)), "x0": x_left, "x1": x_right, "y0": y_top, "y1": y_bot, "cells": cells})
    return out


def _footer(spans: list[Span], page_h: float) -> float:
    return min([s.y0 for s in spans if "シール" in s.text or ("受" in s.text and "番" in s.text)] or [page_h - 80]) - 5


def slots_from_sheet(sheet: fitz.Document) -> list[dict]:
    spans = _spans(sheet)
    table = _table(spans, sheet[0], _footer(spans, sheet[0].rect.height))
    slots = []
    for reg in table:
        for c in reg["cells"]:
            parts = [p["text"] for p in c["parts"]] or None
            frame = [s for s in spans if 10 <= s.size < 15 and c["x0"] <= s.cx < c["x1"]
                     and c["y0"] < s.y0 <= c["y1"] and s.text.strip() not in PART_WORDS]
            frame_text = "".join(s.text for s in sorted(frame, key=lambda s: (-round(s.x0 / 6), s.y0))).strip()
            slots.append({
                "id": f"{reg['no']}-{c['no']}", "big": reg["no"], "path": [str(c["no"])], "label": f"問{c['no']}",
                "unit": "", "parts": parts, "part_units": None,
                "frame": frame_text or None, "width": c["width"],
                "answer_type": None, "answer": None, "confidence": "none", "raw_values": [],
            })
    return slots


# ------------------------------------------------------------------ answers

def _classify(t: str, width: int) -> str:
    n = nfkc(t)
    if re.fullmatch(r"[A-Zア-ン]", n):
        return "choice"
    if re.fullmatch(r"[A-Zア-ン]{2,4}", n):
        return "set"
    if len(n) >= 12 or width >= 3:
        return "essay"
    return "text"


def _join_vertical(spans: list[Span]) -> str:
    cols: dict[int, list[Span]] = {}
    for s in spans:
        cols.setdefault(round(s.cx / 10), []).append(s)
    out = []
    for k in sorted(cols, reverse=True):
        for s in sorted(cols[k], key=lambda s: s.y0):
            out.append(s.text.strip())
    return unicodedata.normalize("NFKC", "".join(out)).replace(" ", "")


def _split_parts(cell: dict, chars: list[Span]) -> list[list[Span]]:
    parts = cell["parts"]
    if len(parts) < 2:
        return [chars]
    groups: list[list[Span]] = [[] for _ in parts]
    if len({round(p["x0"] / 15) for p in parts}) > 1:   # side by side (Ⅰ/Ⅱ, A/B), parts sorted right-to-left
        centers = [(p["x0"] + p["x1"]) / 2 for p in parts]
        for ch in chars:
            idx = 0
            for i in range(1, len(centers)):
                if ch.cx < (centers[i - 1] + centers[i]) / 2:
                    idx = i
            groups[idx].append(ch)
    else:                                                # stacked (はじめ / 終わり): label sits above its chars
        tops = [p["y0"] for p in parts]
        for ch in chars:
            idx = 0
            for i in range(1, len(tops)):
                if ch.y0 >= tops[i] - 2:
                    idx = i
            groups[idx].append(ch)
    return groups


def extract_answers(sheet: fitz.Document, model: fitz.Document, slots: list[dict]) -> None:
    page = model[0]
    words = _spans(model)
    chars_all = _char_spans(page)
    footer = _footer(words, page.rect.height)
    table = _table(words, page, footer)
    by_id = {s["id"]: s for s in slots}
    for reg in table:
        chars = [s for s in chars_all if s.size >= 16 and reg["x0"] - 5 <= s.cx < reg["x1"] + 5
                 and reg["y0"] <= s.y0 <= reg["y1"] and s.text.strip() not in PART_WORDS]
        narrow = [c for c in reg["cells"] if not c["wide"]]
        wide = [c for c in reg["cells"] if c["wide"]]
        assigned: dict[int, list[Span]] = {c["no"]: [] for c in reg["cells"]}
        rest = []
        for ch in chars:
            hit = next((c for c in narrow if c["x0"] - 3 <= ch.cx < c["x1"] + 3 and c["y0"] - 4 <= ch.y0 <= c["y1"] + 4), None)
            (assigned[hit["no"]] if hit else rest).append(ch)
        for ch in rest:
            hit = next((c for c in wide if c["x0"] - 3 <= ch.cx < c["x1"] + 3), None)
            if hit is None and wide:
                hit = wide[0] if len(wide) == 1 else min(wide, key=lambda c: min(abs(ch.cx - c["x0"]), abs(ch.cx - c["x1"])))
            if hit:
                assigned[hit["no"]].append(ch)
        for c in reg["cells"]:
            slot = by_id.get(f"{reg['no']}-{c['no']}")
            if slot is None:
                continue
            mine = assigned[c["no"]]
            slot["raw_values"] = [f"{s.text}@({s.x0:.0f},{s.y0:.0f})" for s in mine]
            if not mine:
                slot["confidence"] = "none"
                continue
            sheet_parts = slot.get("parts") or []
            if len(sheet_parts) >= 2:
                if len(c["parts"]) == len(sheet_parts):
                    groups = _split_parts(c, mine)
                else:  # model lacks part labels: equal x-shares, right to left (best effort)
                    groups = [[] for _ in sheet_parts]
                    share = (c["x1"] - c["x0"]) / len(sheet_parts)
                    for ch in mine:
                        idx = min(len(sheet_parts) - 1, max(0, int((c["x1"] - ch.cx) // share)))
                        groups[idx].append(ch)
                answers = [_join_vertical(g) for g in groups]
                slot["answer"] = answers
                slot["answer_type"] = "multi"
                slot["confidence"] = "high" if all(answers) else "low"
                continue
            text = _join_vertical(mine)
            atype = _classify(text, slot.get("width", 1))
            slot["answer"] = list(text) if atype == "set" else text
            slot["answer_type"] = atype
            slot["confidence"] = "high"
