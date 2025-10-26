# 実装ロードマップ（RaspberryPiServer 移行計画）

この文書は RaspberryPiServer を中心としたサーバー集約後の実装タスクを整理し、各リポジトリでの作業内容・ブランチ戦略・検証ポイントを示す。

## 1. 概要
- 現行運用: Window A（tool-management-system02）がサーバー役割を担い、Window B（DocumentViewer）、Window D（OnSiteLogistics）が連携。
- 目標: RaspberryPiServer（Window E）へサーバー機能を集約し、USB メモリ運用・バックアップ・ミラー検証を統一する。
- ブランチ運用: 各リポジトリで作業開始時に専用ブランチを作成し、現行環境へ即時復帰できる状態を維持する。

## 2. リポジトリ別タスク一覧

### 2.1 RaspberryPiServer（Window E）

| フェーズ | 作業内容 | ブランチ例 | 検証ポイント |
| --- | --- | --- | --- |
| Doc | `docs/requirements.md` / `docs/architecture.md` / `docs/usb-operations.md` / `docs/mirror-verification.md` 整備 | `feature/server-ops-docs` | ドキュメントレビュー |
| Impl-1 | Docker Compose, systemd ユニット、ログ設計の実装 | `feature/server-stack` | `systemctl status`、`docker compose ps` |
| Impl-2 | USB スクリプト（INGEST/DIST/BACKUP）と udev 連携 | `feature/usb-scripts` | テスト用ループバックデバイスで差分検証 |
| Impl-3 | ミラー比較スクリプト、`mirrorctl` CLI | `feature/mirror-tools` | 日次比較のシミュレーション、ログ確認 |
| QA | 結合テスト（DocumentViewer・OnSiteLogistics と接続） | `qa/server-cutover` | 手動チェックリスト、RUNBOOK 作成 |

### 2.2 tool-management-system02（Window A）

| フェーズ | 作業内容 | ブランチ例 | 備考 |
| --- | --- | --- | --- |
| Prep | 現行 USB スクリプト・サービス設定の棚卸し | `feature/server-migration-prep` | 移行後にどこまで残すかを整理 |
| Prep-2 | DocumentViewer・工具管理 UI 等のクライアント機能を棚卸し、必要データと依存関係を整理 | `feature/windowa-inventory` | RaspberryPiServer へ移す機能と残す機能を明確化 |
| Impl-1 | DocumentViewer の API/Socket.IO 提供機能を RaspberryPiServer 側へ移植 | `feature/windowa-viewer-migration` | 新サーバーでの API 応答と UI 連携を検証 |
| Impl-2 | 工具管理、標準工数、日程、構内物流などのサーバー機能を段階的に移行 | `feature/windowa-tool-migration` | それぞれの API / データ移行手順を整理し、Pi Zero や DocumentViewer との連携を確認 |
| Cutover | Window A からサーバー機能を外し、クライアント専用に再構成 | `feature/server-migration` | RaspberryPiServer への移行完了後に実施し、ロールバック手順を保持 |
| Archive | 必要であれば README/RUNBOOK を更新し、旧環境の役割を明示 | `feature/archive-notes` | トラブル時のロールバック手順を保持 |

### 2.3 DocumentViewer（Window B）

| フェーズ | 作業内容 | ブランチ例 | 検証ポイント |
| --- | --- | --- | --- |
| Prep | Socket.IO 接続先設定を外部化（環境変数 / config） | `feature/socketio-switch` | 旧サーバー / 新サーバー切替テスト |
| Cutover | DIST USB 形式への対応、右ペインの動作検証 | `feature/dist-usb` | USB → 端末コピーのテスト |
| Docs | RUNBOOK / README 更新 | `feature/update-docs` | サーバー切替手順、ロールバック手順 |

### 2.4 OnSiteLogistics（Window D）

| フェーズ | 作業内容 | ブランチ例 | 検証ポイント |
| --- | --- | --- | --- |
| Prep | ミラー送信モードの実装（config / 送信処理） | `feature/mirror-mode` | HTTP 送信順序、再送キュー検証 |
| Integration | RaspberryPiServer とのエンドポイント切替 | `feature/server-endpoint` | ミラー有効・無効の切替テスト |
| Docs | ハンディリーダ設定手順更新 | `feature/update-docs` | ミラー設定・復旧手順の明記 |

> Pi Zero 側の設定手順は `OnSiteLogistics/README.md` および `scripts/install_client_config.sh` に整備済み。`sudo ./scripts/install_client_config.sh --api-url http://raspi-server.local:8501/api/v1/scans ...` を実行し、`handheld@.service` を再起動するだけで RaspberryPiServer へ切り替えられる。
> 作業進捗の一覧は `docs/status/2025-10-26-client-cutover.md` を参照。

