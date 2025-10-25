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
| Cutover | サーバー機能の縮退（API/Socket.IO の停止、データ移行） | `feature/server-migration` | RaspberryPiServer への移行完了後に実施 |
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

## 3. 共通検証項目

- **USB 運用**: INGEST → サーバー反映 → DIST エクスポート → 端末同期 → バックアップまでの一連テストを自動化する。
- **データ整合性**: `mirror-compare.sh` と PostgreSQL クエリで差分がないことを確認。
- **ロールバック**: 各リポジトリで `git checkout main` / `docker compose down` / `systemctl disable` を実施し、旧構成へ復帰できるか確認。
- **RUNBOOK**: 切替手順書、トラブルシュート、連絡フローをまとめ、現場共有する。

## 4. マイルストーン候補

| 時期 | 内容 | 判定基準 |
| --- | --- | --- |
| M1 | RaspberryPiServer の基盤実装完了 | Docker/systemd/ログが稼働し、USB スクリプトが手動で動作 |
| M2 | ミラー運用開始 | OnSiteLogistics から二重送信が成功し、日次比較がスタート |
| M3 | DocumentViewer / 工具管理 UI の切替準備完了 | Socket.IO 接続先切替、DIST USB 運用が問題なく実行可能 |
| M4 | 本番切替 | 14 日連続 OK、RUNBOOK 整備、ロールバック手順完了 |
| M5 | 旧環境の一定期間監視後に退役 | Window A のサーバー機能を停止し、アーカイブ化 |

## 5. オープン課題

- USB スクリプト実装で必要なユーティリティ依存（`rsync`, `jq`, `tar`, `zstd`）のインストール手順
- Pi Zero 2 W からの SSH／設定変更方法（`mirrorctl` との連携）をどう自動化するか
- SSD バックアップの保管場所（物理保管先、A/B ローテーション）と責任者
- RUNBOOK/CHANGELOG の更新タイミングとレビュー体制

状況変化に応じて本ロードマップを更新し、進捗共有の基準とする。
