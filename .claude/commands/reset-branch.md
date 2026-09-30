---
description: main に切り替えて、直前のブランチを削除します
---

main ブランチに戻り、それまで作業していたブランチをコミットや変更ごと削除してください。削除するブランチに紐づく PR があれば、あわせてクローズします。

手順:
1. `git branch --show-current` で現在のブランチを確認する
2. すでに main にいる場合は、リセットは不要だとユーザーに伝えて終了する
3. フィーチャーブランチにいる場合:
   - 失われるコミットと変更を表示する: `git log main..HEAD --oneline` と `git status --short`
   - **ユーザーに確認を取ってから**次に進む
   - PR があればクローズする: `gh pr list --head <branch-name> --state open` → `gh pr close <number>`(`gh` がなければスキップして伝える)
   - 追跡ファイルの変更を破棄する: `git reset --hard HEAD`
   - main に切り替える: `git checkout main`
   - ブランチを削除する: `git branch -D <branch-name>`
   - 結果を表示する: `git status` と `git branch`

注意:
- `git clean` は実行しない。このリポジトリには git 管理外の大事なファイル(`*_past/` の過去問 PDF、`pipeline/in/`、`web/.env.local`、`functions/.env`)がある。未追跡ファイルの削除が必要なら、対象を一覧してユーザーに確認する
- フィーチャーブランチとそのコミット・変更は完全に削除され、PR もクローズされる
