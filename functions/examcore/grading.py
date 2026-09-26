"""Answer normalization and grading.

answer_type:
  number   : integer / decimal / fraction, compared as exact rational
  fraction : same as number (UI hint: fraction input)
  ratio    : "a:b[:c]" compared after reduction (2:4 == 1:2)
  text     : normalized string equality (words, time "9:40"); variants accepted
  choice   : single option (A / ウ / 正)
  set      : several options, order free ("A・D" == "D, A")
  sequence : ordered ("A→C→D" ; arrows / separators ignored)
  multi    : list of parts, each graded as number when parseable, set when it lists options ("ア・ウ"),
             else text; "a|b" in a part = accepted alternatives; all parts must match
  essay    : free text; not auto-gradable -> pending (manual grade)
  manual   : drawing / graph; pending (manual grade)
Student input tolerated: 全角 digits/symbols, spaces, thousands commas, trailing unit text,
mixed numbers "1 3/22", "1と3/22", decimals with 全角 dot.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction

_UNIT_TAIL = re.compile(r"\s*[^\d\s.,/:()][^\s]*$")
_MIXED = re.compile(r"^(-?\d+)\s*(?:と|\s)\s*(\d+)\s*/\s*(\d+)$")
_FRAC = re.compile(r"^(-?\d+)\s*/\s*(\d+)$")
_DEC = re.compile(r"^-?\d+(?:\.\d+)?$")
_SEP = re.compile(r"[・,、;／/\s]+")
_ARROW = re.compile(r"\s*(→|->|⇒|➡|―>|>|、|,|・|\s)\s*")

PENDING_TYPES = ("essay", "manual")


def normalize(s: str) -> str:
    if s is None:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = t.replace("：", ":").replace("／", "/").replace("，", ",").replace("．", ".").replace("−", "-").replace("－", "-")
    t = t.replace("、", ",").replace("。", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_number(s: str) -> Fraction | None:
    t = normalize(s)
    if not t:
        return None
    t = t.replace(",", "")
    t = re.sub(r"(\d)\s*と\s*(\d)", r"\1 \2", t)
    for _ in range(3):
        stripped = _UNIT_TAIL.sub("", t).strip()
        if not stripped or stripped == t:
            break
        t = stripped
    t = re.sub(r"^[^\d\-(]+\s*", "", t) or t
    m = _MIXED.match(t)
    if m:
        whole, num, den = int(m[1]), int(m[2]), int(m[3])
        if den == 0:
            return None
        f = Fraction(num, den)
        return Fraction(whole) - f if whole < 0 else Fraction(whole) + f
    m = _FRAC.match(t)
    if m:
        if int(m[2]) == 0:
            return None
        return Fraction(int(m[1]), int(m[2]))
    if _DEC.match(t):
        return Fraction(t)
    return None


def parse_ratio(s: str) -> tuple[Fraction, ...] | None:
    t = normalize(s)
    parts = [p.strip() for p in t.split(":")]
    if len(parts) < 2:
        return None
    vals = [parse_number(p) for p in parts]
    if any(v is None for v in vals):
        return None
    return reduce_ratio(tuple(vals))  # type: ignore[arg-type]


def reduce_ratio(vals: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    from math import gcd, lcm
    den = 1
    for v in vals:
        den = lcm(den, v.denominator)
    ints = [int(v * den) for v in vals]
    g = 0
    for i in ints:
        g = gcd(g, abs(i))
    g = g or 1
    return tuple(Fraction(i // g) for i in ints)


def norm_word(s: str) -> str:
    """Text equality key: NFKC, no spaces, no punctuation noise, katakana long vowel unified."""
    t = normalize(s).replace(" ", "")
    t = t.replace("ｰ", "ー").replace("-", "ー") if re.search(r"[ァ-ン]", t) else t
    return t.rstrip(".。")


def split_set(s) -> list[str]:
    if isinstance(s, (list, tuple)):
        return [norm_word(x) for x in s if norm_word(x)]
    t = normalize(s)
    parts = [norm_word(p) for p in _SEP.split(t) if p]
    if len(parts) == 1 and re.fullmatch(r"[A-Zア-ン]{2,}", parts[0]):
        return list(parts[0])  # "CDF" -> C, D, F
    return parts


def split_sequence(s) -> list[str]:
    if isinstance(s, (list, tuple)):
        return [norm_word(x) for x in s if norm_word(x)]
    t = normalize(s)
    parts = [norm_word(p) for p in _ARROW.split(t) if p and not _ARROW.fullmatch(p)]
    parts = [p for p in parts if p]
    if len(parts) == 1 and re.fullmatch(r"[A-Zア-ン]{2,}", parts[0]):
        return list(parts[0])
    return parts


@dataclass
class GradeResult:
    correct: bool
    normalized: str | list[str]
    parts_correct: list[bool] = field(default_factory=list)
    matched: str | None = None
    pending: bool = False


def _grade_scalar(atype: str, expected, variants: list, student: str) -> GradeResult:
    forms = [expected] + list(variants or [])
    norm = normalize(student)
    if atype in ("number", "fraction"):
        sv = parse_number(student)
        if sv is None:
            return GradeResult(False, norm)
        for f in forms:
            ev = parse_number(str(f))
            if ev is not None and ev == sv:
                return GradeResult(True, norm, matched=str(f))
        return GradeResult(False, norm)
    if atype == "ratio":
        sv = parse_ratio(student)
        if sv is None:
            return GradeResult(False, norm)
        for f in forms:
            ev = parse_ratio(str(f))
            if ev is not None and ev == sv:
                return GradeResult(True, norm, matched=str(f))
        return GradeResult(False, norm)
    if atype == "set":
        sv = set(split_set(student))
        for f in forms:
            if sv and sv == set(split_set(f)):
                return GradeResult(True, norm, matched=str(f))
        return GradeResult(False, norm)
    if atype == "sequence":
        sv = split_sequence(student)
        for f in forms:
            if sv and sv == split_sequence(f):
                return GradeResult(True, norm, matched=str(f))
        return GradeResult(False, norm)
    # text / choice / unknown -> normalized equality, numeric equality as fallback
    key = norm_word(student)
    for f in forms:
        if norm_word(str(f)) == key:
            return GradeResult(True, norm, matched=str(f))
    sv, evs = parse_number(student), [parse_number(str(f)) for f in forms]
    if sv is not None and any(e is not None and e == sv for e in evs):
        return GradeResult(True, norm, matched=str(expected))
    return GradeResult(False, norm)


def grade(key: dict, student) -> GradeResult:
    """key = {"answer_type", "answer", "variants"?, "parts"?}; student = str or list[str] (for multi)."""
    atype = key.get("answer_type") or "text"
    expected = key.get("answer")
    variants = key.get("variants") or []
    if atype in PENDING_TYPES:
        return GradeResult(False, normalize(student) if not isinstance(student, list) else student, pending=True)
    if atype == "multi" or (isinstance(expected, list) and atype not in ("set", "sequence")):
        exp_list = list(expected)
        stu_list = list(student) if isinstance(student, (list, tuple)) else _split_multi(student, len(exp_list))
        stu_list = (stu_list + [""] * len(exp_list))[: len(exp_list)]
        results = [_grade_part(str(e), s) for e, s in zip(exp_list, stu_list)]
        return GradeResult(all(r.correct for r in results), [r.normalized for r in results],
                           parts_correct=[r.correct for r in results])
    if isinstance(student, (list, tuple)):
        student = "・".join(str(x) for x in student) if atype == "set" else "→".join(str(x) for x in student)
    return _grade_scalar(atype, expected if isinstance(expected, list) else str(expected),
                         variants, str(student) if student is not None else "")


def _grade_part(expected: str, student: str) -> GradeResult:
    """One part of a multi answer. "a|b" = accepted alternatives (answer keys live in Firestore, which has no
    nested arrays); a part listing several choice letters ("ア・ウ") is order-free like a set."""
    alts = [a for a in expected.split("|") if a] or [expected]
    res = None
    for a in alts:
        opts = split_set(a)
        is_set = len(opts) > 1 and all(re.fullmatch(r"[ア-ンA-Z]", o) for o in opts)
        sub_type = "number" if parse_number(a) is not None else ("set" if is_set else "text")
        res = _grade_scalar(sub_type, a, [], student)
        if res.correct:
            return res
    return res


def _split_multi(s: str, n: int) -> list[str]:
    t = normalize(s)
    parts = [p for p in re.split(r"[,、;/]\s*|\s{2,}", t) if p]
    if len(parts) == n:
        return parts
    parts = t.split()
    return parts if len(parts) == n else [t]
