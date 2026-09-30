#!/bin/bash

# Claude Code の post-tool-use フック
# デバッグと動作追跡のため、すべてのツール使用をファイルに記録します

# ログディレクトリがなければ作成する(.claude/logs、git 管理外)
LOGS_DIR="${CLAUDE_PROJECT_DIR}/.claude/logs"
mkdir -p "$LOGS_DIR"

# 日付つきのログファイルパス
LOG_FILE="${LOGS_DIR}/tool-usage-$(date +%Y-%m-%d).log"

# 標準入力から JSON を読み込む
INPUT=$(cat)

# jq が使える場合は jq で、なければ簡易的な方法で主要フィールドを取り出す
if command -v jq &> /dev/null; then
    # jq できれいに JSON をパースする
    TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"')
    SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')
    TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}')
    TOOL_RESPONSE=$(echo "$INPUT" | jq -c '.tool_response // {}')

    # 整形されたログエントリを作成する
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    echo "=== ツール使用: $TIMESTAMP ===" >> "$LOG_FILE"
    echo "ツール: $TOOL_NAME" >> "$LOG_FILE"
    echo "セッション: $SESSION_ID" >> "$LOG_FILE"
    echo "入力: $TOOL_INPUT" >> "$LOG_FILE"
    echo "レスポンス: $TOOL_RESPONSE" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"

else
    # フォールバック: JSON をパースせず、そのまま記録する
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    echo "=== ツール使用: $TIMESTAMP ===" >> "$LOG_FILE"
    echo "$INPUT" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
fi

# ツールの実行は常に許可する
exit 0
