"""Step 4: build answer slots from 解答用紙 and extract answers from 模範解答.

Outputs out/answers/{exam_id}.json:
{
  "exam_id": ..,
  "slots": [
    {"id": "1-1", "big": 1, "sub": 1, "label": "①", "unit": "", "parts": ["AD","BC"] | null,
     "answer_type": "number|fraction|ratio|multi|text", "answer": "23/120" | ["36","42"],
     "work_required": false, "confidence": "high|low", "raw_values": [...]}
  ]
}
Kyoritsu facts:
  解答用紙: big label digit size ~19.8 x~51; sub labels ①/あ size 10.6; units size 10.6 (g, 株, 点, ｃｍ, ...)
  模範解答: re-typeset. big label MS-PMincho 10.5 x~110 digits; sub labels MS-PMincho ①/あ; answer values
            Calibri / CambriaMath size >= 13; work steps in MS-Mincho / Suken* fonts (ignored).
Manual fixes: pipeline/overrides/answers/{exam_id}.json  {"slots": {"1-1": {"answer": "...", ...}}}
"""
from __future__ import annotations

import re
from fractions import Fraction

import fitz

from common import OUT, OVERRIDES, ROOT, Span, iter_spans, sub_index, kana_index, load_json, dump_json, nfkc

ANSWER_FONTS = ("Calibri", "Cambria")
UNIT_WORDS = {"g", "株", "点", "ｍ", "ｍ2", "m", "ｃｍ", "ｃｍ2", "cm", "cm2", "個", "人", "分", "秒", "度", "円", "通り", "回",
              "枚", "本", "％", "%", "倍", "km", "ｋｍ", "L", "Ｌ", "dL", "mL", "kg", "ｋｇ", "時間", "日", "番目", "ｍ3", "cm3", "ｃｍ3"}
RE_PART_LABEL = re.compile(r"^[A-Z]{1,3}$")  # AD, BC ...


def _is_big_label(s: Span, mode: str) -> bool:
    if len(s.text) != 1 or s.text not in "123456789":
        return False
    if mode == "sheet":
        return s.size >= 15 and s.x0 < 70
    return "PMincho" in s.font and 9.5 <= s.size <= 11.5 and s.x0 < 130


def _sub_label(s: Span) -> tuple[str, int] | None:
    t = s.text.strip()
    if not t:
        return None
    ch = t[0]
    if (i := sub_index(ch)) is not None:
        return ("num", i)
    if len(t) == 1 and (i := kana_index(ch)) is not None:
        return ("kana", i)
    return None


def build_slots(sheet: fitz.Document) -> list[dict]:
    spans = [s for s in iter_spans(sheet) if s.page == 0]
    bigs = sorted([s for s in spans if _is_big_label(s, "sheet")], key=lambda s: s.y0)
    slots: list[dict] = []
    for i, b in enumerate(bigs):
        y0 = b.y0 - 5
        y1 = bigs[i + 1].y0 - 5 if i + 1 < len(bigs) else 860  # stop before 受験番号 footer
        band = [s for s in spans if y0 <= s.y0 < y1 and s is not b]
        labels = [(s, _sub_label(s)) for s in band if _sub_label(s)]
        labels.sort(key=lambda t: (round(t[0].y0 / 12), t[0].x0))
        work_required = any("計算式" in s.text for s in band)
        part_labels = [s for s in band if RE_PART_LABEL.match(s.text)]
        bno = int(b.text)
        if not labels:
            # whole 大問 is one slot (rare)
            slots.append(_slot(bno, 1, "", "", None, work_required))
            continue
        for j, (ls, (kind, idx)) in enumerate(labels):
            # unit = texts on the same row between this label and next label
            nx = labels[j + 1][0].x0 if j + 1 < len(labels) and abs(labels[j + 1][0].y0 - ls.y0) < 12 else 800
            row = [s for s in band if abs(s.y0 - ls.y0) < 14 and ls.x0 < s.x0 < nx and s is not ls
                   and not _sub_label(s) and not RE_PART_LABEL.match(s.text)]
            unit = "".join(nfkc(s.text) for s in sorted(row, key=lambda s: s.x0))
            unit = unit.replace("（答え）", "").replace("(答え)", "").strip()
            parts = None
            my_parts = [p for p in part_labels if ls.x0 - 5 < p.x0 < nx and 0 < ls.y0 - p.y0 < 30]
            if len(my_parts) >= 2:
                parts = [p.text for p in sorted(my_parts, key=lambda p: p.x0)]
            label = ls.text[0]
            slots.append(_slot(bno, idx, label, unit, parts, work_required and kind == "num" and "計算式" in "".join(
                s.text for s in band if abs(s.y0 - ls.y0) < 60)))
    seen: set[str] = set()
    uniq = []
    for sl in slots:
        if sl["id"] in seen:
            continue
        seen.add(sl["id"])
        uniq.append(sl)
    return uniq


