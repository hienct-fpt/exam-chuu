---
description: コードベースの未使用コードと非効率な箇所を洗い出して整理します
---

# コードベースの最適化

次の範囲を対象に最適化を実施してください: `functions/`, `web/src/`, `scripts/`, `pipeline/*.py`。
**対象外**: `pipeline/out/`, `pipeline/in/`, `web/public/`, `web/dist/`, `*_past/`, `node_modules/`, `functions/venv/`(生成物・元データ)。

1. **洗い出す**:
   - 未使用の関数、変数、import、`style.css` の未使用クラス
   - デッドコード、コメントアウトされたコード
   - `web/package.json`, `requirements.txt`, `functions/requirements.txt` の未使用依存
   - 重複コード(例: 各 view にコピーされている `esc()` など、共通化すべきか判断する)

2. **分析する**:
   - bank json の重複読み込み、Firestore の読み取り回数(ループ内の get)
   - pipeline の重い処理の無駄な再実行
   - エラーハンドリングの漏れ

3. **整理する**: 未使用だと確信できるものだけ削除する。pipeline の学校別ルール(`SUBJECT_RULES` など)は一見未使用でも特定の試験で使われるので、`pipeline/out/exams.json` と突き合わせてから判断する。

4. **検証する**: `python -m pytest tests -q` と `cd web && npm test && npm run build` が通ること。

5. **サマリーを報告する**:
   - 削除した内容(ファイルの場所つき)
   - 最適化した内容(変更前後)
   - さらなる改善の提案、テストしておくべき点
