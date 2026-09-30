---
description: 番号を自動で採番して新しいデモブランチを作成します
---

"demo-branch" という名前の新しい git ブランチを作成してください。すでに存在する場合は "demo-branch-2"、"demo-branch-3" のように番号を増やしていきます。

手順:
1. "demo-branch" が存在するか確認する: `git branch --list demo-branch`
2. 存在する場合は "demo-branch-2"、"demo-branch-3" と順に確認し、空いている名前を見つける
3. 新しいブランチを作成してチェックアウトする: `git checkout -b <branch-name>`
4. ブランチが作成されたことを確認し、現在の状態を表示する
