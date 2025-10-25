# RaspberryPiServer RUNBOOK

本書は RaspberryPiServer の運用担当者向けに、日常運用・障害対応・ロールバックをまとめたものです。作業前には必ず最新の `docs/requirements.md` と `docs/usb-operations.md` を参照してください。

## 1. 基本情報
- ホスト: Raspberry Pi 5 (SSD ブート)
- OS: Raspberry Pi OS 64bit
- メインサービス: tool-ingest / tool-dist / tool-backup automation, tool-snapshot.timer
- ログディレクトリ: `/srv/rpi-server/logs/`
- スクリプト配置: `/usr/local/toolmaster/bin/`
- 共通ライブラリ: `/usr/local/lib/toolmaster-usb.sh`

## 2. 日常運用
### 2.1 USB 自動化確認
1. USB メモリ (`TM-INGEST`, `TM-DIST`, `TM-BACKUP`) を挿入。
2. `journalctl -u usb-ingest@* -n 20` などで `ingest completed` / `dist export completed` / `backup export completed` が出力されることを確認。
3. 必要に応じて `/srv/rpi-server/master` や `/mnt/physusb` を spot check。

### 2.2 スナップショット確認
- `systemctl status tool-snapshot.timer`
- `journalctl -u tool-snapshot.service --since "1 day ago"`
- スナップショット保存先: `/srv/rpi-server/snapshots/YYYY-MM-DD_HHMMSS/`

### 2.3 バックアップ USB のローテーション
1. `TM-BACKUP` を挿入し、自動実行ログを確認。
2. `/mnt/backup/YYYY-MM-DD_full.tar.zst` が生成されていることを確認。
3. 取り外す前に `sudo umount /mnt/backup`。

## 3. デプロイ/更新手順
### 3.1 コード更新
```bash
cd ~/RaspberryPiServer
git fetch origin
git checkout feature/server-ops-docs
git pull --ff-only
```
### 3.2 systemd/udev テンプレート更新
```bash
sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/
sudo cp udev/90-toolmaster.rules /etc/udev/rules.d/
sudo systemctl daemon-reload
sudo systemctl enable --now tool-snapshot.timer
sudo udevadm control --reload
sudo udevadm trigger
```
### 3.3 スクリプト配置
```bash
sudo mkdir -p /usr/local/toolmaster/bin /usr/local/toolmaster/lib
sudo cp scripts/tool-*.sh /usr/local/toolmaster/bin/
sudo cp lib/toolmaster-usb.sh /usr/local/toolmaster/lib/
sudo chmod 755 /usr/local/toolmaster/bin/tool-*.sh
sudo chmod 644 /usr/local/toolmaster/lib/toolmaster-usb.sh
sudo ln -sf /usr/local/toolmaster/bin/tool-ingest-sync.sh /usr/local/bin/tool-ingest-sync.sh
sudo ln -sf /usr/local/toolmaster/bin/tool-dist-export.sh /usr/local/bin/tool-dist-export.sh
sudo ln -sf /usr/local/toolmaster/bin/tool-dist-sync.sh /usr/local/bin/tool-dist-sync.sh
sudo ln -sf /usr/local/toolmaster/bin/tool-backup-export.sh /usr/local/bin/tool-backup-export.sh
sudo ln -sf /usr/local/toolmaster/bin/tool-snapshot.sh /usr/local/bin/tool-snapshot.sh
sudo cp /usr/local/toolmaster/lib/toolmaster-usb.sh /usr/local/lib/toolmaster-usb.sh
```
### 3.4 Docker/PostgreSQL セットアップ

**前提**
- Docker/Compose と `postgresql-client` がインストール済みで `docker` サービスが起動している。
- リポジトリは `/srv/rpi-server` に配置し、`.env` は `POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB` を本番値へ更新済み。
- SSD（例: `/srv/rpi-server`）が bind mount されており、`/srv/rpi-server/snapshots` へ書き込み可能。

**セットアップ手順**

1. 依存パッケージ導入  
   **コマンド**
   ```bash
   sudo apt install -y docker.io docker-compose-plugin postgresql-client
   ```
   **想定結果**: `docker`, `docker compose`, `pg_dump` が利用可能になる。既に導入済みの場合は `0 upgraded` 等が表示される。  
   **エラー時の確認**: 失敗時は `apt` のログを確認し、必要に応じてパッケージキャッシュを更新する（`sudo apt update`）。

2. `.env` の配置  
   **コマンド**
   ```bash
   cd /srv/rpi-server
   cp .env.example .env
   ```
   **想定結果**: `.env` が生成され、`.env.example` と同じ値で初期化される。編集後は `chmod 600 .env` を推奨。  
   **エラー時の確認**: `.env` が既に存在する場合は上書きせず、中身を手動で更新する。

3. コンテナ起動  
   **コマンド**
   ```bash
   sudo docker compose up -d
   ```
   **想定結果**: `postgres` コンテナがバックグラウンド起動し、`Started` メッセージが表示される。初回はイメージ取得のため数分かかる。  
   **エラー時の確認**: `Cannot connect to the Docker daemon` が出る場合は `sudo systemctl status docker` でサービス状態を確認する。

