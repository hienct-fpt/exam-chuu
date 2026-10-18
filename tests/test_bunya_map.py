"""Every topic label in pipeline/tags/*.json must map onto the shared 分野 taxonomy (pipeline/bunya_map.py),
so practice sets pool 組み分け items with the school past papers."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from bunya_map import MAPS, bunya_for, unified_topic  # noqa: E402
from minsan import CATS  # noqa: E402

UNMAPPED_OK = {("math", "文章題")}


def _tag_labels():
    out = set()
    for f in (ROOT / "pipeline" / "tags").glob("*.json"):
        subject = f.stem.rsplit("_", 1)[1]
        d = json.loads(f.read_text(encoding="utf-8"))
        for sec in ("bigs", "items"):
            for v in (d.get(sec) or {}).values():
                if v.get("topic"):
                    out.add((subject, v["topic"], f.stem))
    return out


def test_every_tag_label_is_mapped():
    missing = sorted({(s, t) for s, t, _ in _tag_labels() if (s, t) not in UNMAPPED_OK and not bunya_for(t, s)})
    assert not missing, f"add these to pipeline/bunya_map.py: {missing}"


@pytest.mark.parametrize("subject", ["math", "science", "social", "japanese"])
def test_kumiwake_and_schools_share_every_bunya(subject):
    """Each kumiwake 分野 should also be reachable from at least one school exam (and vice versa, mostly)."""
    by_src = {"kumiwake": set(), "school": set()}
    for s, t, stem in _tag_labels():
        if s == subject and bunya_for(t, s):
            by_src["kumiwake" if stem.startswith("kumiwake_") else "school"].add(bunya_for(t, s))
    assert by_src["kumiwake"] & by_src["school"], subject
    assert len(by_src["kumiwake"] & by_src["school"]) >= len(by_src["kumiwake"]) - 1


def test_math_taxonomy_is_minsan():
    minsan = {label for c in CATS.values() for label in c["bunya"].values()}
    assert {v for v in MAPS["math"].values() if v} == minsan


def test_unified_topic_falls_back_to_original():
    assert unified_topic("割合や比の問題", "math") == "割合と比"
    assert unified_topic("割合・食塩水", "math") == "割合と比"
    assert unified_topic("輪軸", "science") == unified_topic("物理-かっ車・輪じく", "science")
    assert unified_topic("文章題", "math") == "文章題"
    assert unified_topic(None, "math") is None