## 3. 共通検証項目

- **USB 運用**: INGEST → サーバー反映 → DIST エクスポート → 端末同期 → バックアップまでの一連テストを自動化する。
- **データ整合性**: 日次チェックリスト（Pi Zero → API → DocumentViewer → USB）を用い、送信から表示までの一連フローを手動で検証する。
- **ロールバック**: 各リポジトリで `git checkout main` / `docker compose down` / `systemctl disable` を実施し、旧構成へ復帰できるか確認。
- **RUNBOOK**: 切替手順書、トラブルシュート、連絡フローをまとめ、現場共有する。

## 4. マイルストーン候補

| 時期 | 内容 | 判定基準 |
| --- | --- | --- |
| M1 | RaspberryPiServer の基盤実装完了 | Docker/systemd/ログが稼働し、USB スクリプトが手動で動作 |
| M2 | ミラー運用開始 | Pi Zero から RaspberryPiServer への送信が安定し、日次手動チェックがスタート |
| M3 | DocumentViewer / 工具管理 UI の切替準備完了 | Socket.IO 接続先切替、DIST USB 運用が問題なく実行可能 |
| M4 | 本番切替 | 手動チェックリストで 14 日連続 OK、RUNBOOK 整備、ロールバック手順完了 |
| M5 | 旧環境の一定期間監視後に退役 | Window A のサーバー機能を停止し、アーカイブ化 |

### systemd / udev 導入メモ（現状の推奨手順）

1. `sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/`
2. `sudo cp udev/90-toolmaster.rules /etc/udev/rules.d/`
3. `sudo systemctl daemon-reload`
4. `sudo systemctl enable --now tool-snapshot.timer`
5. `sudo mkdir -p /usr/local/toolmaster/bin /usr/local/toolmaster/lib`
6. `sudo cp scripts/tool-*.sh /usr/local/toolmaster/bin/`
7. `sudo cp lib/toolmaster-usb.sh /usr/local/toolmaster/lib/`
8. `sudo chmod 755 /usr/local/toolmaster/bin/tool-*.sh`
9. `sudo chmod 644 /usr/local/toolmaster/lib/toolmaster-usb.sh`
10. `sudo ln -sf /usr/local/toolmaster/bin/tool-*.sh /usr/local/bin/`
11. `sudo cp /usr/local/toolmaster/lib/toolmaster-usb.sh /usr/local/lib/toolmaster-usb.sh`
12. `sudo udevadm control --reload && sudo udevadm trigger`

## 5. オープン課題

- USB スクリプト実装で必要なユーティリティ依存（`rsync`, `jq`, `tar`, `zstd`）のインストール手順
- Pi Zero 2 W からの SSH／設定変更方法（`mirrorctl` との連携）をどう自動化するか
- SSD バックアップの保管場所（物理保管先、A/B ローテーション）と責任者
- RUNBOOK/CHANGELOG の更新タイミングとレビュー体制
- RUNBOOK 作成（systemd/udev 導入手順、USB 運用手順、ロールバック手順）のスケジュール化
- 物理 USB メモリでの最終検証（TM-INGEST/DIST/BACKUP ラベル適用、ラベル固定方法）
- Docker/PostgreSQL セットアップ（`docker-compose.yml`、`.env` 整備、バックアップ連携）— **2025-10-25** に Raspberry Pi 上でコンテナ起動・スナップショット・USB バックアップまで検証済み。詳細ログは `docs/test-notes/2025-10-25-postgres-compose.md` を参照。残課題: Docker volume → SSD bind mount への切替。
- OnSiteLogistics ミラー (`mirrorctl`, `mirror-compare`) 実装と Pi Zero 設定更新 — 仕様案: `docs/mirrorctl-spec.md`
  - `scripts/mirrorctl.py` で `status/enable/disable/rotate` を実装済み（Pi Zero 設定バックアップ・書き換え、SSH 経由のサービス再起動、mirror-compare.timer 制御、ログローテーション対応）。
  - 設定テンプレート `config/mirrorctl-config.sample.json` を配置。デプロイ先では `/etc/mirrorctl/config.json` へ展開予定。
  - systemd unit `systemd/mirror-compare.service` / `.timer` を追加し、日次実行の枠組みを整備。
  - TODO: `mirror_compare.py` の拡張（健全性チェック指標の追加）と Pi Zero 側ミラー送信モード実装、mirrorctl の統合テストと RUNBOOK 手動検証手順の拡張。

状況変化に応じて本ロードマップを更新し、進捗共有の基準とする。
