---
description: ローカル開発サーバー(mock 採点サーバー + Vite)を停止します
---

ポート 8790(`scripts/dev_server.py`)と 5173(Vite)で動いているプロセスを見つけて停止してください。

- Windows: `netstat -aon | findstr :8790` / `findstr :5173` で PID を調べてから `taskkill /F /PID <pid>`
- macOS/Linux: `lsof -ti:8790,5173 | xargs kill 2>/dev/null || true`
