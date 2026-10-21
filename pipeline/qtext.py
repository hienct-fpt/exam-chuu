"""Step 4b: question crops that are plain text -> HTML text, so the app shows text instead of a PNG.

Only 算数・理科・社会 crops with a text layer and nothing drawn (no figure / table / fraction / raster) are converted
("group A" of the image audit). Everything else keeps its PNG. The markup is the same for every question:
  <ruby>  furigana (small text just above a line)       <b>    bold / gothic emphasis inside 明朝 text
  <em class="kt">  傍点 (KentenGeneric dots)              <sup>  small raised text (cm 2 -> cm<sup>2</sup>)
  <u>     text with a short rule right under it          <span class="qbox">   framed word (［A］, ア〜エ)
  <span class="qbox blank"></span>  empty frame on a line  <div class="qframe">  framed paragraph (資料文)
  <span class="maru">  circled letter (あ drawn on top of ○)
Lines that run to the right edge are joined; other breaks stay as "\n" (shown with white-space: pre-wrap).

Output: out/qtext/{exam_id}.json  {"q/{exam_id}/q2-3.png": "<html>"}   (build.py ships the map as bank["texts"])
Manual: pipeline/overrides/qtext.json {"keep_image": ["q/{exam_id}/q2-3.png", ...]} forces the PNG.
"""
from __future__ import annotations

import html
import re
import unicodedata
from collections import Counter

import fitz

from common import OUT, ROOT, load_json, dump_json
from render import LEFT, RIGHT_MARGIN, node_name

SUBJECTS = {"math", "science", "social"}
OVERRIDES = ROOT / "pipeline" / "overrides" / "qtext.json"
# fonts whose glyphs are private symbols mapped onto random kanji (組分け: 唄 = ⑴, 欝 = ⑵, 安 = ㎤ ...)
SYMBOL_FONTS = ("Fx-", "TT784C9A13")
KENTEN_FONT = "KentenGeneric"
BOLD_RE = re.compile(r"Bold|Goth|GoB|Heavy|Demi", re.I)
JP_RE = re.compile(r"[぀-ヿ一-鿿０-ｚ]")
KANA_RE = re.compile(r"[぀-ヿ]+")
KANJI_RE = re.compile(r"[一-鿿々]")
# a line opening a paragraph / list entry is never joined to the line before (　段落, ア．, (1), ①, ⑴, 問3)
ITEM_START_RE = re.compile(
    r"[ア-ンＡ-Ｚ][．.：:　 ]|[あ-ん][．.]"                          # ア．  Ａ：  あ．  (not 選|び、)
    r"|[（(〔［\[【〈<＜][ア-ンｦ-ﾝあ-んＡ-Ｚａ-ｚA-Za-z0-9０-９ⅠⅡⅢⅣⅤ一-九]{1,3}[）)〕］\]】〉>＞]"  # （イ） (ｱ) [A]
    r"|[〔［【][^〕］】]{1,6}[〕］】]"                                     # 〔問１〕 【資料】
    r"|[①-⑳⑴-⒇㋐-㋾ⒶⒷⒸⒹⒺⒻⓐ-ⓩⅠⅡⅢⅣⅤ]"                                  # ① ⑴ ㋐ Ⅰ
    r"|問\s*[0-9０-９]|[0-9０-９]{1,2}[．.)）](?![0-9０-９])"              # 問3  1．  (not 8.9％)
    r"|[・●○■□◆◇※＊★☆▼▽]"                                               # bullets / notes
)


