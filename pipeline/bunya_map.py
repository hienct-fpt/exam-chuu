"""Map this project's own 算数 topic tags (pipeline/tags/*.json, hand-assigned, ~50 distinct labels) onto
みんなの算数オンライン (min-san)'s fixed 12-category 分野 taxonomy, so kyoritsu/shinagawa items can be compared
directly against min-san items (same category system) instead of only via free-form topic strings.

min-san's 12 leaf 分野 (pipeline/minsan.py CATS):
  db  (文章題) : 和と差, 割合と比, 数の性質, 速さ, 規則性, 場合の数, 論理・推理
  dbz (図形)   : 平面図形, 立体図形
  dbk (計算)   : 計算, 逆算, 単位換算

Grounding: for each ambiguous local label, pipeline/out/minsan/items.json (2078 problems' own `tags` +
`topic`) was checked for the closest matching keyword, and the majority 分野 it falls under there was used
(see git history of this file for the query). A few labels have no min-san precedent and are a domain-
knowledge best guess (marked below). "文章題" alone (this project's fallback label, not a min-san leaf
category) is intentionally left unmapped (None) rather than guessed.
"""
from __future__ import annotations

BUNYA_MAP: dict[str, str] = {
    # direct 1:1 with a min-san leaf category
    "数の性質": "数の性質",
    "計算": "計算",
    "規則性": "規則性",
    "場合の数": "場合の数",
    "割合と比": "割合と比",
    "速さ": "速さ",
    "論理・推理": "論理・推理",
    "単位換算": "単位換算",
    "立体図形": "立体図形",
    # grounded via min-san's own tag->topic majority (see docstring)
    "割合・食塩水": "割合と比",
    "平均": "和と差",
    "文章題-平均": "和と差",
    "仕事算": "割合と比",
    "売買損益": "割合と比",
    "流水算": "速さ",
    "速さ・旅人算": "速さ",
    "速さと比": "速さ",
    "速さとグラフ": "速さ",
    "通過算": "速さ",
    "時計算": "速さ",
    "植木算": "規則性",
    "文章題-植木算": "規則性",
    "暦・周期": "規則性",
    "虫食い算": "論理・推理",
    "集合": "和と差",
    "文章題-集合": "和と差",
    "つるかめ算": "和と差",
    "文章題-消去算": "和と差",
    "和差算・分配": "和と差",
    "ニュートン算": "割合と比",
    "比例・ばね": "割合と比",
    "約束記号": "逆算",
    "計算-部分分数": "計算",
    "平面図形-面積": "平面図形",
    "平面図形-相似・比": "平面図形",
    "平面図形-角度": "平面図形",
    "角度": "平面図形",
    "図形の移動": "平面図形",
    "図形の移動・回転": "平面図形",
    "縮尺・面積": "平面図形",
    "立体の体積": "立体図形",
    "立体図形-回転体": "立体図形",
    "立体-展開図": "立体図形",
    "立体-切断": "立体図形",
    # no min-san precedent found for the exact concept -> best domain-knowledge guess
    "点の移動とグラフ": "平面図形",
    "水量変化とグラフ": "立体図形",  # 水そう(立体)の水位グラフ, distinct from the simple L/mL "単位換算" tag
    "立体-水量": "立体図形",
    "位置・方角": "平面図形",
    "概数": "数の性質",
    # intentionally unmapped: generic fallback label, not a min-san leaf category
    "文章題": None,
}


def bunya_for(topic: str | None) -> str | None:
    """min-san-compatible 分野 for a local topic tag, or None if unmapped/untagged."""
    if not topic:
        return None
    return BUNYA_MAP.get(topic)
