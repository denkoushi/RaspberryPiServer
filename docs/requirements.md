# RaspberryPiServer 要件・決定事項

最終更新: 2025-11-02  
一次情報は本ファイルで一元管理し、詳細な手順や履歴はリンク先ドキュメントを参照する。

## 1. ゴール
- Window A（tool-management-system02）は DocumentViewer／工具管理 UI などのクライアント機能に専念し、サーバー処理は RaspberryPiServer（Pi5）へ集約する。
- RaspberryPiServer は REST / Socket.IO / PostgreSQL / USB 配布・バックアップを統合し、Pi Zero 2 W（ハンディ）からのスキャンを唯一の受信点とする。
- Pi Zero 2 W は `mirrorctl`／`mirror_compare` による 14 日連続健全性チェックを完了した状態で本番切替を行う。
- RUNBOOK・systemd・USB 運用を整備し、旧 Window A サーバーを安全に退役できる状態にする。

## 2. 構成と責務

| コンポーネント | 主な責務 | 参照ドキュメント |
| --- | --- | --- |
| RaspberryPiServer (Pi5) | API / Socket.IO / DB / USB 運用のハブ | `RUNBOOK.md`, `docs/implementation-plan.md`, `docs/mirror-verification.md` |
| Window A (Pi4) | クライアント表示（DocumentViewer iframe、所在一覧、構内物流 UI 等） | Window A リポジトリ `docs/right-pane-plan.md`, `docs/docs-index.md` |
| Pi Zero 2 W | ハンディ送信専用端末、`mirrorctl` 管理対象 | OnSiteLogistics `docs/handheld-reader.md`, RaspberryPiServer `docs/mirrorctl-spec.md` |

## 3. ステータス一覧

| 機能領域 | 現状ステータス | 次アクション | 参照 |
| --- | --- | --- | --- |
| DocumentViewer 移行 | ⚙ 稼働中（Pi5 で `/viewer`・Socket.IO を提供） | 1. Window A の systemd drop-in / `.env` を Pi5 向けに確定（`SOCKET_STATUS_WATCHDOG`・トークン含む）<br>2. RUNBOOK と `docs/documentviewer-migration.md` へウォッチドッグ／PDF バインドマウント注意点を反映<br>3. Pi4・Pi5・DocumentViewer の 14 日連続可用性チェック手順を `docs/test-notes/` へ追加 | `docs/documentviewer-migration.md`, `DocumentViewer/docs/test-notes/2025-10-26-viewer-check.md` |
| 工具管理 UI クライアント化 | ⏳ 進行中（UI/REST プロキシ集約を設計） | 1. Window A の API 参照先を Pi5 へ統一し、旧サーバー経由コードを削除<br>2. クライアント専用品の systemd 定義と RUNBOOK を整理<br>3. Socket.IO / REST テストログを `docs/test-notes/` へ追記（2025-11-02 viewer highlight 実機検証を記録済） | Window A `docs/right-pane-plan.md`, `docs/implementation-plan.md` |
| USB INGEST / DIST / BACKUP 集約 | ⏳ 設計中（スクリプト雛形あり） | 1. `docs/usb-operations.md` を RUNBOOK へ反映し、役割別 USB ラベル運用を確定<br>2. `udev` / systemd timer スクリプトを実装してテスト<br>3. Pi5↔Pi4 で DIST リハーサルを実施し証跡を `docs/test-notes/` へ残す | `docs/usb-operations.md`, `RUNBOOK.md` |
| ミラー 14 日連続チェック | ▶ 準備中（`mirrorctl` CLI/Timer 実装済み） | 1. Pi Zero 実機へ `mirrorctl enable` を配備し、初期疎通を確認<br>2. `docs/templates/test-log-mirror-daily.md` を用いた記録サイクルを整備<br>3. 14 日分のログを収集後に判定会議へ提出 | `docs/mirror-verification.md`, `docs/templates/test-log-mirror-daily.md` |
| 旧 Window A サーバー退役 | ⏸ 未着手 | 1. 退役対象サービスと依存を棚卸しし、RUNBOOK に停止手順を追記<br>2. ロールバック（Pi4 単独復帰）手順をテストノート化<br>3. 切替判定の意思決定記録を Decision Log へ追加 | `RUNBOOK.md`, `docs/archive/2025-10-26-client-cutover.md` |