# ---------------------------------------------------------------- crop regions (same naming as render.py)
def crop_regions(seg: dict) -> dict[str, list[dict]]:
    """{"q2-3": [regions]} for every crop render.py writes (page_regions -> q{n}-p{i})."""
    out: dict[str, list[dict]] = {}

    def walk(big_no: int, path: list[str], node: dict) -> None:
        name = node_name(big_no, path)
        if node.get("page_regions"):
            for i, r in enumerate(node["page_regions"], 1):
                out[f"{name}-p{i}"] = r if isinstance(r, list) else [r]
            return
        if node.get("regions"):
            out[name] = node["regions"]
        if node.get("stem") and node.get("subs"):
            st = node["stem"]
            out[f"{name}_stem"] = st if isinstance(st, list) else [st]
        for s in node.get("subs", []):
            walk(big_no, path + [s["key"]], s)

    for b in seg["bigs"]:
        walk(b["no"], [], b)
    return out


def node_labels(seg: dict) -> dict[str, str]:
    """{"q2-3": "(3)"} -> replaces a private-font marker glyph at the start of the crop."""
    out: dict[str, str] = {}

    def walk(big_no: int, path: list[str], node: dict) -> None:
        out[node_name(big_no, path)] = node.get("label", "")
        for s in node.get("subs", []):
            walk(big_no, path + [s["key"]], s)

    for b in seg["bigs"]:
        walk(b["no"], [], b)
    return out


def clip_of(page: fitz.Page, r: dict) -> fitz.Rect:
    return fitz.Rect(r.get("x0", LEFT), r["y0"], r.get("x1", page.rect.width - RIGHT_MARGIN), r["y1"])


# ---------------------------------------------------------------- per-page caches (one page holds many crops)
def _page_cache(page: fitz.Page) -> dict:
    doc = page.parent
    if not hasattr(doc, "_qtext_cache"):
        doc._qtext_cache = {}
    return doc._qtext_cache.setdefault(page.number, {})


def _drawings(page: fitz.Page) -> list[dict]:
    c = _page_cache(page)
    if "dr" not in c:
        c["dr"] = page.get_drawings()
    return c["dr"]


def _page_chars(page: fitz.Page) -> list[tuple[dict, dict, bool]]:
    """(char, span, horizontal) for every char on the page."""
    c = _page_cache(page)
    if "ch" not in c:
        out = []
        for b in page.get_text("rawdict")["blocks"]:
            for ln in b.get("lines", []):
                horiz = abs(ln["dir"][0]) >= 0.5
                for sp in ln["spans"]:
                    for ch in sp["chars"]:
                        out.append((ch, sp, horiz))
        c["ch"] = out
    return c["ch"]


def _in_clip(ch: dict, clip: fitz.Rect) -> bool:
    x0, y0, x1, y1 = ch["bbox"]
    return clip.x0 <= (x0 + x1) / 2 <= clip.x1 and clip.y0 <= (y0 + y1) / 2 <= clip.y1


# ---------------------------------------------------------------- classification
def crop_stats(page: fitz.Page, clip: fitz.Rect) -> Counter:
    st: Counter = Counter()
    for ch, _, horiz in _page_chars(page):
        if ch["c"].strip() and _in_clip(ch, clip):
            st["chars"] += 1
            st["hchars" if horiz else "vchars"] += 1
    glyphs = [(fitz.Rect(c["bbox"]), c["c"]) for c in _raw_chars(page, clip) if c["c"].strip()]
    c = _page_cache(page)
    if "img" not in c:
        c["img"] = page.get_image_info()
    raster_area = 0.0  # summed: a photo may be stored as dozens of 5pt strips
    for img in c["img"]:
        bb = fitz.Rect(img["bbox"]) & clip
        if not bb.is_empty:
            raster_area += bb.get_area()
    st["raster"] += raster_area > 1500
    cx0, cy0, cx1, cy1 = clip
    inside = lambda pt: cx0 <= pt.x <= cx1 and cy0 <= pt.y <= cy1  # noqa: E731 (plain floats: map pages hold 10k+ paths)
    for dr in _drawings(page):
        x0, y0, x1, y1 = dr["rect"]
        if x1 < cx0 - 1 or x0 > cx1 + 1 or y1 < cy0 - 1 or y0 > cy1 + 1:  # a bare rule has a zero-height rect
            continue
        if not _could_be_plain(st):
            break  # already a figure, stop counting
        for it in dr["items"]:
            op = it[0]
            if op == "c":
                st["curves"] += 1
            elif op == "l":
                p1, p2 = it[1], it[2]
                if not (inside(p1) or inside(p2)):
                    continue
                dx, dy = abs(p1.x - p2.x), abs(p1.y - p2.y)
                if dx > 1 and dy > 1:
                    st["diag"] += 1
                elif dy <= 1 and dx > 3:
                    st["shortH" if dx < 30 else "axis"] += 1
                    st["frac"] += _is_fraction_bar(fitz.Rect(p1, p2).normalize(), glyphs)
                else:
                    st["axis"] += 1
            elif op == "re" and it[1].height < 1.5:  # a rule drawn as a thin filled rectangle
                st["shortH" if it[1].width < 30 else "axis"] += 1
                st["frac"] += _is_fraction_bar(it[1], glyphs)
            elif op in ("re", "qu"):
                st["rects"] += 1
    return st


