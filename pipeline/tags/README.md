# Item tags (grade + topic)

`{exam_id}.json`:

```json
{
  "bigs":  {"3": {"grade": 6, "topic": "平面図形-相似・比"}},   // default for every item in 大問3
  "items": {"5-4": {"grade": 6}, "2-1": {"topic": "割合・食塩水"}}   // per-item override
}
```

`grade` = the school year (中学受験 塾カリキュラム基準, 予習シリーズ相当) by whose end the technique is taught:

- **4** — solvable with 小4 までの内容: 整数・小数の四則計算, 計算のくふう(分配法則), 和差算, 植木算・周期算, 角度(三角形・四角形の内角),
  正方形・長方形・三角形の面積, 倍数・約数(基本), 場合の数(書き出し), 表・グラフの読み取り, 簡単な規則性
- **5** — solvable with 小5 までの内容: 計算 (分数・小数), 割合・食塩水・売買損益, 速さ・旅人算・流水算, 仕事算,
  平均・消去算・つるかめ・集合, 平面図形の面積(円・おうぎ形), 立体の体積, 規則性, 基本の場合の数, 水量変化(基本)
- **6** — needs 小6 内容: 比と図形(相似), 速さと比, 点の移動とグラフ, 図形の移動・回転体, ニュートン算, 部分分数,
  整数の性質(階乗など), 複雑な場合の数, 仕切り付き水そうの応用

Tags are hand-assigned from the question text (`pipeline/dump_texts.py`). Adjust freely; `python pipeline/build.py` re-merges.

The web grade filter is `grade <= N` (`#/exam/{id}?g=4|5`, default from the 試験一覧 selector), so re-tagging an item
from 5 down to 4 keeps it inside "小5まで" and additionally exposes it under "小4まで". `grade_counts` in `bank/index.json`
is per grade; the web sums the buckets `<= N`.
