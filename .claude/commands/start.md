---
description: ローカル開発サーバー(mock 採点サーバー + Vite)を起動します
---

ポート 8790 と 5173 で動いている既存のサーバーを停止してから、次の 2 つをバックグラウンドで起動してください。

**mock 採点サーバー(:8790):** `python scripts/dev_server.py`
**フロントエンド(Vite, :5173):** `cd web && npm run dev:mock`

引数 `student` が渡された場合は、フロントエンドを `npm run dev:mock:student`(生徒ビュー)で起動します。

前提: `web/public/bank` がなければ先に `python scripts/sync_assets.py` を実行する(`pipeline/out` が必要)。`web/node_modules` がなければ `cd web && npm install`。

ポートを使用中のプロセスを停止する方法(Windows):
- `netstat -aon | findstr :8790` / `findstr :5173` で PID を調べてから `taskkill /F /PID <pid>`

起動後、次の URL で動作を確認してください:
- フロントエンド: http://localhost:5173 (mock モード、ログイン不要、テスト生徒 = 保護者ビュー)
- mock 採点 API: Vite が `/api/*` を :8790 に proxy する
