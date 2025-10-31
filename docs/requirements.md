# RaspberryPiServer 要件・決定事項

最終更新: 2025-10-31  
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
| DocumentViewer 移行 | ⚙ 稼働中（Pi5 で `/viewer`・Socket.IO を提供） | Window A 側の環境ファイルを Pi5 参照に切替え、テストログ更新 | `docs/documentviewer-migration.md`, `DocumentViewer/docs/test-notes/2025-10-26-viewer-check.md` |
| 工具管理 UI クライアント化 | ⏳ 進行中（UI/REST プロキシ集約を設計） | Window A 側で API 参照先を Pi5 に統一し、不要なサーバー処理を停止 | Window A `docs/right-pane-plan.md`, `docs/implementation-plan.md` |
| USB INGEST / DIST / BACKUP 集約 | ⏳ 設計中（スクリプト雛形あり） | `docs/usb-operations.md` を RUNBOOK へ反映し、ラベル運用と udev イベントを実装 | `docs/usb-operations.md`, `RUNBOOK.md` |
| ミラー 14 日連続チェック | ▶ 準備中（`mirrorctl` CLI/Timer 実装済み） | Pi Zero 実機で `mirrorctl enable` → 日次検証を開始し、テンプレートへ記録 | `docs/mirror-verification.md`, `docs/templates/test-log-mirror-daily.md` |
| 旧 Window A サーバー退役 | ⏸ 未着手 | サービス停止手順・ロールバック手順を RUNBOOK へ追記し、切替判定を Decision Log に記録 | `RUNBOOK.md`, `docs/archive/2025-10-26-client-cutover.md` |

ステータス表記: ✅ 完了 / ⚙ 稼働中 / ⏳ 進行中 / ▶ 準備中 / ⏸ 未着手

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

## 6. 参照ドキュメント
- `docs/docs-index.md` — 全ドキュメントの索引
- `docs/implementation-plan.md` — リポジトリ別の詳細ロードマップ
- `docs/documentviewer-migration.md` — DocumentViewer 移行状況
- `docs/mirror-verification.md` — 14 日検証手順
- `docs/mirrorctl-spec.md` — `mirrorctl` / `mirror_compare` の仕様
- `docs/usb-operations.md` — USB 運用フロー
- `docs/archive/2025-10-26-client-cutover.md` — 過去作業ログ（参照専用）
