# 2025-10-26 Docker Compose (appサービス) 起動確認

## 目的
- RaspberryPiServer の Docker Compose (`postgres` + `app`) を起動し、REST API `/api/v1/scans` と `/healthz` の動作を確認する。

## 手順履歴
1. `.env` を作成し、`DATABASE_URL=postgresql://app:app_password@postgres:5432/appdb` を設定。
2. `sudo docker compose up -d` で `postgres` / `app` を起動。
3. `sudo docker compose ps` で両サービスが `running (healthy)` であることを確認。
4. `curl http://127.0.0.1:8501/healthz` → `{"status":"ok"}` を確認。
5. `curl -X POST http://127.0.0.1:8501/api/v1/scans -H 'Content-Type: application/json' -d '{"part_code":"TEST-001","location_code":"SHELF-01"}'` を実行し、201 応答と `accepted:true` を確認。
6. `psql` で `SELECT * FROM part_locations;` を実行し、`TEST-001` 行が追加されていることを確認。
7. `sudo docker compose down` でコンテナを停止。

## 結果
- すべてのステップが成功。`part_locations` への upsert と `/healthz` の疎通を確認済み。
- API トークン未設定時の挙動を確認。今後本番運用では `.env` に `API_TOKEN` を定義し、クライアント側にも適用する必要がある。

## メモ
- 次回再確認時は `API_TOKEN` を有効化したケース、およびエラーハンドリング（不正 JSON、必須フィールド不足）を追加検証する。
