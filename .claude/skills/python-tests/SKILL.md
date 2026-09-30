---
name: python-tests
description: exam-chuu の pytest テスト(tests/ 配下: 採点ロジック examcore/grading、grader、analytics、dev_server、minsan)を書く・直すときのガイドライン。採点ルールや answer_type を追加・変更したとき、Cloud Functions や pipeline のロジックにテストを足すときに使う。
---

# pytest テストのガイドライン

exam-chuu の Python テストは `tests/` 直下に置き、`python -m pytest tests -q` で実行します(`scripts/deploy.sh` もデプロイ前にこれを実行し、失敗したらデプロイを止めます)。HTTP サーバーや Firebase エミュレーターは使いません。**純粋関数を直接 import して呼ぶ**のが基本です。

## ファイル構成

```
tests/
├── test_grading.py     # functions/examcore/grading.py: parse_number / parse_ratio / normalize / grade()
├── test_grader.py      # functions/grader.py: grade_submission(), 小5サブセット, perBig/perTopic/perGrade
├── test_analytics.py   # functions/analytics.py: outcomes, topic_stats, weak_topics, practice_set, weekly_series
├── test_dev_server.py  # scripts/dev_server.py: grade() / stats() を実データで end-to-end
└── test_minsan.py      # pipeline/minsan.py: 一覧 HTML のパース、50分セットの詰め方
```

新しいモジュールをテストするときは `test_<module>.py` を作ります。関連するテストは同じファイルにまとめ、クラスは使わず**トップレベルの関数**で書きます(既存に合わせる)。

## import の書き方

`functions/`・`scripts/`・`pipeline/` はパッケージではないので、`sys.path` に追加してから import します。

```python
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))

from examcore.grading import grade, parse_number  # noqa: E402
from grader import grade_submission  # noqa: E402
```

`firebase_admin` / `firebase_functions` に依存する `functions/main.py` は直接 import しません。テストしたいロジックは `grader.py` / `analytics.py` / `examcore/` の純粋関数に切り出してからテストします。

## パイプライン出力への依存

実データ(`pipeline/out/bank/*.json`, `pipeline/out/answers_all.json`)を使うテストは、出力がなければ **skip** します。

```python
OUT = ROOT / "pipeline" / "out"

@pytest.fixture
def exam_and_keys():
    bank = OUT / "bank" / "kyoritsu_2026_2-1_math.json"
    if not bank.exists():
        pytest.skip("run pipeline first")
    ...

# モジュール全体で必要なとき
if not (ROOT / "pipeline" / "out" / "bank" / "index.json").exists():
    pytest.skip("run pipeline first", allow_module_level=True)
```

JSON は必ず `read_text(encoding="utf-8")` で読みます(Windows のデフォルトは cp932)。

## パターン

### 1. 解答の正規化 → `parametrize`

全角・単位・帯分数などの揺れは表形式で並べます。**正解になるべきもの**と**正解になってはいけないもの**の両方を書きます。

```python
@pytest.mark.parametrize("s,expect", [
    ("１　３/２２", Fraction(25, 22)),   # 全角 + 帯分数
    ("132秒後", Fraction(132)),          # 単位つき
    ("ウ", None),
    ("3/0", None),
])
def test_parse_number(s, expect):
    assert parse_number(s) == expect
```

### 2. answer_type ごとの `grade()`

キーは bank / answers と同じ形の dict で直接組み立てます。

```python
def test_grade_set_is_order_free():
    key = {"answer_type": "set", "answer": "A・D"}
    assert grade(key, "D・A").correct
    assert not grade(key, "A").correct
```

| answer_type | 必ず確認すること |
|---|---|
| number / fraction / ratio | 有理数で一致(`7.20` = `36/5`)、比は約分、誤答が通らない |
| choice / text | 正規化後の一致、`variants`(別解・読み) |
| set / sequence | 順不同 / 順序あり |
| multi | パートごとの `partsCorrect`、`ア・ウ` は順不同、`a\|b` は別解 |
| essay / manual | `pending` になり自動で正誤を付けない、`manual_grades` で再採点 |

### 3. `grade_submission()` の集計

```python
def test_partial_and_blank(exam_and_keys):
    exam, keys = exam_and_keys
    r = grade_submission({"1-1": "２３／１２０"}, keys, exam)
    assert r["perItem"]["1-1"]["correct"]
    assert not r["perItem"]["2-1"]["answered"]
    assert r["answeredCount"] == 1
```

- `score` / `max` / `percent` / `answeredCount` / `pendingCount`
- `perBig` / `perTopic` / `perGrade` の件数
- `item_ids`(小5サブセット: 範囲外の解答は無視される)、`full_ids=True`(練習セット: `exam#slot` キー)
- `points`(配点、kawasaki)

### 4. analytics は小さな合成データで

attempt を手で組み立てるヘルパーを使い、日時は固定します(`now=` を渡す)。

```python
def _attempt(day, exam, per_item):
    return {"status": "graded", "examId": exam, "submittedAt": f"2026-09-{day:02d}T10:00:00+00:00",
            "result": {"perItem": per_item}}
```

### 5. pipeline のパーサーは HTML/テキスト断片を埋め込む

`test_minsan.py` のように、ネットワークにアクセスせず、最小限の入力文字列をテスト内に書きます。

## 命名

- `test_<関数>_<条件>`(例: `test_grade_ratio`, `test_subset_grade5_only`, `test_parse_list_handles_both_markup_generations`)
- 回帰テストには、どのデータで壊れたかをコメントで残す(例: `# chuo 2026 社会 1-3: 全角ハイフン`)

## 実行

```bash
python -m pytest tests -q                         # 全部
python -m pytest tests/test_grading.py -q         # 1 ファイル
python -m pytest tests -k ratio -q                # 名前で絞り込み
```

web 側のテストは別: `cd web && npm test`(vitest + jsdom、`scripts/sync_assets.py` 実行済みが前提)。

## まとめ

- 採点ロジックを変えたら**必ず** `test_grading.py` / `test_grader.py` にケースを足す(誤って正解にするケースも)
- 純粋関数を直接呼ぶ。Firebase には触れない
- 実データ依存のテストは出力がなければ skip
- UTF-8 を明示する