4. 状態確認  
   **コマンド**
   ```bash
   sudo docker compose ps
   ```
   **想定結果**: `State` 列が `running`、`Health` 列が `healthy`。  
   **エラー時の確認**: `unhealthy` の場合は次手順のログ確認で原因を特定する。

5. ログ確認  
   **コマンド**
   ```bash
   sudo docker logs postgres --tail 50
   ```
   **想定結果**: 出力末尾に `database system is ready to accept connections` が表示される。  
   **エラー時の確認**: `FATAL: password authentication failed` などが出た場合は `.env` の資格情報と既存ボリュームの整合を確認する。

6. 永続化確認  
   **コマンド**
   ```bash
   sudo docker volume inspect postgres-data
   ```
   **想定結果**: `Mountpoint` が `/var/lib/docker/volumes/postgres-data/_data` 等、ホスト上の永続領域を指す。  
   **エラー時の確認**: ボリュームが存在しない場合は `docker compose down` → `docker compose up -d` で再生成する。

7. スナップショット実行  
   **コマンド**
   ```bash
   sudo PG_URI="postgresql://USER:PASSWORD@localhost:5432/DB" tool-snapshot.sh --dest /srv/rpi-server/snapshots
   ```
   **想定結果**: `/srv/rpi-server/snapshots/yyyymmdd_hhmmss/db/pg_dump.sql` が作成される。ログに `snapshot completed` が出力。  
   **エラー時の確認**: `pg_dump` が見つからない場合は `postgresql-client` のインストールと `PATH` を確認。接続拒否の場合は `pg_hba.conf` 等を調整。

8. バックアップ書き出し（dry-run）  
   **コマンド**
   ```bash
   sudo tool-backup-export.sh --device /dev/sdX1 --dry-run
   ```
   **想定結果**: 最新スナップショットのアーカイブ計画がログに出力され、USB への書き込みは行われない。  
   **エラー時の確認**: `validation failed` が出た場合は USB のラベルと `/.toolmaster/role` を確認する。

9. 本番バックアップ  
   **コマンド**
   ```bash
   sudo tool-backup-export.sh --device /dev/sdX1
   ```
   **想定結果**: USB 直下に `*_full.tar.zst` が生成され、ログに `backup export completed` が出力。完了後は `sync` → `sudo umount`。  
   **エラー時の確認**: 書き込みエラーは USB の残容量とマウント状態を確認。

**想定されるトラブルと診断**
- `Cannot connect to the Docker daemon`: `sudo systemctl status docker` で状態確認、停止時は `sudo systemctl start docker`。`docker` グループ未所属の場合は `sudo usermod -aG docker $USER` 後再ログイン。
- コンテナが `unhealthy`: `sudo docker logs postgres` で原因を特定。`POSTGRES_PASSWORD` を変更した場合は `postgres-data` をリセットする必要がある。
- `pg_dump` コマンド未検出: `sudo apt install postgresql-client` を再実行し、PATH に `/usr/bin` を含める。
- バックアップ USB を認識しない: `lsblk` でデバイスを確認し、`/etc/udev/rules.d/90-toolmaster.rules` のラベル定義を再確認。

**ロールバック**
1. `sudo docker compose down` でコンテナを停止。
2. 永続ボリュームを削除する場合は `sudo docker volume rm postgres-data`（本番データは削除されるため要注意）。
3. `.env` や `postgres-data` に秘密情報が残る場合はバックアップ後に消去。

**バックアップ後の確認**
- `/srv/rpi-server/snapshots/latest/db/pg_dump.sql` のタイムスタンプとサイズを確認。
- USB （`/media/TM-BACKUP` 等）に生成された `*_full.tar.zst` のサイズを記録し、保管ログへ転記。

## 4. ロールバック手順
1. `sudo systemctl disable tool-snapshot.timer`
2. `sudo rm /etc/systemd/system/usb-*.service /etc/systemd/system/tool-snapshot.*`
3. `sudo rm /etc/udev/rules.d/90-toolmaster.rules`
4. `sudo systemctl daemon-reload`
5. `sudo udevadm control --reload`
6. 必要に応じて `/usr/local/toolmaster` 配下を削除し、バックアップした旧バージョンを復元。

## 5. 障害対応
| 症状 | 確認ポイント | 対応 |
| --- | --- | --- |
| USB 自動処理が動かない | `journalctl -u usb-ingest@*` などでエラー確認 | スクリプト配置とラベル/role を再確認。 `/usr/local/lib/toolmaster-usb.sh` の存在を確認 |
| スナップショットが生成されない | `systemctl status tool-snapshot.timer`、`journalctl -u tool-snapshot.service` | タイマーが有効か、`/srv/rpi-server/snapshots` の権限確認 |
| バックアップ USB にアーカイブが無い | `/mnt/backup` のマウント・残容量確認 | アーカイブの手動作成: `sudo tool-backup-export.sh --device /dev/sdX1` |

## 6. 連絡フロー
- 1 次対応: システム担当（RaspberryPiServer 運用者）
- 2 次対応: 開発チーム（連絡先 TBD）

## 7. 変更履歴
- 2025-10-25: 初版（USB 自動化・スナップショット手順を記載）
