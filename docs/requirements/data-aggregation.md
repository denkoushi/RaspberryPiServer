# Data Aggregation API (DocumentViewer/Window A Integration)

## 1. Purpose
- RaspberryPiServerを唯一のデータ提供元とし、Window A クライアントが REST API から生産計画・標準工数・station設定・所在一覧を取得できるようにする。
- USB インポート後のデータ更新をサーバー側で一元管理し、Window A は API のみ参照する構成へ移行。

## 2. API Overview
| Endpoint | Method | 説明 |
| --- | --- | --- |
| `/api/v1/production-plan` | GET | 生産計画一覧。納期順。CSV 元データを JSON へ変換して返す。 |
| `/api/v1/standard-times` | GET | 標準工数一覧。部品番号・工程名順。 |
| `/api/v1/station-config` | GET/POST | station 設定の取得・更新。Window A からの設定変更をサーバーに集約。 |
| `/api/v1/part-locations` | GET | 最新所在一覧。既存 DB (`part_locations`) を JSON で返す。 |

- 認証: 既存の Bearer トークン方式 (`Authorization: Bearer <token>`)
- レスポンス例・エラー仕様は後続で OpenAPI 化を検討。

## 3. Data Flow
1. USB 取り込み (`tool-ingest-sync.sh`) が生産計画／標準工数 CSV を `/srv/rpi-server/data/plan/` に配置。
2. サーバー起動時またはインポート完了時に、CSV を読み込みキャッシュ（JSON）を生成。API はキャッシュから返す。
3. station 設定は `/srv/rpi-server/config/station.json` に保存し、API を通じて読み書きする。
4. 所在一覧は現在と同様、PostgreSQL `part_locations` を直接参照。

## 4. Implementation Tasks
- Flask (`app/server.py`) に上記 API を追加。必要に応じて Blueprint 分割。
- CSV キャッシュ生成モジュールを追加（`plan_cache.py` から再利用 or 移植）。
- station 設定の保存先をサーバー側に移動し、環境変数でパスを調整可能にする。
- API の単体テスト（pytest）を整備。CSV/JSON/DB のテストデータを用意。
- `docker-compose.yml` 等に必要なボリューム（`/srv/rpi-server/data`、`config`）を明示。

## 5. Open Questions
- Window A との切替期間中、USB ローカル同期を継続するか。並行運用する場合の整合性をどう担保するか。
- 生産計画／標準工数の更新頻度とキャッシュ戦略（手動 vs 自動リロード）。
- station 設定のロックや同時更新への対応。

---
このドキュメントを基に、サーバー側 API 実装を進め、Window A クライアント改修へ繋げる。
