"""四谷大塚 公開組分けテスト: file-name scan, footer / glyph-marker handling, two-tier 国語 segmentation."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import fitz  # noqa: E402

from common import nfkc  # noqa: E402
import inventory  # noqa: E402
import japanese  # noqa: E402
import segment  # noqa: E402

PDFS = ROOT / "kumiwake_past"


def _pdf(name: str) -> Path:
    p = PDFS / name
    if not p.exists():
        pytest.skip("kumiwake_past PDFs not on this machine")
    return p


def test_file_name_pattern():
    m = inventory.RE_KUMI.match(nfkc("2026年3月 公開組分けテスト５年　第１回算数問題.pdf"))
    assert m and (m["year"], m["month"], m["round"], m["subject"], m["kind"]) == ("2026", "3", "1", "算数", "問題")
    assert inventory.RE_KUMI.match(nfkc("2026年8月 公開組分けテスト５年　第５回国語回答.pdf"))["kind"] == "回答"
    assert not inventory.RE_KUMI.match(nfkc("2-1入試_算数_問題.pdf"))


def test_footer_is_noise():
    assert segment._is_footer("2026－組①－５－算－2")
    assert segment._is_footer("2026－組②－10－国－14")
    assert not segment._is_footer("2026年3月15日実施")


def test_math_glyph_markers():
    doc = fitz.open(_pdf("2026年3月 公開組分けテスト５年　第１回算数問題.pdf"))
    bigs = segment.segment(doc, "kumiwake_math")
    shape = {b["no"]: [s["label"] for s in b["subs"]] for b in bigs}
    assert shape[1] == ["(1)", "(2)", "(3)"]
    assert len(shape[2]) == 8
    assert [s["label"] for s in bigs[7]["subs"][1]["subs"]] == ["①", "②"]   # 8(2)①②
    assert next(b for b in bigs if b["no"] == 4).get("whole")               # figure beside (1)(2)


def test_japanese_tiers():
    doc = fitz.open(_pdf("2026年3月 公開組分けテスト５年　第１回国語問題.pdf"))
    bigs = japanese.segment_tiers(doc)
    assert [b["no"] for b in bigs] == [1, 2, 3, 4]
    b1, b2 = bigs[0]["regions"], bigs[1]["regions"]
    # 大問1 (漢字) and the start of 大問2 share the top tier of page 1
    assert len(b1) == 1 and b1[0]["page"] == 1 and b1[0]["y1"] == japanese.TIERS[0][1]
    assert b2[0]["page"] == 1 and b2[0]["x1"] == b1[0]["x0"]
    # a page wholly inside one 大問 is a single full-page region
    assert any(r["y0"] == japanese.TIERS[0][0] and r["y1"] == japanese.TIERS[1][1] for r in bigs[2]["regions"])
