"""Generic 解答用紙 slot builder + 模範解答 answer extraction (science / social; math uses answer_key.py).

Slot id = "{big}-{key}-{key}..." following the label hierarchy (問N -> ⑴ -> ①/あ). Katakana / alpha
labels (ア, エ, AD, BC) become `parts` of their parent slot; so do multi-row description texts inside one
cell (日の出 / 日の入り). 完答 -> multi (all parts required).

Cell geometry comes from the table rules drawn on the sheet: a label owns the vertical extent between the
nearest horizontal lines above/below that cross its x. Children are labels inside that extent to the right.

Model answer modes:
  overlay   : model PDF keeps the sheet layout; answers are in fonts the blank sheet never uses (理科)
  retypeset : model PDF is rebuilt; labels re-detected by regex, answers = remaining spans with size >= 12 (社会)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz

from common import Span, iter_spans, nfkc
from labels import parse_label, is_big_digit, Label

ROW_TOL = 14
FOOTER_MARKERS = ("ここにシール", "受験番号", "受　験　番　号")
UNIT_LIKE = re.compile(r"^[\wぁ-んァ-ヶ一-龥・（）〔〕％%°℃／/\.\s:：→]{1,14}$")
ANNOTATIONS = {"完答", "順不同", "順不同・完答", "完答・順不同", "順不同完答", "(漢字)", "漢字", "(ひらがな)"}
CIRCLE_MARKS = {"〇", "○", "◯"}
RE_EMBEDDED_Q = re.compile(r"(問\s*(?:[1１][0-9０-９]|[0-9０-９]))")   # 問1..問19; "問８２番目" -> 問８ | ２番目


@dataclass
class Node:
    label: Label | None
    span: Span | None
    big: int
    children: list["Node"] = field(default_factory=list)
    parent: "Node | None" = None
    units: list[Span] = field(default_factory=list)
    extent: tuple[float, float] = (0.0, 0.0)
    part_texts: list[list[Span]] = field(default_factory=list)   # multi-row descriptions -> parts

    @property
    def path(self) -> list[str]:
        if self.label is None:
            return [str(self.big)]
        return (self.parent.path if self.parent else [str(self.big)]) + [self.label.key]

    @property
    def id(self) -> str:
        return "-".join(self.path)

    @property
    def display(self) -> str:
        if self.label is None:
            return ""
        return (self.parent.display if self.parent else "") + self.label.text


# ------------------------------------------------------------------ spans / geometry

RE_LEADING_MARK = re.compile(r"^([⑴-⒇①-⑳]|[（(]\s*[0-9０-９]{1,2}\s*[）)])(\s*\S.*)$")


def _split_embedded(s: Span) -> list[Span]:
    """'時間問２' -> ['時間', '問２']; '⑴　→　→　→' -> ['⑴', '→　→　→'] with approximate x positions."""
    m = RE_LEADING_MARK.match(s.text)
    if m and m.group(2).strip():
        parts = [m.group(1), m.group(2)]
    else:
        parts = [p for p in RE_EMBEDDED_Q.split(s.text) if p]
    if len(parts) <= 1:
        return [s]
    out, x, total = [], s.x0, max(len(s.text), 1)
    w = (s.x1 - s.x0) / total
    for p in parts:
        out.append(Span(s.page, x, s.y0, x + w * len(p), s.y1, s.size, s.font, p))
        x += w * len(p)
    return out


def _spans_page0(doc: fitz.Document) -> list[Span]:
    seen, out = set(), []
    for s in iter_spans(doc):
        if s.page != 0:
            continue
        for p in _split_embedded(s):
            k = (round(p.x0), round(p.y0), p.text)
            if k in seen:
                continue
            seen.add(k)
            out.append(p)
    return out


def _hlines(page: fitz.Page) -> list[tuple[float, float, float]]:
    """Horizontal rules as (y, x0, x1). Short collinear segments (dashed borders) are merged."""
    segs: list[tuple[float, float, float]] = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                if abs(p1.y - p2.y) < 1.5 and abs(p1.x - p2.x) > 1:
                    segs.append(((p1.y + p2.y) / 2, min(p1.x, p2.x), max(p1.x, p2.x)))
            elif it[0] == "re":
                r = it[1]
                if r.width > 1 and r.height < 5:      # rules drawn as thin filled rectangles (0-3pt)
                    segs.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
                elif r.width > 15 and r.height > 5:
                    segs.append((r.y0, r.x0, r.x1))
                    segs.append((r.y1, r.x0, r.x1))
    # merge: same y (±1) and overlapping / nearly touching x-ranges
    segs.sort(key=lambda s: (round(s[0]), s[1]))
    merged: list[list[float]] = []
    for y, x0, x1 in segs:
        if merged and abs(merged[-1][0] - y) <= 1 and x0 <= merged[-1][2] + 6:
            merged[-1][2] = max(merged[-1][2], x1)
            merged[-1][1] = min(merged[-1][1], x0)
        else:
            merged.append([y, x0, x1])
    return [(y, x0, x1) for y, x0, x1 in merged if x1 - x0 > 15]


def _strip_leading(s: Span) -> Span:
    """'　　　B' -> 'B' with x0 moved to the glyph (needed for scanned-sheet overlays)."""
    stripped = s.text.lstrip(" \u3000")
    if stripped == s.text or not s.text:
        return s
    per = (s.x1 - s.x0) / max(len(s.text), 1)
    return Span(s.page, s.x0 + per * (len(s.text) - len(stripped)), s.y0, s.x1, s.y1, s.size, s.font, stripped)


def _footer_y(spans: list[Span], default: float) -> float:
    ys = [s.y0 for s in spans if any(m in s.text for m in FOOTER_MARKERS)]
    return min(ys) - 5 if ys else default


def big_regions(spans: list[Span], page_h: float, page_w: float, min_size: float = 15.0) -> list[dict]:
    bigs = [s for s in spans if s.size >= min_size and is_big_digit(s.text) is not None]
    footer = _footer_y(spans, page_h - 60)
    bigs = [s for s in bigs if s.y0 < footer]
    regions = []
    for b in bigs:
        same_col = [o for o in bigs if abs(o.x0 - b.x0) < 60 and o.y0 > b.y0 + 5]
        y1 = min(o.y0 for o in same_col) - 4 if same_col else footer
        right_cols = [o for o in bigs if o.x0 > b.x0 + 100]
        x1 = min(o.x0 for o in right_cols) - 4 if right_cols else page_w
        regions.append({"no": is_big_digit(b.text), "x0": b.x0 - 2, "y0": b.y0 - 6, "x1": x1, "y1": y1, "span": b})
    regions.sort(key=lambda r: r["no"])
    return regions


def _cell_extent(s: Span, hlines, region: dict) -> tuple[float, float]:
    cx = s.cx
    above = [y for (y, x0, x1) in hlines if x0 - 2 <= cx <= x1 + 2 and y <= s.cy - 2]
    below = [y for (y, x0, x1) in hlines if x0 - 2 <= cx <= x1 + 2 and y >= s.cy + 2]
    top = max(above) if above else region["y0"]
    bot = min(below) if below else region["y1"]
    return (top, bot)


# ------------------------------------------------------------------ tree

def build_tree(spans: list[Span], region: dict, hlines, label_ok=None) -> Node:
    """label_ok(span) -> bool lets the caller reject answer spans that look like labels (kana answers)."""
    root = Node(None, region["span"], region["no"], extent=(region["y0"], region["y1"]))
    inside = [s for s in spans if region["x0"] <= s.x0 < region["x1"] and region["y0"] <= s.y0 < region["y1"]
              and s is not region["span"]]
    labeled: list[Node] = []
    for s in inside:
        lab = parse_label(s.text)
        if lab and len(s.text.strip()) <= 4 and (label_ok is None or label_ok(s)):
            n = Node(lab, s, region["no"])
            n.extent = _cell_extent(s, hlines, region) if hlines else (s.cy - 30, s.cy + 30)
            labeled.append(n)
    # parent = deepest (largest x) lower-rank label whose cell extent contains the child's centre
    for n in labeled:
        cands = [p for p in labeled if p.label.rank < n.label.rank and p.span.x0 < n.span.x0 - 2
                 and p.extent[0] - 2 <= n.span.cy <= p.extent[1] + 2]
        if not cands:  # fallback: nearest by dy
            cands = [p for p in labeled if p.label.rank < n.label.rank and p.span.x0 < n.span.x0 - 2
                     and abs(p.span.cy - n.span.cy) < 60]
            par = min(cands, key=lambda p: (round(abs(p.span.cy - n.span.cy) / 12), -p.span.x0)) if cands else None
        else:
            par = max(cands, key=lambda p: p.span.x0)
        n.parent = par
        (par.children if par else root.children).append(n)
    label_spans = {id(n.span) for n in labeled}
    # unit / description texts inside a label's cell, right of the label, before the next label on that row
    for n in labeled:
        rows: dict[int, list[Span]] = {}
        for s in inside:
            if id(s) in label_spans or s.x0 <= n.span.x0 or is_big_digit(s.text) is not None and s.size >= 15:
                continue
            if label_ok is not None and not label_ok(s):  # on a model page: answers are not descriptions
                continue
            if not (n.extent[0] - 2 <= s.cy <= n.extent[1] + 2):
                continue
            if nfkc(s.text) in ANNOTATIONS or not UNIT_LIKE.match(s.text):
                continue
            nxt = [m for m in labeled if abs(m.span.cy - s.cy) < ROW_TOL and n.span.x0 < m.span.x0 <= s.x0]
            if nxt:  # belongs to a deeper label on that row
                continue
            rows.setdefault(round(s.cy / 10), []).append(s)
        ordered = [sorted(v, key=lambda s: s.x0) for _, v in sorted(rows.items())]
        same_row = [r for r in ordered if abs(r[0].cy - n.span.cy) < ROW_TOL]
        n.units = same_row[0] if same_row else []
        if len(ordered) >= 2 and not n.children:
            n.part_texts = ordered

    def sort_rec(node: Node) -> None:
        node.children.sort(key=lambda c: (round(c.span.cy / 10), c.span.x0))
        for c in node.children:
            sort_rec(c)
    sort_rec(root)
    return root


def leaves(node: Node) -> list[Node]:
    if not node.children:
        return [node] if node.label is not None else []
    if all(c.label.rank == 4 for c in node.children):
        return [node]
    out = []
    for c in node.children:
        out.extend(leaves(c))
    return out


def _all_nodes(node: Node) -> list[Node]:
    out = [node] if node.label else []
    for c in node.children:
        out.extend(_all_nodes(c))
    return out


def slots_from_sheet(sheet: fitz.Document) -> list[dict]:
    spans = _spans_page0(sheet)
    page = sheet[0]
    hl = _hlines(page)
    out = []
    for reg in big_regions(spans, page.rect.height, page.rect.width):
        root = build_tree(spans, reg, hl)
        for leaf in leaves(root):
            if leaf.children:
                parts = [c.label.text for c in leaf.children]
                part_units = [" ".join(nfkc(u.text) for u in c.units) for c in leaf.children]
            elif leaf.part_texts:
                parts = [" ".join(nfkc(s.text) for s in row) for row in leaf.part_texts]
                part_units = None
            else:
                parts, part_units = None, None
            unit = "" if leaf.part_texts else " ".join(nfkc(u.text) for u in leaf.units).strip()
            out.append({
                "id": leaf.id, "big": leaf.big, "path": leaf.path[1:], "label": leaf.display,
                "unit": unit, "parts": parts, "part_units": part_units,
                "answer_type": None, "answer": None, "confidence": "none", "raw_values": [],
            })
    return out


# ------------------------------------------------------------------ answers

def _detect_mode(sheet_spans: list[Span], model_spans: list[Span]) -> str:
    sheet_fonts = {s.font for s in sheet_spans}
    labels_sheet = [s for s in sheet_spans if parse_label(s.text) and len(s.text.strip()) <= 4]
    labels_model = [s for s in model_spans if parse_label(s.text) and len(s.text.strip()) <= 4]
    if len(labels_model) < 0.3 * max(len(labels_sheet), 1):
        return "sheet-tree"      # scanned sheet with typed answers on top: no label text in the model
    same_font = sum(1 for s in labels_model if s.font in sheet_fonts)
    return "overlay" if labels_model and same_font / len(labels_model) > 0.7 else "retypeset"


def _circled_choice(page: fitz.Page, leaf: Node, opts: list[Span]) -> str | None:
    """正 ・ 誤 style: find a small closed drawing (circle) around one of the option words."""
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if not (8 < r.width < 45 and 8 < r.height < 45):
            continue
        for o in opts:
            if r.contains(fitz.Point(o.cx, o.cy)) or abs(r.x0 + r.width / 2 - o.cx) < 8 and abs(r.y0 + r.height / 2 - o.cy) < 10:
                return nfkc(o.text)
    return None


def extract_answers(sheet: fitz.Document, model: fitz.Document, slots: list[dict]) -> str:
    sheet_spans = _spans_page0(sheet)
    model_spans = _spans_page0(model)
    mode = _detect_mode(sheet_spans, model_spans)
    page = model[0]
    sheet_fonts = {s.font for s in sheet_spans}
    squash = lambda t: re.sub(r"\s+", "", nfkc(t))
    sheet_texts = {squash(s.text) for s in sheet_spans if len(squash(s.text)) >= 2}
    tree_spans = sheet_spans if mode == "sheet-tree" else model_spans
    tree_page = sheet[0] if mode == "sheet-tree" else page
    hl = _hlines(tree_page)
    regions = big_regions(tree_spans, page.rect.height, page.rect.width, min_size=15.0)
    if len(regions) < len({s["big"] for s in slots}):
        regions = big_regions(tree_spans, page.rect.height, page.rect.width, min_size=12.0)
    by_id = {s["id"]: s for s in slots}
    if mode == "overlay":
        label_ok = lambda s: s.font in sheet_fonts            # answers use other fonts
    elif mode == "retypeset":
        label_ok = lambda s: s.size < 12                      # labels are small, answers >= 12
    else:
        label_ok = None
    header_y = min([s.y0 for s in model_spans if "解答用紙" in s.text] or [0]) + 20
    for reg in regions:
        root = build_tree(tree_spans, reg, hl, label_ok)
        model_leaves = leaves(root)
        label_ids = {id(n.span) for n in _all_nodes(root)}
        inside = [s for s in model_spans if reg["x0"] <= s.x0 < reg["x1"] and reg["y0"] <= s.y0 < reg["y1"]
                  and id(s) not in label_ids and s is not reg["span"] and squash(s.text) not in ANNOTATIONS
                  and s.y0 > header_y]
        if mode == "overlay":
            values = [s for s in inside if s.font not in sheet_fonts]
        elif mode == "retypeset":
            values = [s for s in inside if s.size >= 10.5 and squash(s.text) not in sheet_texts]
        else:
            values = [_strip_leading(s) for s in inside if squash(s.text)]
        for leaf in model_leaves:
            slot = by_id.get(leaf.id)
            if slot is None:
                continue
            vals = _values_for(leaf, values, model_leaves)
            marks = [v for _, v in vals if squash(v.text) in CIRCLE_MARKS]
            if marks and "・" in (slot.get("unit") or ""):
                opt_spans = _split_options(leaf.units)
                if opt_spans:
                    pick = min(opt_spans, key=lambda o: abs(o.cx - marks[0].cx))
                    slot["answer"], slot["answer_type"], slot["confidence"] = nfkc(pick.text), "choice", "high"
                    slot["options"] = [nfkc(o.text) for o in opt_spans]
                    slot["raw_values"] = [f"{v.text}@({v.x0:.0f},{v.y0:.0f})" for _, v in vals]
                    continue
            _fill(slot, leaf, vals)
            unit_opts = re.sub(r"\s+", "", slot.get("unit") or "")
            if slot["answer_type"] == "text" and re.sub(r"\s+", "", str(slot["answer"])) == unit_opts and "・" in unit_opts:
                slot["confidence"] = "none"   # captured the option words themselves; look for the circle
            if slot["confidence"] == "none" and "・" in (slot.get("unit") or ""):
                opts = [u for u in leaf.units if nfkc(u.text) not in ("・",)]
                opts = [Span(0, u.x0, u.y0, u.x1, u.y1, u.size, u.font, t) for u in leaf.units for t in [u.text]
                        if t.strip() not in ("・",)]
                # unit words may be one span "正 ・ 誤": split into option words by position
                opt_spans = _split_options(leaf.units)
                pick = _circled_choice(page, leaf, opt_spans)
                if pick:
                    slot["answer"], slot["answer_type"], slot["confidence"] = pick, "choice", "high"
                    slot["options"] = [nfkc(o.text) for o in opt_spans]
    return mode


def _split_options(units: list[Span]) -> list[Span]:
    out = []
    for u in units:
        toks = [t for t in re.split(r"[\s・]+", u.text) if t]
        if len(toks) <= 1:
            out.append(u)
            continue
        n = max(len(u.text), 1)
        w = (u.x1 - u.x0) / n
        pos = 0
        for t in toks:
            i = u.text.find(t, pos)
            x0 = u.x0 + w * i
            out.append(Span(u.page, x0, u.y0, x0 + w * len(t), u.y1, u.size, u.font, t))
            pos = i + len(t)
    return out


def _anchors(leaf: Node) -> list[tuple[Span, float]]:
    """(anchor span, row centre) list: part labels, or part-text rows, or the leaf label itself."""
    if leaf.children:
        return [(c.span, c.span.cy) for c in leaf.children]
    if leaf.part_texts:
        return [(row[0], row[0].cy) for row in leaf.part_texts]
    return [(leaf.span, leaf.span.cy)]


def _values_for(leaf: Node, values: list[Span], all_leaves: list[Node]) -> list[tuple[int, Span]]:
    """Values inside this leaf's cell extent, grouped by anchor index (part) when the leaf has parts."""
    picked = []
    for v in values:
        # candidate leaves: cell extent contains value centre and label is to the left
        cands = [l for l in all_leaves if l.span.x0 < v.x0 + 2 and l.extent[0] - 2 <= v.cy <= l.extent[1] + 2]
        if not cands:
            continue
        best = max(cands, key=lambda l: l.span.x0)
        if best is not leaf:
            continue
        anc = _anchors(leaf)
        if len(anc) == 1:
            picked.append((0, v))
        else:
            same_row = [i for i in range(len(anc)) if abs(anc[i][1] - v.cy) < 10 and anc[i][0].x0 <= v.x0 + 2]
            if same_row:  # part labels side by side on one row (ア ... エ ...): nearest label to the left
                idx = max(same_row, key=lambda i: anc[i][0].x0)
            else:         # parts stacked in rows: nearest row
                idx = min(range(len(anc)), key=lambda i: abs(anc[i][1] - v.cy))
            picked.append((idx, v))
    picked.sort(key=lambda t: (t[0], round(t[1].cy / 8), t[1].x0))
    return picked