def _could_be_plain(st: Counter) -> bool:
    # a slanted stroke is always a drawing (angle, arrow, graph); 4 curves = one rounded frame
    return st["curves"] <= 4 and st["diag"] == 0 and st["axis"] <= 4 and st["rects"] <= 2


def _raw_chars(page: fitz.Page, clip: fitz.Rect):
    return (ch for ch, _, _ in _page_chars(page) if _in_clip(ch, clip))


def _is_fraction_bar(bar: fitz.Rect, glyphs: list[tuple[fitz.Rect, str]]) -> bool:
    """A rule with only digits / letters right above and right below it: a stacked fraction (2/3, 1/100000000)
    or a 筆算. An underline has words (kana / kanji) above it."""
    def side(above):
        out = []
        for r, ch in glyphs:
            if bar.x0 - 1 <= (r.x0 + r.x1) / 2 <= bar.x1 + 1:
                gap = bar.y0 - r.y1 if above else r.y0 - bar.y1
                if -3 <= gap <= 6:
                    out.append(ch)
        return out
    up, down = side(True), side(False)
    def is_num(chs):
        norm = [unicodedata.normalize("NFKC", ch) for ch in chs]
        return bool(norm) and all(ch.isascii() and ch.isalnum() or ch in "+-−" for ch in norm)
    return is_num(up) and is_num(down)


def is_plain(st: Counter, text: str, subject: str) -> bool:
    """Group A: text layer, horizontal, nothing drawn beyond ≤2 frames / ≤4 rules, no math layout."""
    if subject not in SUBJECTS or st["chars"] < 5 or st["raster"]:
        return False
    if not _could_be_plain(st):
        return False
    if st["vchars"] > st["hchars"]:
        return False  # 縦書き
    if st["frac"] or subject == "math" and (st["shortH"] or re.search(r"[÷×]|\d\s+\d", text)):
        return False  # fractions / 計算式 need math markup (group B)
    return True


# ---------------------------------------------------------------- text -> html
def _chars(page: fitz.Page, clip: fitz.Rect) -> list[dict]:
    out = []
    for ch, sp, horiz in _page_chars(page):
        if not horiz or not _in_clip(ch, clip):
            continue
        bb = fitz.Rect(ch["bbox"])
        out.append({"c": ch["c"], "bb": bb, "cx": (bb.x0 + bb.x1) / 2, "cy": (bb.y0 + bb.y1) / 2, "size": sp["size"],
                    "font": sp["font"], "bold": bool(sp["flags"] & 16) or bool(BOLD_RE.search(sp["font"]))})
    return out


