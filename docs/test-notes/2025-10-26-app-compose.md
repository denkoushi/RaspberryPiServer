# 2025-10-26 REST API / Pi Zero 結合テスト

## 目的
- RaspberryPiServer の Docker Compose (`postgres` + `app`) を起動し、REST API `/api/v1/scans` と `/healthz` の動作を確認する。
- OnSiteLogistics (Pi Zero) から実データを送信し、PostgreSQL の `part_locations` に反映されることを確認する。

## 手順
1. `.env` を作成し、`POSTGRES_USER=app` / `POSTGRES_PASSWORD=app_password` / `POSTGRES_DB=appdb` を設定。
2. `sudo docker compose up -d` で `postgres` / `app` を起動。
3. `sudo docker compose ps` で両サービスが `running (healthy)` であることを確認。
4. `curl http://127.0.0.1:8501/healthz` → `{"status":"ok"}` を確認。
5. OnSiteLogistics (Pi Zero) の `/etc/onsitelogistics/config.json` を `api_url=http://raspi-server.local:8501/api/v1/scans` に更新。
6. Pi Zero にて
   ```bash
   cd ~/OnSiteLogistics
   sudo PYTHONPATH=/home/denkonzero/e-Paper/RaspberryPi_JetsonNano/python/lib \\
     python3 scripts/handheld_scan_display.py
   ```
   バーコードを 2 回読み込み（`Status: DONE` 表示）後、`Ctrl+C` で終了。
7. `sqlite3 ~/.onsitelogistics/scan_queue.db 'SELECT COUNT(*) FROM scan_queue'` → 0 を確認。
8. RaspberryPiServer 側で
   ```bash
   sudo docker exec -it postgres \\
     psql -U app -d appdb \\
     -c "SELECT order_code, location_code, updated_at FROM part_locations ORDER BY updated_at DESC LIMIT 5;"
   ```
   を実行し、最新データが反映されていることを確認。

## 結果
- `/healthz` が `status=ok` を返し、REST API が正常に応答した。
- Pi Zero から送信した `bambulab://...` / `4573252947585` のデータが `part_locations` に取り込まれた。
- 再送キューは 0 件となり、`handheld.log` に `Server accepted scan ...` が記録された。

## メモ
- Pi Zero の `/etc/hosts` へ `192.168.128.128 raspi-server.local` を追記し名前解決を行った。
- 今後、本番運用時は `.env` に `API_TOKEN` を設定し、Pi Zero 側でも同一トークンを利用する。
- エラーハンドリング（必須項目不足、400/500 応答時の再送挙動）は別タスクで追加検証予定。