ステータス表記: ✅ 完了 / ⚙ 稼働中 / ⏳ 進行中 / ▶ 準備中 / ⏸ 未着手

### 3.1 次の着手順序（2025-11-02 時点）

1. DocumentViewer 移行タスク 1〜3 を完了し、Window A 環境とテストログを最新化する。  
2. 工具管理 UI クライアント化タスクを実施し、Window A 側から旧サーバー依存を排除する。  
3. USB INGEST / DIST / BACKUP 集約タスクを順に進め、Pi5 を中心とした配布フローを実稼働させる。  
4. ミラー 14 日連続チェックを開始し、テンプレート通りにエビデンスを蓄積する。  
5. 旧 Window A サーバー退役のための停止・ロールバック手順を固め、Decision Log で切替判定を行う。

## 4. 決定事項（Decision Log）

| 日付 (YYYY-MM-DD) | 区分 | 内容 |
| --- | --- | --- |
| 2025-02-xx | アーキテクチャ | Docker Compose + PostgreSQL コンテナ構成を継続し、永続データは `/srv/rpi-server/postgres` を bind mount して保管する。 |
| 2025-02-xx | 構成 | OnSiteLogistics 受信 API と工具管理アプリを Pi5 へ集約し、DocumentViewer はクライアント（Window A）で表示のみ行う。 |
| 2025-02-xx | データ運用 | USB メモリ同期を継続。サーバー側で INGEST / DIST / BACKUP の役割を切り分け、USB → サーバー更新後にクライアントへ配布する。 |
| 2025-02-xx | USB 識別 | USB メモリはラベル + シグネチャファイル（例: `/.toolmaster/role`）で役割判定し、想定外の媒体は処理を中断する。 |
| 2025-02-xx | systemd | `raspi-server.service` は `docker.service` に依存し、`Restart=on-failure` / `OnFailure=` で復旧スクリプトを呼び出す。 |
| 2025-02-xx | ログ | 運用ログは `/srv/rpi-server/logs/` に保存し、USB には書き出さない。日次で `docs/checklists/weekly-log-review.md` を用いて点検する。 |
| 2025-02-xx | バックアップ | SSD 上で日次スナップショット（7 世代）を保持し、`TM-BACKUP` USB 挿入時に最新スナップショットを `tar + zstd` で転送する。 |

> 日付は確定時に更新すること。新たな決定事項は表へ追記し、関連ドキュメントへリンクする。

## 5. 未解決課題
- USB スクリプトに必要な依存パッケージ (`rsync`, `jq`, `tar`, `zstd`) の導入手順とロールバックフローを RUNBOOK へ統合。
- API トークン管理を共通化し、発行・ローテーション履歴をログへ記録する仕組みを整備（`docs/security-overview.md` 更新を含む）。
- `logrotate` 設定と監視スクリプト（`toolmaster-status` 仮称）を整備し、失敗時の通知経路を決定。
- Pi Zero 実機での `mirrorctl` 自動テストを準備し、14 日連続チェック開始後の証跡を `docs/templates/` を用いて管理。
- TLS / DNS 方針（mDNS から固定 DNS/TLS への移行計画）を `docs/architecture.md` に反映。
- macOS 開発環境で `/srv/rpi-server/documents` を bind mount する手順をドキュメント化し、本番 Pi5 とパスの不一致による 404 を防止。

## 6. 参照ドキュメント
- `docs/docs-index.md` — 全ドキュメントの索引
- `docs/implementation-plan.md` — リポジトリ別の詳細ロードマップ
- `docs/documentviewer-migration.md` — DocumentViewer 移行状況
- `docs/mirror-verification.md` — 14 日検証手順
- `docs/mirrorctl-spec.md` — `mirrorctl` / `mirror_compare` の仕様
- `docs/usb-operations.md` — USB 運用フロー
- `docs/archive/2025-10-26-client-cutover.md` — 過去作業ログ（参照専用）