def _frames(page: fitz.Page, clip: fitz.Rect, unit: float) -> tuple[list[fitz.Rect], list[fitz.Rect]]:
    """(rectangles, horizontal rules) drawn inside the clip. Frames drawn as separate strokes (4 lines / 4 thin bars)
    are put back together, so their top and bottom never read as underlines."""
    rects, rules, sides = [], [], []
    for dr in _drawings(page):
        r = dr["rect"]
        if not (r + (-1, -1, 1, 1)).intersects(clip) or (r & clip).get_area() < 0.8 * r.get_area() and r.height > 1:
            continue
        ops = [it[0] for it in dr["items"]]
        if "re" in ops or "qu" in ops:
            for it in dr["items"]:
                if it[0] in ("re", "qu"):
                    rr = fitz.Rect(it[1] if it[0] == "re" else it[1].rect)
                    if rr.height < 1.5:
                        rules.append(rr)
                    elif rr.width < 1.5:
                        sides.append(rr)
                    else:
                        rects.append(rr)
        elif ops and all(o == "l" for o in ops) and len(ops) >= 3 and r.height > unit * 0.6 and r.width > 1.5:
            rects.append(fitz.Rect(r))
        else:
            for it in dr["items"]:
                if it[0] != "l":
                    continue
                seg = fitz.Rect(it[1], it[2]).normalize()
                if seg.height <= 1.5 and seg.width > unit * 0.5:
                    rules.append(seg)
                elif seg.width <= 1.5 and seg.height > 3:
                    sides.append(seg)

    def has_side(x, y0, y1):
        return any(abs(s.x0 - x) < 2.5 and s.y0 <= y0 + 2.5 and s.y1 >= y1 - 2.5 for s in sides)

    rules.sort(key=lambda r: r.y0)
    for top in list(rules):
        if top not in rules:
            continue
        bottom = next((b for b in rules if b is not top and abs(b.x0 - top.x0) < 2.5 and abs(b.x1 - top.x1) < 2.5
                       and b.y0 - top.y0 > unit * 0.6 and has_side(top.x0, top.y0, b.y1) and has_side(top.x1, top.y0, b.y1)),
                      None)
        if bottom is not None:
            rules.remove(top)
            rules.remove(bottom)
            rects.append(fitz.Rect(top.x0, top.y0, bottom.x1, bottom.y1))
    return rects, rules


def crop_html(doc: fitz.Document, regions: list[dict], label: str = "") -> str | None:
    """HTML for a text-only crop, or None when something can't be expressed (-> keep the PNG)."""
    out_parts = []
    first = True
    for r in regions:
        page = doc[r["page"]]
        clip = clip_of(page, r)
        part = _region_html(page, clip, label if first else "")
        if part is None:
            return None
        if part:
            out_parts.append(part)
            first = False
    text = "\n".join(out_parts).strip("\n")
    plain = re.sub(r"<rt>.*?</rt>|<[^>]+>", "", text)
    if not plain.strip() or "�" in plain or any(0xE000 <= ord(c) <= 0xF8FF for c in plain):
        return None
    if len(JP_RE.findall(plain)) < 0.3 * len(re.sub(r"\s", "", plain)):
        return None  # garbled text layer
    return text


