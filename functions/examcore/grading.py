"""Answer normalization and grading.

answer_type:
  number   : integer / decimal / fraction, compared as exact rational
  fraction : same as number (kept for UI hint: show fraction input)
  ratio    : "a:b[:c]" compared after reduction (2:4 == 1:2)
  text     : normalized string equality (choice letters ア/イ/ウ, time "9:40", words)
  choice   : alias of text
  multi    : list of parts, each graded as number when parseable else text; all parts must match
Student input tolerated: 全角 digits/symbols, spaces, thousands commas, trailing unit text,
mixed numbers "1 3/22", "1と3/22", decimals with 全角 dot.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction

_UNIT_TAIL = re.compile(r"\s*[^\d\s.,/:()][^\s]*$")  # trailing unit token: "132秒後"->"132", "43.96 m2"->"43.96"
_MIXED = re.compile(r"^(-?\d+)\s*(?:と|\s)\s*(\d+)\s*/\s*(\d+)$")
_FRAC = re.compile(r"^(-?\d+)\s*/\s*(\d+)$")
_DEC = re.compile(r"^-?\d+(?:\.\d+)?$")


def normalize(s: str) -> str:
    """NFKC, unify symbols, collapse whitespace."""
    if s is None:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = t.replace("：", ":").replace("／", "/").replace("，", ",").replace("．", ".").replace("−", "-").replace("－", "-")
    t = t.replace("、", ",")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_number(s: str) -> Fraction | None:
    """Parse '3/4', '1 3/22', '1と3/22', '0.75', '1,200', '132秒後' -> Fraction; None if not numeric."""
    t = normalize(s)
    if not t:
        return None
    t = t.replace(",", "")
    t = re.sub(r"(\d)\s*と\s*(\d)", r"\1 \2", t)  # mixed number "1と3/22" -> "1 3/22"
    # strip trailing unit words, but only if what remains still looks numeric
    for _ in range(3):  # "秒速 25/22 m" style tails: strip up to 3 trailing unit tokens
        stripped = _UNIT_TAIL.sub("", t).strip()
        if not stripped or stripped == t:
            break
        t = stripped
    t = re.sub(r"^[^\d\-(]+\s*", "", t) or t  # leading unit e.g. "時速12" -> "12"
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
    """Scale so all terms are coprime integers: (2, 4) -> (1, 2); (1/2, 3/4) -> (2, 3)."""
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


@dataclass
class GradeResult:
    correct: bool
    normalized: str | list[str]
    parts_correct: list[bool] = field(default_factory=list)
    matched: str | None = None  # which expected form matched (answer or variant)


def _grade_scalar(atype: str, expected: str, variants: list[str], student: str) -> GradeResult:
    forms = [expected] + list(variants or [])
    norm = normalize(student)
    if atype in ("number", "fraction"):
        sv = parse_number(student)
        if sv is None:
            return GradeResult(False, norm)
        for f in forms:
            ev = parse_number(f)
            if ev is not None and ev == sv:
                return GradeResult(True, norm, matched=f)
        return GradeResult(False, norm)
    if atype == "ratio":
        sv = parse_ratio(student)
        if sv is None:
            return GradeResult(False, norm)
        for f in forms:
            ev = parse_ratio(f)
            if ev is not None and ev == sv:
                return GradeResult(True, norm, matched=f)
        return GradeResult(False, norm)
    # text / choice / unknown -> normalized equality, also accept numeric equality as fallback
    for f in forms:
        if normalize(f) == norm:
            return GradeResult(True, norm, matched=f)
    sv, evs = parse_number(student), [parse_number(f) for f in forms]
    if sv is not None and any(e is not None and e == sv for e in evs):
        return GradeResult(True, norm, matched=expected)
    return GradeResult(False, norm)


def grade(key: dict, student) -> GradeResult:
    """key = {"answer_type", "answer", "variants"?, "parts"?}; student = str or list[str] (for multi)."""
    atype = key.get("answer_type") or "text"
    expected = key["answer"]
    variants = key.get("variants") or []
    if atype == "multi" or isinstance(expected, list):
        exp_list = list(expected)
        stu_list = list(student) if isinstance(student, (list, tuple)) else _split_multi(student, len(exp_list))
        stu_list = (stu_list + [""] * len(exp_list))[: len(exp_list)]
        results = []
        for e, s in zip(exp_list, stu_list):
            sub_type = "number" if parse_number(e) is not None else "text"
            results.append(_grade_scalar(sub_type, e, [], s))
        return GradeResult(all(r.correct for r in results), [r.normalized for r in results],
                           parts_correct=[r.correct for r in results])
    return _grade_scalar(atype, str(expected), [str(v) for v in variants], str(student) if student is not None else "")


def _split_multi(s: str, n: int) -> list[str]:
    t = normalize(s)
    parts = [p for p in re.split(r"[,、;/]\s*|\s{2,}", t) if p]
    if len(parts) == n:
        return parts
    parts = t.split()
    return parts if len(parts) == n else [t]