RE_ALT = re.compile(r"[（(]\s*(.+?)\s*(?:も可|でも可|も正解|も良い)\s*[）)]")
RE_PAREN_ALT = re.compile(r"^(.+?)\s*[（(]([^（()）]+)[）)]$")


def _clean_text(t: str) -> tuple[str, list[str]]:
    t = nfkc(t).strip()
    variants: list[str] = []
    m = RE_ALT.search(t)
    if m:
        variants.append(m.group(1).strip())
        t = RE_ALT.sub("", t).strip()
    m = RE_PAREN_ALT.match(t)
    if m:  # 凝縮(ぎょうしゅく) / 麦芽糖(マルトース) / 平等院(5位 平等院) -> main + alternative form
        t, alt = m.group(1).strip(), m.group(2).strip()
        variants.append(alt)
    t = re.sub(r"(?<=[\d.])\s+(?=[\d.])", "", t)   # digits typed with spaces -> 50
    return t, variants


def _classify(t: str) -> str:
    n = nfkc(t)
    if "→" in n or "->" in n:
        return "sequence"
    if re.fullmatch(r"[A-Zア-ンあ-ん正誤○×]", n):
        return "choice"
    if re.fullmatch(r"[A-Zア-ン]([・,、][A-Zア-ン])+", n) or ("・" in n and " " not in n and len(n) <= 20):
        return "set"
    if re.fullmatch(r"-?\d+(\.\d+)?(/\d+)?", n):
        return "number"
    if len(n) >= 12 or n.endswith(("ため", "ため。", "から", "から。", "こと。", "こと")):
        return "essay"
    return "text"