def _slot(big: int, sub: int, label: str, unit: str, parts, work: bool) -> dict:
    return {"id": f"{big}-{sub}", "big": big, "sub": sub, "label": label, "unit": unit,
            "parts": parts, "work_required": work, "answer_type": None, "answer": None,
            "confidence": "none", "raw_values": []}


WORK_FONT_HINTS = ("Suken",)
RE_NUMERIC = re.compile(r"^[0-9０-９.,．，/／:：()（）]+$")
RE_NUM_UNIT = re.compile(r"^([0-9０-９][0-9０-９.,．，/／:：]*)([^\d０-９.,/:()（）]{1,4})$")
CHOICE_CHARS = set("アイウエオカキクケコ")


def words_from_rawdict(page: fitz.Page) -> list[Span]:
    """Whitespace-split words with precise bbox from per-character data."""
    out: list[Span] = []
    for b in page.get_text("rawdict")["blocks"]:
        for line in b.get("lines", []):
            for sp in line["spans"]:
                font, size = sp["font"], sp["size"]
                cur: list[dict] = []

                def flush():
                    if not cur:
                        return
                    x0 = min(c["bbox"][0] for c in cur); y0 = min(c["bbox"][1] for c in cur)
                    x1 = max(c["bbox"][2] for c in cur); y1 = max(c["bbox"][3] for c in cur)
                    out.append(Span(0, x0, y0, x1, y1, size, font, "".join(c["c"] for c in cur)))
                    cur.clear()

                for ch in sp["chars"]:
                    if ch["c"].isspace() or ch["c"] == "　":
                        flush()
                    else:
                        cur.append(ch)
                flush()
    return out


def _is_value(w: Span) -> bool:
    t = nfkc(w.text)
    if any(h in w.font for h in WORK_FONT_HINTS):
        return False
    if w.size < 7.5:  # superscript ² etc.
        return False
    if RE_NUMERIC.match(t) and any(ch.isdigit() for ch in t):
        return True
    if RE_NUM_UNIT.match(t):
        return True
    if len(t) == 1 and t in CHOICE_CHARS:
        return True
    return False


def extract_values(model: fitz.Document) -> tuple[list[Span], list[Span], list[Span], list[Span]]:
    words = words_from_rawdict(model[0])
    rows_x = {}
    for w in words:
        rows_x.setdefault(round(w.cy / 6), []).append(w.x0)
    bigs = [w for w in words if w.text in "123456789" and len(w.text) == 1 and w.x0 < 130
            and min(rows_x[round(w.cy / 6)]) >= w.x0 - 1 and "Mincho" not in w.font.replace("PMincho", "")]
    bigs = _dedupe_bigs(sorted(bigs, key=lambda w: w.y0))
    labels = [w for w in words if _sub_label(w) and w not in bigs]

    def on_label(w: Span) -> bool:
        return any(abs(l.x0 - w.x0) < 3 and abs(l.y0 - w.y0) < 3 for l in labels)

    values = [w for w in words if _is_value(w) and w not in bigs and w.y0 > 80 and not on_label(w)]
    kotae = [w for w in words if "答え" in w.text]
    return bigs, labels, values, kotae