def _region_html(page: fitz.Page, clip: fitz.Rect, label: str) -> str | None:
    chars = _chars(page, clip)
    if not chars:
        return ""
    sizes = Counter(round(c["size"], 1) for c in chars if c["font"] != KENTEN_FONT)
    main = sizes.most_common(1)[0][0] if sizes else 10.0
    body_fonts = Counter(c["font"] for c in chars if abs(c["size"] - main) < 0.5)
    body_font = body_fonts.most_common(1)[0][0]
    body_bold = bool(BOLD_RE.search(body_font))
    # circled letter set as a small glyph on top of ○ (下線部あ○) -> one circled char
    for ring in [c for c in chars if c["c"] in "○◯"]:
        inner = next((c for c in chars if c is not ring and c["size"] < ring["size"] * 0.8
                      and abs(c["cx"] - ring["cx"]) < main * 0.35 and abs(c["cy"] - ring["cy"]) < main * 0.35), None)
        if inner is not None:
            ring["c"], ring["maru"] = inner["c"], True
            chars.remove(inner)
    kenten = [c for c in chars if c["font"] == KENTEN_FONT]
    big = [c for c in chars if c["font"] != KENTEN_FONT and c["size"] >= main * 0.75]
    small = [c for c in chars if c["font"] != KENTEN_FONT and c["size"] < main * 0.75]

    # lines of body-size chars
    lines: list[dict] = []
    for c in sorted(big, key=lambda c: (c["cy"], c["cx"])):
        ln = next((l for l in lines if abs(l["cy"] - c["cy"]) < main * 0.45), None)
        if ln is None:
            ln = {"cy": c["cy"], "chars": []}
            lines.append(ln)
        ln["chars"].append(c)
    for ln in lines:
        ln["chars"].sort(key=lambda c: c["cx"])
        ln["y0"] = min(c["bb"].y0 for c in ln["chars"])
        ln["y1"] = max(c["bb"].y1 for c in ln["chars"])
        ln["x0"], ln["x1"] = ln["chars"][0]["bb"].x0, ln["chars"][-1]["bb"].x1
    lines = [ln for ln in sorted(lines, key=lambda l: l["cy"])
             if any(c["c"].strip() for c in ln["chars"]) and not _is_furniture(ln["chars"])]
    if not lines:
        return ""

    # small text: furigana above a line, else superscript / subscript inside a line, else dropped (cut-off ruby)
    rubies = []  # (line, x0, x1, text)
    runs: list[list[dict]] = []
    for c in sorted(small, key=lambda c: (round(c["cy"]), c["cx"])):
        if runs and abs(runs[-1][-1]["cy"] - c["cy"]) < 1 and c["bb"].x0 - runs[-1][-1]["bb"].x1 < c["size"] * 0.6:
            runs[-1].append(c)
        else:
            runs.append([c])
    for run in runs:
        x0, x1 = run[0]["bb"].x0, run[-1]["bb"].x1
        y0, y1 = min(c["bb"].y0 for c in run), max(c["bb"].y1 for c in run)
        txt = "".join(c["c"] for c in run)
        cy = (y0 + y1) / 2
        below = [l for l in lines if main * 0.35 < l["cy"] - cy < main * 1.3]
        inline = [l for l in lines if l["y0"] - 1 <= cy <= l["y1"] + 1]
        if below and KANA_RE.fullmatch(txt):
            rubies.append((below[0], x0, x1, txt))
        elif inline:
            ln = inline[0]
            tag = "sup" if (y0 + y1) / 2 < ln["cy"] else "sub"
            for c in run:
                c["wrap"] = tag
            ln["chars"].extend(run)
            ln["chars"].sort(key=lambda c: c["cx"])
        # else: furigana whose base line is outside the crop -> drop
    lines = [ln for ln in lines if not _is_furniture(ln["chars"])]  # the ━ of a page number bar can be small text
    if not lines:
        return ""
    if any(_has_figure_caption(ln["chars"], main) for ln in lines):
        return None  # a figure / table sits in (or reaches into) the crop

    for ln, x0, x1, txt in rubies:
        slack = main * 0.25
        base = [c for c in ln["chars"] if x0 - slack <= c["cx"] <= x1 + slack and not c.get("wrap")]
        while len(base) > 1 and not KANJI_RE.match(base[0]["c"]):  # 、米内光政 -> 米内光政
            base.pop(0)
        while len(base) > 1 and not KANJI_RE.match(base[-1]["c"]):
            base.pop()
        if not base:
            continue
        if any("ruby" in c for c in base):  # two ruby runs over one base: join them
            first = next(c for c in base if "ruby" in c)
            first["ruby"] += txt
            continue
        base[0]["ruby"], base[0]["ruby_len"] = txt, len(base)
    for k in kenten:
        for ln in lines:
            for c in ln["chars"]:
                if abs(c["cx"] - k["cx"]) < main * 0.5 and 0 <= c["bb"].y0 - k["cy"] < main:
                    c["kt"] = True

    rects, rules = _frames(page, clip, main)
    framed_lines: dict[int, int] = {}  # line index -> frame index (multi-line frames)
    for fi, rr in enumerate(rects):
        boxed = [c for ln in lines for c in ln["chars"] if rr.contains(fitz.Point(c["cx"], c["cy"]))]
        if rr.height > main * 2.6 and len(boxed) < 6:
            return None  # a tall, nearly empty frame: answer column (算数1教科 「秒」) or a figure frame
        inside = [i for i, ln in enumerate(lines) if rr.contains(fitz.Point(ln["chars"][0]["cx"], ln["cy"]))]
        if len(inside) >= 2 or (inside and rr.height > main * 2.2):
            for i in inside:
                framed_lines[i] = fi
            continue
        if rr.height > main * 2.6:
            return None  # a tall frame whose text doesn't open its lines: not a framed paragraph
        if boxed:
            for c in boxed:
                c["box"] = fi + 1  # 0 would read as "no box"
        elif rr.height < main * 2.2 and rr.width < clip.width * 0.6:
            ln = next((l for l in lines if l["y0"] - 2 <= (rr.y0 + rr.y1) / 2 <= l["y1"] + 2), None)
            if ln is not None:
                ln["chars"].append({"c": "", "blank": True, "bb": rr, "cx": (rr.x0 + rr.x1) / 2, "cy": ln["cy"],
                                    "size": main, "font": body_font, "bold": False})
                ln["chars"].sort(key=lambda c: c["cx"])
    for rl in rules:
        for ln in lines:
            for c in ln["chars"]:
                if rl.x0 - 1 <= c["cx"] <= rl.x1 + 1 and -1 <= rl.y0 - c["bb"].y1 <= main * 0.45:
                    c["u"] = True

    # private-font glyphs: a leading marker becomes the node label, anything else can't be read -> keep the PNG
    first_c = lines[0]["chars"][0]
    for ln in lines:
        for c in ln["chars"]:
            if c["font"].startswith(SYMBOL_FONTS):
                if c is first_c and label:
                    c["c"], c["font"] = label, body_font
                else:
                    return None

    # right edge per block (a framed quotation is narrower than the question text around it)
    right: dict[int | None, float] = {}
    for i, ln in enumerate(lines):
        fr = framed_lines.get(i)
        right[fr] = max(right.get(fr, 0), ln["x1"])
    left = Counter(round(ln["x0"]) for ln in lines).most_common(1)[0][0]  # body column (hanging labels sit left of it)
    out = []
    open_frame = None
    for i, ln in enumerate(lines):
        fr = framed_lines.get(i)
        at_start = i == 0  # nothing of this frame / paragraph written yet
        if fr != open_frame:
            if open_frame is not None:
                out.append("</div>")  # a block element: no line break needed after it
            if fr is not None:
                out.append('<div class="qframe">')
            elif i and not out[-1].endswith("</div>"):
                out.append("\n")
            open_frame, at_start = fr, True
        if not at_start:
            # a line that runs to the right edge continues on the next one, unless that one opens a paragraph / item
            # a sentence that ends exactly at the edge still ends the line: what follows is mostly a list / 数列 /
            # new instruction, and a break between two sentences of one paragraph costs nothing
            prev = lines[i - 1]
            last = next((c["c"] for c in reversed(prev["chars"]) if c["c"].strip()), "")
            # 」 at the edge ends a line only when the next one opens a new paragraph / utterance (「…」と言った joins)
            opens = ln["chars"][0]["c"] in "　「"
            short = prev["x1"] < right[fr] - main * 1.2 or last in "。？！" or last == "」" and opens
            first, prev_first = ln["chars"][0]["c"], prev["chars"][0]["c"]
            # same opening symbol as the line before (〔…〕…19人 / 〔…〕…13人): rows of a list
            parallel = first == prev_first and not JP_RE.match(first)
            item = _starts_item(ln["chars"], main) or parallel
            if TRACE is not None:
                TRACE.append({"prev": "".join(c["c"] for c in lines[i - 1]["chars"][-12:]),
                              "head": "".join(c["c"] for c in ln["chars"][:12]), "break": short or item, "item": item})
            if short or item:
                out.append("\n")
                at_start = True
        if at_start and fr is None and ln["chars"][0]["c"] != "　":
            ind = int(round((ln["x0"] - left) / main))
            if 0 < ind <= 4:
                out.append("　" * ind)
        chars = ln["chars"]
        if not at_start:  # a continuation line: its leading 　 was only alignment
            while len(chars) > 1 and chars[0]["c"] == "　":
                chars = chars[1:]
        out.append(_line_html(chars, main, body_bold))
    if open_frame is not None:
        out.append("</div>")
    return "".join(out)


