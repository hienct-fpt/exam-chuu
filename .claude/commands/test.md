---
description: Python(pytest)と web(vitest)のテストを実行し、レポートを作成します
---

このリポジトリのテストを実行してください:

1. **Python テスト**: `python -m pytest tests -q`(採点 grading / grader / analytics / dev_server / minsan)
2. **web テスト**: `cd web && npm test`(vitest + jsdom、mock モード)
3. **ビルド確認**: `cd web && npm run build`(Vite のビルドが通るか)

前提:
- `pipeline/out` がないと実データ依存のテストは skip される。skip の件数もレポートに含める
- web テストは `web/public/bank` が必要。なければ `python scripts/sync_assets.py` を先に実行する

実行後、次の内容をまとめてください:
- 実行数と結果(成功 / 失敗 / skip)
- 失敗したテストの原因と修正案(採点ロジックの変更が原因なら、どの answer_type か)
- 警告やビルドエラー

リント・型チェックはこのリポジトリでは設定されていないので実行しない。テストが不足している箇所(特に採点ロジックの変更)があれば、`python-tests` スキルに沿った追加テストを提案してください。
