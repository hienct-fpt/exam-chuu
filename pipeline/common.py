"""Shared helpers for the exam pipeline."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "out"
OVERRIDES = ROOT / "pipeline" / "overrides"

SUBJECT_MAP = {"算数": "math", "国語": "japanese", "理科": "science", "社会": "social"}
KIND_MAP = {"問題": "question", "模範解答": "answer", "解答用紙": "sheet"}

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
PAREN = "⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽⑾⑿⒀⒁⒂"
KANA_SLOTS = "あいうえおかきくけこさしすせそたちつてと"


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def zen2han_digits(s: str) -> str:
    return nfkc(s)


def sub_index(ch: str) -> int | None:
    """①→1, ⑴→1, あ→1 ... returns None if not a sub-question marker."""
    if ch in CIRCLED:
        return CIRCLED.index(ch) + 1
    if ch in PAREN:
        return PAREN.index(ch) + 1
    return None


def kana_index(ch: str) -> int | None:
    if ch in KANA_SLOTS:
        return KANA_SLOTS.index(ch) + 1
    return None


@dataclass
class Span:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    font: str
    text: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def iter_spans(doc: fitz.Document, pages: range | None = None) -> list[Span]:
    out: list[Span] = []
    for pi, page in enumerate(doc):
        if pages is not None and pi not in pages:
            continue
        d = page.get_text("dict")
        for b in d["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    t = s["text"].strip()
                    if not t:
                        continue
                    x0, y0, x1, y1 = s["bbox"]
                    out.append(Span(pi, x0, y0, x1, y1, s["size"], s["font"], t))
    return out


def content_bbox(page: fitz.Page, clip: fitz.Rect) -> fitz.Rect | None:
    """Tight bbox of all text/drawings/images intersecting clip."""
    rects: list[fitz.Rect] = []
    for b in page.get_text("dict", clip=clip)["blocks"]:
        r = fitz.Rect(b["bbox"]) & clip
        if not r.is_empty:
            rects.append(r)
    for dr in page.get_drawings():
        r = fitz.Rect(dr["rect"]) & clip
        if not r.is_empty and r.width > 1 and r.height > 1:
            rects.append(r)
    for img in page.get_image_info():
        r = fitz.Rect(img["bbox"]) & clip
        if not r.is_empty:
            rects.append(r)
    if not rects:
        return None
    acc = rects[0]
    for r in rects[1:]:
        acc |= r
    return acc


def load_json(p: Path, default: Any = None) -> Any:
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def dump_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