TRACE: list[dict] | None = None  # QA: set to [] to record every join / break decision
FURNITURE_RE = re.compile(r"━[^━]{0,16}━")  # page number bar of the scanned-layout papers: ━ 0理 100 ━


CAPTION_RE = re.compile(r"(図|表|グラフ|資料|写真)\s*[0-9０-９ⅠⅡⅢⅣⅤ]*")


def _has_figure_caption(chars: list[dict], unit: float) -> bool:
    """「図３」 alone on a line, or set apart from the text by a wide gap: the caption of a figure in the crop."""
    chunks, cur = [], [chars[0]]
    for a, b in zip(chars, chars[1:]):
        if b["bb"].x0 - a["bb"].x1 > unit * 4:
            chunks.append(cur)
            cur = []
        cur.append(b)
    chunks.append(cur)
    texts = ["".join(c["c"] for c in ch).strip() for ch in chunks]
    return any(CAPTION_RE.fullmatch(t) for t in texts)


def _is_furniture(chars: list[dict]) -> bool:
    text = "".join(c["c"] for c in chars)
    return bool(FURNITURE_RE.search(text)) and len(re.sub(r"\s|" + FURNITURE_RE.pattern, "", text)) <= 6


def _starts_item(chars: list[dict], unit: float) -> bool:
    """The line opens a list entry / paragraph, so it is never joined to the line before:
    ア．  ア　(gap)  （イ）  (ｱ)  〔問１〕  (1)  ①  ⑴  問3  1．  ・ ● ※  and a line that repeats the opening
    symbol of the line before. (A 　 indent alone is not enough: 「…時間は／　2 点P…」 is one sentence.)"""
    head = "".join(c["c"] for c in chars[:8])
    if ITEM_START_RE.match(head) or head.startswith("　　"):  # a deep indent opens a heading / 資料
        return True
    # a one-char marker set apart by a gap: ア　自動車 / Ａ　…
    return (len(chars) > 1 and bool(re.match(r"[ア-ンＡ-Ｚあ-ん]", chars[0]["c"]))
            and chars[1]["bb"].x0 - chars[0]["bb"].x1 > unit * 0.5)


