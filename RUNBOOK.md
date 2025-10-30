# RaspberryPiServer RUNBOOK

本書は RaspberryPiServer の運用担当者向けに、日常運用・障害対応・ロールバックをまとめたものです。作業前には必ず最新の `docs/requirements.md` と `docs/usb-operations.md` を参照してください。

## 1. 基本情報
- ホスト: Raspberry Pi 5 (SSD ブート)
- OS: Raspberry Pi OS 64bit
- 推奨ホスト名: `raspi-server`
  - 初期構築時に `sudo hostnamectl set-hostname raspi-server` を実行し、クライアントから `raspi-server.local` で参照できるようにする。
  - Pi4 などクライアントでは `/etc/hosts` に IP を固定せず、Avahi (mDNS) に任せる。環境を移動した場合は `ping raspi-server.local` で疎通を確認し、解決できない場合はクライアントの Avahi 状態を確認する。
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

### 3.0 サーバースタックの自動セットアップ
リポジトリ直下で次を実行すると、USB スクリプト配置・systemd/udev・必要ディレクトリ・タイマー有効化までを一括で行う。

```bash
cd ~/RaspberryPiServer
sudo scripts/install_server_stack.sh
```

- `PREFIX=/opt/toolmaster sudo scripts/install_server_stack.sh` のように `PREFIX` を変更可能。
- タイマー起動をスキップする場合は `--skip-enable` を付与。
- ロールバックは `sudo scripts/install_server_stack.sh --remove` で行う（スクリプトと unit、udev を削除。`/srv/rpi-server/*` のデータは削除されない）。

以降の節では個別手順を記載しているが、自動セットアップで完了した場合は必要に応じた確認のみ実施すればよい。

### 3.1 コード更新
```bash
cd ~/RaspberryPiServer
git fetch origin
git checkout feature/server-ops-docs
git pull --ff-only
```
### 3.2 systemd/udev テンプレート更新

> `scripts/install_server_stack.sh` を利用した場合は自動的に配置・daemon-reload 済み。必要に応じて再実行する。

```bash
sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/
sudo cp udev/90-toolmaster.rules /etc/udev/rules.d/
sudo systemctl daemon-reload
sudo systemctl enable --now tool-snapshot.timer
sudo systemctl enable --now mirror-compare.timer
sudo udevadm control --reload
sudo udevadm trigger
```
### 3.3 スクリプト配置

