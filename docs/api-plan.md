# Data Aggregation API Plan (RaspberryPiServer)

## Summary
- エンドポイント: `/api/v1/production-plan`, `/api/v1/standard-times`, `/api/v1/station-config`, `/api/v1/part-locations` を追加済み。Window A が REST API でデータ取得できる。
- 認証: 既存の Bearer トークン (`Authorization: Bearer <token>`)。今後 OpenAPI 化を検討。

## 1. Production Plan
- **Endpoint**: `GET /api/v1/production-plan`
- **Query params**: なし
- **Response**:
  ```json
  {
    "label": "生産計画",
    "entries": [
      {
        "納期": "2025-01-01",
        "個数": "10",
        "部品番号": "PART-1",
        "部品名": "部品A",
        "製番": "JOB-1",
        "工程名": "切削"
      }
    ],
    "updated_at": "2025-10-26T00:00:00Z",
    "error": null
  }
  ```
- `entries` が空、または `error` にメッセージが入る場合は Window A 側でフェイルセーフ（従来 CSV または空データ表示）を行う。

## 2. Standard Times
- **Endpoint**: `GET /api/v1/standard-times`
- Response は上記と同形で `entries` が標準工数の配列。

## 3. Station Config
- **GET /api/v1/station-config**
  ```json
  {
    "process": "切削",
    "available": ["切削", "研磨"],
    "updated_at": "2025-10-26T00:00:00Z"
  }
  ```
- **POST /api/v1/station-config**
  - Request Body: `{"process": "切削", "available": ["切削", "研磨"]}`
  - Response: 更新後の JSON（`updated_at` は現在時刻で上書き）。
  - `available` は空→[]、`process` は空文字で許容。型違いの場合は `400 Bad Request`。

## 4. Part Locations
- **Endpoint**: `GET /api/v1/part-locations?limit=200`
  ```json
  {
    "entries": [
      {
        "order_code": "ABC",
        "location_code": "RACK-1",
        "device_id": null,
        "last_scan_id": "scan-...",
        "scanned_at": "2025-10-26T12:34:56Z",
        "updated_at": "2025-10-26T12:34:56Z"
      }
    ]
  }
  ```
- `limit` は 1〜1000 の範囲に制限。範囲外や不正値は `400 Bad Request`。

## Notes
- CSV 読み込み `PLAN_DATA_DIR` は `/srv/rpi-server/data/plan`（環境変数で変更可）。
- station 設定ファイル `STATION_CONFIG_PATH` は `/srv/rpi-server/config/station.json`。
- `/internal/plan-cache/refresh` エンドポイントで `PlanCache` をリフレッシュし、`tool-ingest-sync.sh` から自動呼び出し済み。
- 今後: OpenAPI ドキュメント整備と Window A 側の API 切り替え実装を進める。