def _line_html(chars: list[dict], unit: float, body_bold: bool) -> str:
    out = []
    prev = None
    state: dict[str, object] = {}
    i = 0

    def close_all():
        for k in reversed(list(state)):
            out.append(CLOSE[k](state[k]))
        state.clear()

    while i < len(chars):
        c = chars[i]
        if prev is not None:
            gap = c["bb"].x0 - prev["bb"].x1
            if gap > unit * 0.8:
                close_all()
                out.append("　" * min(4, max(1, int(round(gap / unit)))))
        want = {"b": c["bold"] and not body_bold and not c.get("blank"), "u": c.get("u", False),
                "kt": c.get("kt", False), "box": c.get("box"), "wrap": c.get("wrap")}
        for k in list(state):
            if state[k] != want.get(k):
                close_all()
                break
        for k in ("box", "b", "u", "kt", "wrap"):
            v = want[k]
            if v and k not in state:
                out.append(OPEN[k](v))
                state[k] = v
        if c.get("blank"):
            out.append('<span class="qbox blank"></span>')
        elif c.get("maru"):
            out.append(f'<span class="maru">{html.escape(c["c"])}</span>')
        elif c.get("ruby"):
            n = c["ruby_len"]
            base = "".join(html.escape(x["c"]) for x in chars[i:i + n])
            out.append(f"<ruby>{base}<rt>{html.escape(c['ruby'])}</rt></ruby>")
            prev = chars[i + n - 1]
            i += n
            continue
        else:
            out.append(html.escape(c["c"]))
        prev = c
        i += 1
    close_all()
    return "".join(out).rstrip(" 　")


