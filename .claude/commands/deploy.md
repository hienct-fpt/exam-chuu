---
description: Firebase(Hosting / Functions / Firestore)へデプロイし、試験データと解答キーを取り込みます
---

`scripts/deploy.sh` で本番(Firebase)にデプロイしてください。引数はそのまま `deploy.sh` に渡します(例: `/deploy --skip-import`)。

| オプション | 内容 |
|---|---|
| (なし) | pytest → sync_assets → web ビルド → firestore rules/indexes・functions・hosting をデプロイ → `import_bank.py` |
| `--full` | 先に `pipeline/run_all.py` で全パイプラインを再生成(遅い・元 PDF が必要) |
| `--minsan` | 先に min-san のバンクを再構築(`minsan.py build` + `build.py`) |
| `--skip-import` | Firestore への試験・解答キーの取り込みを省略(hosting / functions だけ更新) |
| `--skip-tests` | pytest ゲートを省略(原則使わない) |
| `--project ID` | Firebase プロジェクト(既定は `.firebaserc` の default) |

手順:
1. **事前確認**(問題があれば止めてユーザーに伝える):
   - `git status --short` で未コミットの変更を一覧し、そのままデプロイしてよいかユーザーに確認する
   - `.firebaserc` のプロジェクト ID を表示する
   - `firebase --version` が通ること、`functions/venv` があること(なければ README §3 の作成コマンドを案内)
   - `import_bank.py` を実行する場合は gcloud の認証が必要。未認証なら `! gcloud auth application-default login` をユーザーに案内する
2. **ユーザーの明示的な承認を得てから**実行する: `bash scripts/deploy.sh <引数>`(時間がかかるのでバックグラウンドで実行し、完了を待つ)
3. 結果を報告する:
   - 各ステップ(pytest、sync、build、firebase deploy、import)の成否
   - 失敗した場合はエラー出力の要点と対処案(途中で失敗したらそれ以降は実行されていない)
   - 成功した場合は URL `https://<project>.web.app`

注意:
- デプロイは本番に即時反映され、元に戻すには再デプロイが必要。**ユーザーの承認なしに実行しない**
- 解答キー(`pipeline/out/answers_all.json`)は `import_bank.py` で Firestore の `answerKeys` にだけ入る。Hosting に出る `web/public/bank` に答えが含まれていないことは `build.py` が保証している
- `kumiwake_past/` の 回答.pdf・結果.pdf(子どもの答案・成績)はデプロイ対象外。`web/public` に紛れ込んでいないか気になる場合は `grep -rl "kumiwake_past" web/public/bank` で確認する
