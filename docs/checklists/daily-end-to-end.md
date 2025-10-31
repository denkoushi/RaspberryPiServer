# Window A エンドツーエンド確認チェックリスト

RaspberryPiServer (Pi5) と Window A (Pi4) の間で、USB → REST → Socket.IO → DocumentViewer 表示までの流れを日次点検・トラブルシュート用にまとめたチェックリスト。

## 事前準備
- Pi5 のホスト名が `raspi-server` に設定されている（`hostnamectl` で確認）。
- Pi5 で Docker / `docviewer` アプリが稼働中 (`sudo docker compose ps`)。
- Pi4 には `tool-management-system02` と `DocumentViewer` が配置済み。

## 手順
1. **Pi4 から mDNS 疎通確認** (`scripts/check_e2e_scan.sh` でも実行可)
   ```bash
   ping -c 2 raspi-server.local
   ```
   - 返答がない場合: Pi5 のホスト名設定と Pi4 の Avahi (`systemctl status avahi-daemon`) を確認。

2. **REST API 動作確認**
   ```bash
   curl -s -X POST http://raspi-server.local:8501/api/v1/scans \
     -H "Authorization: Bearer ${API_TOKEN:-raspi-token-20251027}" \
     -H "Content-Type: application/json" \
     -d '{
           "part_code": "testpart",
           "location_code": "RACK-A1",
           "device_id": "window-a-test"
         }'
   ```
   - 期待結果: `"accepted": true` / `HTTP 201`。
   - エラー時: Pi5 のコンテナログ（`sudo docker compose logs app -n 50`）を確認。
   - Pi4 では `./scripts/check_e2e_scan.sh` を実行すると 1〜2 のチェックをまとめて実施できる。

3. **Socket.IO イベント確認（Pi5）**
   ```bash
   cd ~/RaspberryPiServer
   sudo docker compose exec -T app python /app/tests/socketio_listener.py
   ```
   - `part_location_updated` / `scan_update` の JSON が表示されること。
   - 受信後は `Ctrl+C` で終了。

4. **Viewer 表示確認（Pi4）**
   - ブラウザで `http://localhost:8501/viewer` を開き、`testpart.pdf` が表示されること。
   - 必要に応じて `tail -n 20 /var/log/document-viewer/import.log` を確認。

5. **構内物流タブの更新確認（Pi4 → Pi5）**
   ```bash
   curl -s -X POST http://raspi-server.local:8501/api/logistics/jobs \
     -H "Authorization: Bearer ${API_TOKEN:-raspi-token-20251027}" \
     -H "Content-Type: application/json" \
     -d '{
           "job_id": "job-e2e-$(date +%s)",
           "part_code": "testpart",
           "from_location": "RACK-A1",
           "to_location": "RACK-B1"
         }'
   ```
   - Pi4 の右ペイン「構内物流」タブで件数バッジと最終更新時刻が増分され、`搬送更新: ...` のメッセージが表示されることを確認。
   - Pi5 では `/srv/rpi-server/logs/logistics_audit.log` に `status_update` もしくは `create` の監査ログが追加される。Socket.IO 監視中であれば `logistics_job_updated` が受信される。

## ログ確認コマンド一覧
- Pi5 アプリケーションログ: `cd ~/RaspberryPiServer && sudo docker compose logs app -n 50`
- Pi4 DocumentViewer インポートログ: `sudo tail -n 20 /var/log/document-viewer/import.log`

## トラブル発生時のヒント
- mDNS が解決できない場合は `/etc/hosts` を空にし、Avahi の再起動 (`sudo systemctl restart avahi-daemon`) を試す。
- REST がタイムアウトする場合は Pi5 の Docker サービス状態 (`sudo systemctl status docker`) を確認。
- Viewer が更新されない場合はブラウザの Socket.IO ステータスを確認し、必要であればページを再読込みする。