OPEN = {"b": lambda v: "<b>", "u": lambda v: "<u>", "kt": lambda v: '<em class="kt">',
        "box": lambda v: '<span class="qbox">', "wrap": lambda v: f"<{v}>"}
CLOSE = {"b": lambda v: "</b>", "u": lambda v: "</u>", "kt": lambda v: "</em>",
         "box": lambda v: "</span>", "wrap": lambda v: f"</{v}>"}

def convert_exam(eid: str, ex: dict, seg: dict, keep: set[str]) -> dict[str, str]:
    if ex.get("subject") not in SUBJECTS:
        return {}
    doc = fitz.open(ROOT / ex["files"]["question"])
    labels = node_labels(seg)
    texts: dict[str, str] = {}
    for name, regions in crop_regions(seg).items():
        path = f"q/{eid}/{name}.png"
        if path in keep:
            continue
        st: Counter = Counter()
        raw = []
        for r in regions:
            page = doc[r["page"]]
            clip = clip_of(page, r)
            st.update(crop_stats(page, clip))
            raw.append("".join(ch["c"] for ch, _, _ in _page_chars(page) if _in_clip(ch, clip)))
        if not is_plain(st, " ".join(raw), ex["subject"]):
            continue
        h = crop_html(doc, regions, labels.get(name.split("_")[0].rsplit("-p", 1)[0], ""))
        if h:
            texts[path] = h
    return texts


def main() -> None:
    exams = load_json(OUT / "exams.json", {})
    keep = set((load_json(OVERRIDES, {}) or {}).get("keep_image", []))
    rows = []
    for eid, ex in exams.items():
        seg = load_json(OUT / "segments" / f"{eid}.json")
        if not seg:
            continue
        texts = convert_exam(eid, ex, seg, keep)
        dump_json(OUT / "qtext" / f"{eid}.json", texts)
        rows += [f"<tr><td><img src='../{p}'></td><td><div class='qtext'>{h}</div><small>{p}</small></td></tr>"
                 for p, h in texts.items()]
        if texts:
            print(f"[qtext] {eid}: {len(texts)} crops -> text")
    # QA sheet: each text crop next to its PNG (styles = the .qtext rules of web/src/style.css)
    css = "\n".join(l for l in (ROOT / "web" / "src" / "style.css").read_text(encoding="utf-8").splitlines()
                    if l.startswith((".qtext", ".thumb.qtext")))
    (OUT / "preview").mkdir(parents=True, exist_ok=True)
    (OUT / "preview" / "qtext.html").write_text(
        "<html><head><meta charset='utf-8'><title>qtext</title><style>:root{--ink:#111}img{max-width:600px}"
        f"td{{vertical-align:top;border-bottom:1px solid #ccc;padding:6px}}\n{css}</style></head><body><table>"
        + "".join(rows) + "</table></body></html>", encoding="utf-8")
    print(f"[qtext] total {len(rows)} -> {OUT / 'preview' / 'qtext.html'}")


if __name__ == "__main__":
    main()