def _dedupe_bigs(bigs: list[Span]) -> list[Span]:
    """Keep a monotone 1,2,3.. sequence going down the page."""
    out: list[Span] = []
    expect = 1
    for w in bigs:
        if int(w.text) == expect:
            out.append(w)
            expect += 1
    return out


def assign(slots: list[dict], model: fitz.Document) -> None:
    bigs, labels, values, kotae = extract_values(model)
    if not bigs:
        return
    for i, b in enumerate(bigs):
        y0 = b.y0 - 5
        y1 = bigs[i + 1].y0 - 5 if i + 1 < len(bigs) else 880
        bno = int(b.text)
        band_labels = sorted([s for s in labels if y0 <= s.y0 < y1], key=lambda s: (round(s.y0 / 12), s.x0))
        band_values = [s for s in values if y0 <= s.y0 < y1]
        band_kotae = [k for k in kotae if y0 <= k.y0 < y1]
        band_slots = [sl for sl in slots if sl["big"] == bno]
        for sl in band_slots:
            sl["_vals"] = []
        if not band_labels:
            if len(band_slots) == 1:
                _fill(band_slots[0], band_values)
            continue
        # map 答え boxes -> owning label (nearest label above-or-level, to the left)
        kotae_owner: dict[int, Span] = {}
        for k in band_kotae:
            cands = [l for l in band_labels if l.y0 - 12 <= k.y0 and l.x0 < k.x0]
            if cands:
                lab = min(cands, key=lambda l: k.y0 - l.y0)
                kotae_owner[id(lab)] = k
        used: set[int] = set()
        for lab in band_labels:
            k = kotae_owner.get(id(lab))
            if not k:
                continue
            kind, idx = _sub_label(lab)
            sl = next((s for s in band_slots if s["sub"] == idx), None)
            if sl is None:
                continue
            for v in band_values:
                if k.y0 - 6 < v.y0 < k.y0 + 45 and v.x0 > k.x0 - 5:
                    sl["_vals"].append(v)
                    used.add(id(v))
        for v in band_values:
            if id(v) in used:
                continue
            cands = [l for l in band_labels if l.x0 <= v.x0 + 2 and abs(l.cy - v.cy) < 30 and id(l) not in kotae_owner]
            if not cands:
                continue
            lab = max(cands, key=lambda l: l.x0)
            kind, idx = _sub_label(lab)
            sl = next((s for s in band_slots if s["sub"] == idx), None)
            if sl is not None:
                sl["_vals"].append(v)
        for sl in band_slots:
            _fill(sl, sl.pop("_vals", []))


def to_fraction(t: str) -> Fraction | None:
    t = nfkc(t).strip().strip("()").strip()
    try:
        if " " in t:  # mixed number "1 3/22"
            whole, frac = t.split(" ", 1)
            return Fraction(int(whole)) + Fraction(frac)
        return Fraction(t)
    except (ValueError, ZeroDivisionError):
        return None


