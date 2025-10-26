# 2025-10-26 Socket.IO 検証ログ

## 概要

- **目的**: RaspberryPiServer 上で `/api/v1/scans` 実行時に Socket.IO イベントが送出されるかを確認する。
- **対象ブランチ**: `feature/server-app`
- **対象サービス**: `app`（Flask + Flask-SocketIO + gevent + gunicorn）
- **確認者**: denkon5ssd

## 事前条件

- `docker compose` で `app` / `postgres` サービスを稼働させる。
- `/srv/rpi-server/documents/testpart.pdf` を配置済み。
- `.env` もしくは環境変数で `API_TOKEN`（未設定可）を用意する。

## 実施手順

1. イメージ再ビルドとサービス再起動（依存追加反映のため）。

    ```bash
    cd ~/RaspberryPiServer
    docker compose build app
    docker compose down
    docker compose up -d
    ```

2. アプリ起動ログの確認。

    ```bash
    cd ~/RaspberryPiServer
    docker compose logs app -n 20
    ```

3. Socket.IO リスナーを起動してイベント待機。

    ```bash
    cd ~/RaspberryPiServer
    docker compose exec -T app python /app/tests/socketio_listener.py
    ```

4. 別ターミナルから `/api/v1/scans` に対して POST 実行。

    ```bash
    cd ~/RaspberryPiServer
    curl -X POST http://127.0.0.1:8501/api/v1/scans \
      -H "Authorization: Bearer ${API_TOKEN:-raspi-token-20251026}" \
      -H "Content-Type: application/json" \
      -d '{"part_code":"testpart","location_code":"RACK-A1","device_id":"test-device"}'
    ```

## 結果

- `docker compose logs app -n 20` でエラーなし（Gunicorn + geventwebsocket ワーカー起動を確認）。
- リスナー側出力:

    ```
    part_location_updated: {...}
    scan_update: {...}
    ```

  `part_location_updated` および `scan_update` イベントが期待どおり broadcast された。
- `curl` レスポンスは HTTP 201。データベースへレコード追加されたことを確認済み。

## 所感・フォローアップ

- 問題の原因は `websocket-client` の依存漏れだったため、`app/requirements.txt` に `websocket-client==1.8.0` を追加して解消。
- Window A のクライアント側 Socket.IO エンドポイント切り替え、および継続的な自動テスト整備が今後の課題。

