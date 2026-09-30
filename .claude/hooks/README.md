# Claude Code フック

このディレクトリには、開発中に使える Claude Code のフックスクリプトが入っています。**デフォルトでは有効になっていません。** 使うときは下の設定を `.claude/settings.local.json` に追加してください。

## 利用可能なフック

### ツール使用ロガー(`post-tool-use.sh`)

**目的**: すべてのツール使用をログに記録し、デバッグや Claude の動作の追跡に役立てます。

**トリガー**: 毎回のツール呼び出し(Read、Write、Edit、Bash など)の後。

**ログの場所**: `.claude/logs/tool-usage-YYYY-MM-DD.log`(`.gitignore` 済み)

**有効化**(`.claude/settings.local.json`):
```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/post-tool-use.sh\"" }] }
    ]
  }
}
```
Windows では Git Bash の `bash` が PATH にある前提です。

**ログのフォーマット**:
```
=== ツール使用: 2026-09-30 09:15:23 ===
ツール: Read
セッション: abc123
入力: {"file_path": "web/src/views/exam.js"}
レスポンス: {"content": "..."}
```

**特徴**:
- 日次ログファイルを作成し、ツール名・セッション ID・入力・レスポンスを記録します
- JSON のパースには `jq` を使います(なければ生の JSON をそのまま記録)
- ツールの実行を妨げることはありません(常に exit 0)

**注意**: レスポンス全体を記録するので、pipeline の出力や bank json を読むとログが大きくなります。デバッグが終わったら無効化してください。

**ログの確認**:
```bash
cat .claude/logs/tool-usage-$(date +%Y-%m-%d).log
grep "ツール: Bash" .claude/logs/*.log
```

## フックの無効化

`.claude/settings.local.json` から `hooks.PostToolUse` の設定を削除します。

## カスタムフックの作成

[Claude Code フックのドキュメント](https://docs.claude.com/en/docs/claude-code/hooks)を参照してください。

主なイベント: `PreToolUse` / `PostToolUse` / `UserPromptSubmit` / `Stop` / `SubagentStop` / `SessionStart` / `SessionEnd`

終了コード: `0` = 続行、`2` = ブロックしてメッセージを Claude に返す、その他 = エラー(続行)