> 自動セットアップを利用した場合はこの手順は不要。
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
- `docker-compose.yml` の `postgres` サービスは `ports: ["0.0.0.0:15432:5432"]` 等でホストへ公開されている（`tool-snapshot.sh` がホストから接続するため必須）。
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
   sudo PG_URI="postgresql://USER:PASSWORD@127.0.0.1:15432/DB" tool-snapshot.sh --dest /srv/rpi-server/snapshots
   ```
   **想定結果**: `/srv/rpi-server/snapshots/yyyymmdd_hhmmss/db/pg_dump.sql` が作成される。ログに `snapshot completed` が出力。  
   **エラー時の確認**: `pg_dump` が見つからない場合は `postgresql-client` のインストールと `PATH` を確認。接続拒否の場合は `pg_hba.conf` 等を調整。

> **事前チェック**: `/srv/rpi-server` 配下に `docker-compose.yml` / `.env` / `Dockerfile` / `app/` が揃っていることを確認する。揃っていない場合は以下例のようにリポジトリから再配置する。
> ```bash
> sudo rsync -a ~/RaspberryPiServer/docker-compose.yml ~/RaspberryPiServer/Dockerfile /srv/rpi-server/
> sudo rsync -a ~/RaspberryPiServer/app/ /srv/rpi-server/app/
> sudo cp ~/RaspberryPiServer/.env.example /srv/rpi-server/.env  # 本番値へ編集必須
> ```

8. systemd サービス導入  
   **コマンド**
   ```bash
   sudo install -m 644 systemd/raspi-server.service /etc/systemd/system/raspi-server.service
   sudo install -m 640 config/raspi-server.env.sample /etc/default/raspi-server
   sudo systemctl daemon-reload
   sudo systemctl enable --now raspi-server.service
   ```
   **想定結果**: `systemctl status raspi-server.service` が `Active: active (exited)` を示し、`docker compose ps` で `postgres` / `raspberrypiserver-app-1` が起動済み。  
   **エラー時の確認**:
   - `journalctl -u raspi-server.service` で詳細を確認。`WorkingDirectory`（デフォルト `/srv/rpi-server`）や `.env` の配置 `/srv/rpi-server/.env` を再確認。
   - `no configuration file provided` が表示される場合は `/srv/rpi-server` に `docker-compose.yml` / `.env` / `Dockerfile` / `app/` がコピーされているか確認し、リポジトリから `sudo rsync -a ~/RaspberryPiServer/docker-compose.yml ~/RaspberryPiServer/Dockerfile /srv/rpi-server/`、`sudo rsync -a ~/RaspberryPiServer/app/ /srv/rpi-server/app/` のように再配置する（`.env` は `~/RaspberryPiServer/.env.example` をベースに本番値へ書き換えて配置）。
   - 旧構成のコンテナ (`postgres` / `raspberrypiserver-app-1`) が残っていると名前やポートが競合するため、`sudo docker ps` → `sudo docker stop <name>` → `sudo docker rm <name>` で停止・削除してから再試行する。
   - `Bind for 0.0.0.0:8501 failed` が出る場合は `sudo lsof -iTCP:8501 -sTCP:LISTEN` でポート占有プロセスを特定し、停止後に `sudo docker compose up -d` を再実行する。
   - REST API 用の Bearer トークンを使用する場合は `/etc/default/raspi-server` に `API_TOKEN=...` を設定し、`sudo systemctl restart raspi-server.service` で反映する。Window A（tool-management-system02）からアクセスする際は `/etc/default/window-a-client` の `RASPI_SERVER_API_TOKEN` / `DATABASE_URL` を同じ値へ合わせ、`sudo systemctl restart toolmgmt.service` を実行する。
   - `toolmgmt.service` が見つからない場合は Window A のリポジトリ（`~/tool-management-system02`）で `sudo ./scripts/install_window_a_env.sh --with-dropin` を再実行し、`/etc/systemd/system/toolmgmt.service` と `/etc/default/window-a-client` が展開されているか確認する。

   **既存コンテナ・ポート競合解消のテンプレート**
   ```bash
   cd /srv/rpi-server
   sudo docker ps -a
   sudo docker stop postgres || true
   sudo docker stop raspberrypiserver-app-1 || true
   sudo docker rm postgres || true
   sudo docker rm raspberrypiserver-app-1 || true
   sudo lsof -iTCP:8501 -sTCP:LISTEN  # まだ占有されている場合はプロセスを停止
   sudo docker compose up -d
   ```

9. バックアップ書き出し（dry-run）  
   **コマンド**
   ```bash
   sudo tool-backup-export.sh --device /dev/sdX1 --dry-run
   ```
   **想定結果**: 最新スナップショットのアーカイブ計画がログに出力され、USB への書き込みは行われない。  
   **エラー時の確認**: `validation failed` が出た場合は USB のラベルと `/.toolmaster/role` を確認する。

10. 本番バックアップ  
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
- DocumentViewer ログ（`/srv/rpi-server/logs/document_viewer.log`）に書き込みできない: `sudo ls -ld /srv/rpi-server/logs` でパーミッションと SSD マウントを確認。必要に応じて `sudo chown -R pi:pi /srv/rpi-server/logs` を実行し、Docker 再起動後に再試行する。
- Window A クライアントの `/etc/default/docviewer` を更新したのに反映されない: 設定テンプレートは DocumentViewer リポジトリの `config/docviewer.env.sample`。`sudo systemctl restart docviewer.service` 実行後に `sudo journalctl -u docviewer.service -n 50` と `/var/log/document-viewer/client.log` を確認する。

**ロールバック**
1. `sudo docker compose down` でコンテナを停止。
2. 永続ボリュームを削除する場合は `sudo docker volume rm postgres-data`（本番データは削除されるため要注意）。
3. `.env` や `postgres-data` に秘密情報が残る場合はバックアップ後に消去。

**バックアップ後の確認**
- `/srv/rpi-server/snapshots/latest/db/pg_dump.sql` のタイムスタンプとサイズを確認。
- USB （`/media/TM-BACKUP` 等）に生成された `*_full.tar.zst` のサイズを記録し、保管ログへ転記。

#### 3.4.1 REST API (app サービス) の管理

- 起動／停止  
  ```bash
  sudo docker compose up -d app
  sudo docker compose stop app
  ```
- 状態確認  
  ```bash
  sudo docker compose ps app
  sudo docker logs app
  ```
- ヘルスチェック  
  ```bash
  curl -s http://127.0.0.1:8501/healthz
  ```
  戻り値が `{"status":"ok"}` であれば正常。失敗時は `sudo docker logs app` を確認し、`.env` の `DATABASE_URL` / `API_TOKEN` を点検する。
- DocumentViewer API/ログ確認  
  ```bash
  curl -s http://127.0.0.1:8501/api/documents/testpart | jq
  tail -n 20 /srv/rpi-server/logs/document_viewer.log
  sudo tail -n 20 /var/log/document-viewer/client.log  # Window A 側を確認する場合
  ```
  期待される結果: JSON に `found: true` が含まれ、ログには `Document lookup success` が追記される。404 応答時もログへ `Document not found` が記録される。ログが生成されない場合は `VIEWER_LOG_PATH` 環境変数と Docker bind mount (`/srv/rpi-server/logs`) を確認。
  RaspberryPiServer 側の `/etc/default/raspi-server` で `VIEWER_LOG_PATH` を設定している場合は `config/raspi-server.env.sample` を参照し、DocumentViewer リポジトリ側テンプレートと整合をとる。
- API テスト（Bearer トークン無しの場合）  
  ```bash
  curl -s -X POST http://127.0.0.1:8501/api/v1/scans \
    -H 'Content-Type: application/json' \
    -d '{"part_code":"TEST-001","location_code":"SHELF-01"}'
  ```
  201 が返り `accepted: true` であれば成功。トークンを有効化している場合は `-H "Authorization: Bearer <token>"` を追加する。

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

**日次チェック**
- `docs/test-notes/2025-10-25-mirrorctl-integration-plan.md` のチェックリストに沿って 1 日 1 回手動検証を行い、結果を記録する。
- `mirrorctl status` の出力・Pi Zero の送信ログ・DocumentViewer の画面・USB 取り込み結果をスクリーンショットやメモで残す。
- OK カウンタ: `sudo cat /var/lib/mirror/ok_counter`

**追加モニタリング**
- `journalctl -t mirrorctl -n 50` で mirrorctl 実行ログを確認。
- `journalctl -u mirror-compare.timer` / `mirror-compare.service` で健全性チェック実行を確認。
- 初回セットアップ時は `sudo systemctl enable --now mirror-compare.timer` を実行し、`systemctl list-timers` で登録を確認する。

**ミラー停止時のロールバック**
1. `sudo mirrorctl disable`
2. `sudo systemctl status mirror-compare.timer` で停止済みを確認。
3. Pi Zero 側 `/etc/onsitelogistics/config.json` を確認し、`mirror_endpoint` が削除されていることを確認。

### 3.6 mirror_compare タイマー運用

### 3.6.1 app ログ点検（RaspberryPiServer）

- `sudo ./scripts/check_app_logs.sh` を実行すると、`docker compose logs app` の WARN/ERROR を抽出できます。
- 既知の文言（`attribute 'version' is obsolete`）は自動的に除外されます。その他の WARN/ERROR が出力された場合は `sudo docker compose logs app -n 200` で詳細を確認し、必要に応じて対応策を検討してください。
- 週次点検では `TAIL_LINES=<行数>` を指定してログ範囲を増やし、過去の警告を洗い出してください。

### 3.6.2 `/srv/rpi-server/logs/` 週次サマリ

- `sudo ./scripts/check_storage_logs.sh` を実行すると、ログディレクトリのサイズ・直近更新ファイル・ WARN/ERROR 抜粋をまとめて確認できます。
- `LOG_ROOT`、`DAYS`、`TAIL_LINES`、`RECENT_LIMIT` などの環境変数で対象や期間を調整できます。例: `DAYS=14 TAIL_LINES=200 sudo ./scripts/check_storage_logs.sh`
- WARN/ERROR が検出された場合は終了コード 2 で終了するため、cron ジョブから呼び出す際はステータス監視に組み込みます。
- 処理結果の保存や自動化例は `docs/checklists/weekly-log-review.md` を参照し、`/etc/cron.d/` への登録状況を定期的に棚卸ししてください。
(略)

**手動検証（dry-run）**  
```bash
mirror_compare.py --dry-run
```
**想定結果**: `status":"OK"` を含む JSON が標準出力に表示され、ログやカウンタは更新されない（RaspberryPiServer 内部の健全性チェックとして利用）。  
**エラー時の確認**: `psycopg` ImportError → `sudo apt install python3-psycopg2`。DB 接続エラーが出た場合は `primary_db_uri` / `mirror_db_uri`（どちらも localhost）とテーブル状態を確認する。

**本実行**  
```bash
sudo mirror_compare.py
```
**想定結果**: `/srv/rpi-server/logs/mirror_status.log` に実行結果が追記され、異常があれば `mirror_diff.log` に記録される。OK ストリークは `/var/lib/mirror/ok_counter` に加算される。  
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
| ミラー検証で × が出る | `mirrorctl status`、日次チェックシート、`journalctl -u mirror-compare.service` | `sudo mirrorctl disable` で一時停止。Pi Zero 設定やログ（`mirror_requests.log` / `mirror_status.log` / `mirror_diff.log`）を確認し、原因解消後に再度 `mirrorctl enable` して日次チェックをやり直す |

## 6. 連絡フロー
- 1 次対応: システム担当（RaspberryPiServer 運用者）
- 2 次対応: 開発チーム（連絡先 TBD）

## 7. 変更履歴
- 2025-10-25: 初版（USB 自動化・スナップショット手順を記載）
