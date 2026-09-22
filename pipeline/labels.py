"""Marker/label parsing shared by segmentation (問題 PDF) and slot building (解答用紙).

Rank hierarchy (smaller = higher level):
  0 BIG   大問 digit
  1 Q     問１ / 問 1 / 問一
  2 P     ⑴ / （１） / (1)
  3 C     ①②   or kana あいう (fill-in slots)
  4 A     katakana ア/イ (part labels), alpha AD/BC, roman Ⅰ/Ⅱ  -> become `parts` of the parent slot
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
PAREN = "⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽⑾⑿⒀⒁⒂⒃⒄⒅⒆⒇"
KANA = "あいうえおかきくけこさしすせそたちつてと"
KATA = "アイウエオカキクケコサシスセソタチツテト"
KANJI_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
             "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15}

RE_Q = re.compile(r"^問\s*([0-9０-９]{1,2}|[一二三四五六七八九十]{1,2})\s*[．.、]?")
RE_PAREN = re.compile(r"^[（(]\s*([0-9０-９]{1,2})\s*[）)]")
RE_ALPHA_PART = re.compile(r"^[A-Z]{1,3}$")
RE_ROMAN = re.compile(r"^[ⅠⅡⅢⅣⅤⅰⅱⅲⅳⅴ]$")


@dataclass
class Label:
    rank: int
    kind: str     # Q, P, C, K, A, ALPHA, ROMAN
    index: int    # numeric index (1-based)
    text: str     # display label e.g. 問１, ⑴, ①, あ, ア, AD
    raw: str

    @property
    def key(self) -> str:
        """Path component used in slot ids."""
        if self.kind in ("A", "ALPHA", "ROMAN"):
            return self.text
        return str(self.index)


def to_int(s: str) -> int:
    s = unicodedata.normalize("NFKC", s)
    if s.isdigit():
        return int(s)
    return KANJI_NUM.get(s, 0)


def parse_label(text: str) -> Label | None:
    """Classify the leading marker of a span. Returns None if not a marker."""
    t = text.strip()
    if not t:
        return None
    ch = t[0]
    m = RE_Q.match(t)
    if m:
        n = to_int(m.group(1))
        return Label(1, "Q", n, f"問{n}", t) if n else None
    if ch in PAREN:
        n = PAREN.index(ch) + 1
        return Label(2, "P", n, f"({n})", t)
    m = RE_PAREN.match(t)
    if m:
        n = to_int(m.group(1))
        return Label(2, "P", n, f"({n})", t) if n else None
    if ch in CIRCLED:
        n = CIRCLED.index(ch) + 1
        return Label(3, "C", n, ch, t)
    if len(t) == 1 and ch in KANA:
        return Label(3, "K", KANA.index(ch) + 1, ch, t)
    if len(t) == 1 and ch in KATA:
        return Label(4, "A", KATA.index(ch) + 1, ch, t)
    if RE_ALPHA_PART.match(t) and (len(t) >= 2 or t in "XYZ"):   # AD, BC, or X / Y part labels
        return Label(4, "ALPHA", 0, t, t)
    if ch in "ⅠⅡⅢⅣⅤⅰⅱⅲⅳⅴ" and (len(t) == 1 or t[1] in " \u3000.．、"):
        return Label(4, "ROMAN", "ⅠⅡⅢⅣⅤ".find(unicodedata.normalize("NFKC", ch)[0]) + 1, ch, t)
    return None


def is_big_digit(text: str) -> int | None:
    """大問 number: 1-30, half- or full-width."""
    t = unicodedata.normalize("NFKC", text.strip())
    if t.isdigit() and 1 <= int(t) <= 30 and len(t) <= 2:
        return int(t)
    return None
