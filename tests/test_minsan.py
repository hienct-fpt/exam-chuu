"""min-san import: listing parser + 50-minute set packing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import minsan  # noqa: E402

LISTING = """<main>
<div class="db_school_name">栄東中学校 2026</div>
<a href="//min-san.com/mobile/kakomon/db/6a1f6d2fd6f50/">
<p class="grade5">５年生向け　<span style="color:red">★★</span><span>☆☆☆☆</span></p>
<img loading="lazy" src="//min-san.com/kakomon_mobile/k_svg/6a1f6d2fd6f48-ka-9338_crop1.svgz?1790160478" alt="栄東中学校2026">
</a>
<section class="db_comment">流水算の基本的な問題です。</section>
<form><button type="submit" class="db_tag" name="tag_word" value="流水算">流水算</button></form>
<form><button type="submit" class="db_tag" name="tag_word" value="逆比">逆比</button></form>
<div class="db_school_name">帝京大学中学校 2020</div>
<a href="//min-san.com/mobile/kakomon/dbk/5f630ef013b2c/">
<p class="grade4">４年生向け　</p>
<img src="//min-san.com/kakomon/k_svg/5f630ef013ad7-ka-22661_crop1.svgz" alt="x">
</a>
<a href="//min-san.com/mobile/db/2/6/0/">2</a><a href="//min-san.com/mobile/db/17/6/0/">17</a>
</main>"""


def test_parse_list_handles_both_markup_generations():
    a, b = minsan.parse_list(LISTING)
    assert a["id"] == "6a1f6d2fd6f50" and a["school"] == "栄東中学校" and a["year"] == 2026
    assert a["grade"] == 5 and a["stars"] == 2 and a["tags"] == ["流水算", "逆比"]
    assert a["svg_url"].endswith("_crop1.svgz") and "?" not in a["svg_url"]
    assert a["url"] == "https://min-san.com/mobile/kakomon/db/6a1f6d2fd6f50/"
    assert b["grade"] == 4 and b["stars"] is None and b["comment"] == ""
    assert b["svg_url"] == "//min-san.com/kakomon/k_svg/5f630ef013ad7-ka-22661_crop1.svgz"
    assert b["url"] == "https://min-san.com/mobile/kakomon/dbk/5f630ef013b2c/"
    assert minsan.max_page(LISTING, "db", 6) == 17


def _items(spec):
    out = []
    for school, n, cat in spec:
        out += [{"id": f"{school}{i}", "school": school, "cat": cat} for i in range(n)]
    return out


def test_pack_sets_keeps_schools_together_and_respects_size():
    items = _items([("A", 13, "db"), ("B", 12, "dbz"), ("C", 7, "dbk"), ("D", 8, "db"), ("E", 1, "dbk")])
    sets = minsan.pack_sets(items, size=20)
    assert all(len(s) <= 20 for s in sets)
    assert sum(len(s) for s in sets) == len(items)
    for s in sets:  # a school never straddles two sets when it fits in one
        for school in {it["school"] for it in s}:
            assert sum(1 for it in s if it["school"] == school) == sum(1 for it in items if it["school"] == school)
    assert len(sets) == 3  # 13+7, 12+8, 1 -> FFD


def test_pack_sets_splits_oversized_school_and_orders_categories():
    items = _items([("Z", 25, "db")]) + _items([("Y", 1, "dbz"), ("Y", 1, "dbk")])
    sets = minsan.pack_sets(items, size=20)
    assert sorted(len(s) for s in sets) == [7, 20]
    small = min(sets, key=len)
    cats = [it["cat"] for it in small if it["school"] == "Y"]
    assert cats == ["dbk", "dbz"]  # 計算 before 図形


def test_year_key_buckets_sparse_years():
    assert minsan.year_key(1998) == (2003, "2003年以前")
    assert minsan.year_key(2016) == (2017, "2015〜2017年")
    assert minsan.year_key(2019) == (2019, "2019年")
    assert minsan.year_key(None)[1] == "年不明"
