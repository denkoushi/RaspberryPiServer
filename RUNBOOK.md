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
sudo install -m 755 scripts/mirrorctl.py /usr/local/bin/mirrorctl
sudo install -m 755 scripts/mirror_compare.py /usr/local/bin/mirror_compare.py
```
### 3.4 Docker/PostgreSQL セットアップ

**前提**
- Docker/Compose と `postgresql-client` がインストール済みで `docker` サービスが起動している。
- リポジトリは `/srv/rpi-server` に配置し、`.env` は `POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB` を本番値へ更新済み。
- `docker-compose.yml` の `postgres` サービスは `ports: ["127.0.0.1:5432:5432"]` でホストへ公開されている（`tool-snapshot.sh` が `localhost` へ接続するため必須）。
- SSD（例: `/srv/rpi-server`）が bind mount されており、`/srv/rpi-server/snapshots` へ書き込み可能。

**セットアップ手順**

1. 依存パッケージ導入  
   **コマンド**
   ```bash
   sudo apt install -y docker.io docker-compose-plugin postgresql-client python3-psycopg2
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

### 3.5 mirrorctl 運用（ミラー送信制御）

**前提**
- 設定ファイル `/etc/mirrorctl/config.json` を `config/mirrorctl-config.sample.json` から展開済みで、Pi Zero への SSH 鍵認証が完了している。
- `mirror-compare.service` / `mirror-compare.timer` はシステムに登録済み。
- ログディレクトリ `/srv/rpi-server/logs/` とステータスディレクトリ `/var/lib/mirror/` が作成済み。

1. 状態確認  
   **コマンド**
   ```bash
   mirrorctl status
   ```
   **想定結果**: タイマーとサービスの `active`/`enabled`、OK カウンタ、最新 `mirror_status.log` / `mirror_diff.log` の要約が表示される。  
   **エラー時の確認**: `設定ファイルが見つかりません` → `/etc/mirrorctl/config.json` の権限・パスを確認。`unsupported` 表示の場合は `systemctl` が利用できない環境。

2. ミラー有効化  
   **コマンド**
   ```bash
   sudo mirrorctl enable
   ```
   **想定結果**: Pi Zero 側設定が `mirror_mode=true` に更新され、`mirror-compare.timer` が `enabled/active` へ変化。`mirrorctl status` で反映を確認。  
   **エラー時の確認**: `SSH 接続に失敗` → Pi Zero のホスト名/IP・鍵配置を確認。`systemctl` 関連エラー → タイマーが未登録かサービス名が不一致。  
   **ロールバック**: `sudo mirrorctl disable` を実行し、Pi Zero 設定を戻す。

3. ミラー停止  
   **コマンド**
   ```bash
   sudo mirrorctl disable
   ```
   **想定結果**: Pi Zero 設定が `mirror_mode=false` に戻り、タイマーが `disabled/inactive`。ログ末尾に停止記録が残る。  
   **エラー時の確認**: Pi Zero 側ファイル権限で失敗する場合は `sudo` 付与を検討。タイマー無効化に失敗した場合は `sudo systemctl disable --now mirror-compare.timer` を手動実行。

4. ログローテーション  
   **コマンド**
   ```bash
   sudo mirrorctl rotate
   ```
   **想定結果**: `mirror_requests.log` / `mirror_diff.log` が日付付き `.gz` に退避され、30 日より古いファイルが削除される。  
   **エラー時の確認**: ログディレクトリ権限不足 → `/srv/rpi-server/logs/` の所有者を確認。

**追加モニタリング**
- `journalctl -t mirrorctl -n 50` で mirrorctl 実行ログを確認。
- `journalctl -u mirror-compare.timer` / `mirror-compare.service` で定期比較の実行有無を確認。
- OK カウンタ: `sudo cat /var/lib/mirror/ok_counter`

**ミラー停止時のロールバック**
1. `sudo mirrorctl disable`
2. `sudo systemctl status mirror-compare.timer` で停止済みを確認。
3. Pi Zero 側 `/etc/onsitelogistics/config.json` を確認し、`mirror_endpoint` が削除されていることを確認。

### 3.6 mirror_compare タイマー運用

**手動検証（dry-run）**  
```bash
mirror_compare.py --dry-run
```
**想定結果**: 差分が無い場合は `status":"OK"` を含む JSON が標準出力に表示され、ログやカウンタは更新されない。  
**エラー時の確認**: `psycopg` ImportError → `sudo apt install python3-psycopg2`。DB 接続エラーが出た場合は `primary_db_uri` / `mirror_db_uri` とネットワーク疎通を確認する。

**本実行**  
```bash
sudo mirror_compare.py
```
**想定結果**: `/srv/rpi-server/logs/mirror_status.log` に実行結果が追記され、差分発生時は `mirror_diff.log` に詳細 JSON が記録される。OK ストリークは `/var/lib/mirror/ok_counter` に加算される。  
**ロールバック**: 直前の実行を無視したい場合は、該当ログ行を削除し `ok_counter` を手動で調整する。ログ整理は `sudo mirrorctl rotate` で実施可能。

**タイマー確認手順**
- `sudo systemctl status mirror-compare.timer`
- `sudo systemctl status mirror-compare.service`
- `journalctl -u mirror-compare.service --since "1 day ago"`

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
| ミラー比較が実行されない / 差分が解消しない | `mirrorctl status`、`journalctl -u mirror-compare.service` | `mirrorctl enable` で再有効化。Pi Zero 設定 (`mirror_mode`, `mirror_endpoint`) を確認し、差分ログ (`mirror_diff.log`) を解析 |

## 6. 連絡フロー
- 1 次対応: システム担当（RaspberryPiServer 運用者）
- 2 次対応: 開発チーム（連絡先 TBD）

## 7. 変更履歴
- 2025-10-25: 初版（USB 自動化・スナップショット手順を記載）
