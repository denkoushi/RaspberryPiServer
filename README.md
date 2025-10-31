# RaspberryPiServer

RaspberryPiServer は Raspberry Pi 5 上で工具管理・DocumentViewer・OnSiteLogistics など複数システムのサーバー機能を集約するためのプロジェクトです。REST / Socket.IO API、PostgreSQL、USB 運用、バックアップを一体的に提供し、Window A（Pi4）・Pi Zero 2 W（ハンディ）・DocumentViewer 端末から利用できるようにします。

## リポジトリ構成

| ディレクトリ | 説明 |
| --- | --- |
| `app/` | Flask アプリケーション本体（REST / Socket.IO / DocumentViewer UI） |
| `config/` | systemd / 環境ファイルのサンプル |
| `docs/` | 要件・設計・運用ドキュメント、テンプレート、テストログ |
| `scripts/` | USB 運用・バックアップ・セットアップ向けスクリプト |
| `systemd/` / `udev/` | サービス・タイマー・USB 連携の unit / ルール |
| `templates/` | DocViewer UI などの Jinja テンプレート |
| `tests/` | pytest ベースのユニットテスト |

詳細な役割は `docs/docs-index.md` を参照してください。

## セットアップ概要

1. **ソース取得**
   ```bash
   git clone https://github.com/denkoushi/RaspberryPiServer.git
   cd RaspberryPiServer
   ```
2. **依存パッケージ**
   ```bash
   sudo apt update
   sudo apt install -y python3-venv python3-dev libpq-dev \
       build-essential jq rsync tar zstd avahi-daemon
   ```
3. **Docker / Compose**
   ```bash
   sudo apt install -y docker.io docker-compose-plugin
   sudo usermod -aG docker "$USER"
   ```
4. **環境変数の準備**
   - `cp .env.example .env` で初期ファイルを用意し、PostgreSQL・API トークンなど本番値へ更新。
   - systemd 用の環境ファイルは `config/raspi-server.env.sample` を `/etc/default/raspi-server` に配置して編集。
5. **サーバースタックの導入**
   ```bash
   sudo scripts/install_server_stack.sh
   sudo systemctl enable --now raspi-server.service
   ```

詳細手順・ロールバックは `RUNBOOK.md` を参照してください。

## 運用フローの概要

- **データ受信**: Pi Zero からのスキャンを `/api/v1/scans` で受け取り、PostgreSQL と Socket.IO イベントへ反映。
- **DocumentViewer**: `/viewer` で UI を提供し、Socket.IO を通じて在庫更新を反映。Window A から iframe で利用。
- **USB 運用**: `TM-INGEST`（マスターデータ持ち込み）、`TM-DIST`（各端末配布）、`TM-BACKUP`（世代バックアップ）の 3 種を `docs/usb-operations.md` に沿って運用。
- **ミラー検証**: Pi Zero + DocumentViewer + Window A の 3 機器で 14 日連続チェックを `docs/mirror-verification.md` の手順で実施。

## ホスト名と接続確認

標準ホスト名は `raspi-server` を想定していますが、Avahi の重複回避で `raspi-server-3.local` のように変化する場合があります。以下を参考に実機のホスト名を確認し、クライアント設定と一致させてください。

```bash
hostnamectl
avahi-browse -rt _workstation._tcp  # 公開中の mDNS 名を確認
ping raspi-server.local             # 解決できない場合は実際のホスト名へ置き換え
```

Window A などクライアント側の `/etc/toolmgmt/window-a-client.env` や `/etc/default/docviewer` の `RASPI_SERVER_BASE` / `UPSTREAM_SOCKET_BASE` も同じホスト名に揃えます。

## 主要ドキュメント

- `docs/requirements.md` — 要件・決定事項・未解決課題
- `docs/implementation-plan.md` — リポジトリ別ロードマップ
- `docs/documentviewer-migration.md` — DocumentViewer 移行ステータス
- `docs/api-plan.md` — REST / Socket.IO API 仕様
- `docs/mirror-verification.md` — 14 日検証手順
- `docs/usb-operations.md` — USB 運用ルール
- `docs/templates/` — テストログテンプレート

## ライセンス

このリポジトリのライセンスは `LICENSE` が整備され次第、ここに明記します。