def _fill(slot: dict, vals: list[Span]) -> None:
    vals = sorted(vals, key=lambda s: (s.x0, s.y0))
    texts = []
    for v in vals:
        t = nfkc(v.text).strip("()（）")
        m = RE_NUM_UNIT.match(t)
        texts.append(m.group(1) if m else t)
    slot["raw_values"] = [f"{t}@({v.x0:.0f},{v.y0:.0f})" for t, v in zip(texts, vals)]
    if not vals:
        slot["confidence"] = "none"
        return
    # detect stacked fractions: pairs with x-overlap and 12 < dy < 28
    used = set()
    tokens: list[tuple[float, str]] = []  # (x, text)
    for i, a in enumerate(vals):
        if i in used:
            continue
        frac = None
        for j, b in enumerate(vals):
            if j == i or j in used:
                continue
            if abs(a.cx - b.cx) < 10 and 6 < abs(b.y0 - a.y0) < 30:
                frac = (i, j) if a.y0 < b.y0 else (j, i)
                break
        if frac:
            used.update(frac)
            tokens.append((a.cx, f"{texts[frac[0]]}/{texts[frac[1]]}"))
        else:
            used.add(i)
            tokens.append((a.cx, texts[i]))
    tokens.sort()
    # mixed number: integer token immediately left (< 14pt) of a fraction token on same slot
    merged: list[str] = []
    xs = [t[0] for t in tokens]
    k = 0
    while k < len(tokens):
        x, t = tokens[k]
        if k + 1 < len(tokens) and "/" in tokens[k + 1][1] and "/" not in t and (tokens[k + 1][0] - x) < 16:
            merged.append(f"{t} {tokens[k + 1][1]}")
            k += 2
        else:
            merged.append(t)
            k += 1
    unit = slot.get("unit", "")
    # alternative equal forms e.g. 25/22 (1 3/22), 7.2 (7 1/5, 36/5) -> keep first, rest as variants
    fr = [to_fraction(t) for t in merged]
    if len(merged) > 1 and all(f is not None for f in fr) and len(set(fr)) == 1:
        slot["variants"] = merged[1:]
        merged = merged[:1]
    if len(merged) == 1 and ":" in merged[0] and ":" not in unit:
        slot["answer_type"] = "text"
        slot["answer"] = merged[0]
        slot["confidence"] = "high"
        return
    if slot.get("parts") and len(merged) == len(slot["parts"]):
        slot["answer_type"] = "multi"
        slot["answer"] = merged
        slot["confidence"] = "high"
    elif ":" in unit or "：" in unit:
        slot["answer_type"] = "ratio"
        slot["answer"] = ":".join(merged)
        n_expected = unit.count(":") + unit.count("：") + 1
        slot["confidence"] = "high" if slot["answer"].count(":") + 1 == n_expected else "low"
    elif len(merged) == 1:
        slot["answer"] = merged[0]
        if to_fraction(merged[0]) is None:
            slot["answer_type"] = "text"
        else:
            slot["answer_type"] = "fraction" if "/" in merged[0] else "number"
        slot["confidence"] = "high"
    elif "秒後と" in unit and len(merged) == 2:
        slot["answer_type"] = "multi"
        slot["answer"] = merged
        slot["parts"] = ["1回目", "2回目"]
        slot["confidence"] = "high"
    else:
        slot["answer_type"] = "multi"
        slot["answer"] = merged
        slot["confidence"] = "low"


def apply_overrides(exam_id: str, slots: list[dict]) -> list[dict]:
    ov = load_json(OVERRIDES / "answers" / f"{exam_id}.json")
    if not ov:
        return slots
    by_id = {s["id"]: s for s in slots}
    for sid, patch in ov.get("slots", {}).items():
        if patch.get("delete"):
            by_id.pop(sid, None)
            continue
        s = by_id.get(sid)
        if s is None:
            big, sub = sid.split("-")
            s = _slot(int(big), int(sub), patch.get("label", ""), patch.get("unit", ""), patch.get("parts"), False)
            by_id[sid] = s
        s.update(patch)
        s["confidence"] = "manual"
    return sorted(by_id.values(), key=lambda s: (s["big"], s["sub"]))


def main() -> None:
    exams = load_json(OUT / "exams.json", {})
    for eid, ex in exams.items():
        f = ex["files"]
        if "sheet" not in f or "answer" not in f:
            print(f"[answers] {eid}: missing sheet/answer, skip")
            continue
        slots = build_slots(fitz.open(ROOT / f["sheet"]))
        assign(slots, fitz.open(ROOT / f["answer"]))
        slots = apply_overrides(eid, slots)
        dump_json(OUT / "answers" / f"{eid}.json", {"exam_id": eid, "slots": slots})
        low = [s["id"] for s in slots if s["confidence"] in ("low", "none")]
        print(f"[answers] {eid}: {len(slots)} slots, needs review: {low}")
        for s in slots:
            print(f"    {s['id']:5} {s['label']} unit={s['unit']!r:12} parts={s['parts']} -> {s['answer']!r} [{s['confidence']}]")


if __name__ == "__main__":
    main()