def _join(vals: list[Span]) -> str:
    rows = {round(v.cy / 8) for v in vals}
    if len(rows) > 1 or len(vals) > 2:
        return "".join(v.text for v in vals)
    return " ".join(v.text for v in vals)


def _fill(slot: dict, leaf: Node, vals: list[tuple[int, Span]]) -> None:
    slot["raw_values"] = [f"{v.text}@({v.x0:.0f},{v.y0:.0f})" for _, v in vals]
    anchors = _anchors(leaf)
    if len(anchors) > 1:
        groups: dict[int, list[Span]] = {}
        for idx, v in vals:
            groups.setdefault(idx, []).append(v)
        answers = []
        for i in range(len(anchors)):
            g = sorted(groups.get(i, []), key=lambda s: (round(s.cy / 8), s.x0))
            answers.append(_clean_text(_join(g))[0] if g else "")
        slot["answer"] = answers
        slot["answer_type"] = "multi"
        slot["confidence"] = "high" if all(answers) else ("none" if not any(answers) else "low")
        return
    spans = [v for _, v in vals]
    if not spans:
        slot["confidence"] = "none"
        return
    # several single choice letters side by side in one cell (問1: A ⋮ E) -> ordered multi answer
    letters = [nfkc(s.text) for s in spans]
    if len(spans) >= 2 and all(re.fullmatch(r"[A-Zア-ンあ-ん]", t) for t in letters) \
            and len({round(s.cy / 8) for s in spans}) == 1:
        slot["answer"] = letters
        slot["answer_type"] = "multi"
        slot["parts"] = [str(i + 1) for i in range(len(letters))]
        slot["confidence"] = "high"
        return
    text, variants = _clean_text(_join(spans))
    if not re.search(r"[A-Za-z0-9]\s+[A-Za-z0-9]", text):
        text = re.sub(r"\s+", "", text)
    atype = _classify(text)
    slot["answer"] = [p for p in re.split(r"[・,、]", text) if p] if atype == "set" else text
    slot["answer_type"] = atype
    slot["variants"] = variants
    one_row = len({round(v.cy / 8) for v in spans}) == 1
    slot["confidence"] = "high" if (len(spans) == 1 or atype == "essay" or variants or (one_row and len(text) <= 10)) else "low"
