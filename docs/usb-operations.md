# USB メモリ運用手順（INGEST / DIST / BACKUP）

この文書は RaspberryPiServer で運用する USB メモリの役割と操作手順を定義する。サーバー移行後は本手順に従ってデータ同期とバックアップを実施すること。

## 1. 役割と識別方法

| ラベル例 | シグネチャファイル | 主目的 | 挿入先 | 備考 |
| --- | --- | --- | --- | --- |
| `TM-INGEST` | `/.toolmaster/role` に `INGEST` | 外部で更新したマスターデータや PDF をサーバーへ持ち込む | サーバーのみ（書き込みあり） | ext4 のラベル最大 16 文字制限を踏まえた省略形。サーバーが新旧比較後に公式データへマージし、USB メモリ内容を最新化する |
| `TM-DIST` | `/.toolmaster/role` に `DIST` | サーバーの公式データを各端末へ配布 | 端末（DocumentViewer / 工具管理端末） | 端末は常に USB メモリ → 端末への一方向コピー。書き戻しは禁止 |
| `TM-BACKUP` | `/.toolmaster/role` に `BACKUP` | サーバーの世代バックアップを外部保管 | サーバーのみ（書き込みあり） | `udev` 連携で挿入時に最新スナップショットを `tar + zstd` 形式で出力 |

> ラベルは ext4 の 16 文字制限に合わせて短縮している。既存運用で別ラベルを使う場合は、`USB_INGEST_LABEL` などの環境変数で上書き可能。

シグネチャファイルが欠落している、または内容が一致しない場合は処理を中断し、`/srv/rpi-server/logs/usb_guard.log` に警告を出力する。

## 2. サーバーへの持込み（INGEST）

### 前提
- USB メモリに以下の構成でファイルを用意しておくこと。

```
TM-INGEST/
├── .toolmaster/
│   └── role (内容: INGEST)
├── master/
│   ├── tool_master.csv
│   ├── tools.csv
│   └── users.csv
└── docviewer/
    ├── meta.json
    └── *.pdf
```

### 手順
1. サーバー管理者が `TM-INGEST` をサーバーに挿す。
2. `udev` → `systemd` で `usb-ingest@<デバイス>.service` を起動。
3. サービスは `/.toolmaster/role` を確認し、`INGEST` であることを検証。異なる場合は処理を終了。
4. `meta.json` とファイルタイムスタンプを比較し、USB メモリ側が新しい場合のみサーバー上の `/srv/rpi-server/master/` および `/srv/rpi-server/docviewer/` を更新。
5. 取り込み後、サーバー側の最新データで USB メモリ内容を上書きし、`meta.json` を更新。
6. `journalctl -u usb-ingest@*` または `/srv/rpi-server/logs/usb_ingest.log` で結果を確認し、安全な取り外しを実施。

### エラー時の対処
- CSV のヘッダー不一致や欠落がある場合、対象ファイルを `errors/` ディレクトリへ退避し、詳細をログへ出力する。
- USB メモリの容量不足が検出された場合は処理を中断し、担当者が不要ファイル削除またはメディア交換を行う。

## 3. 端末への配布（DIST）

### 前提
-- サーバー側で定期的または必要に応じて `TM-DIST` へ最新データを書き出しておく（手動コマンド例をセクション 5 参照）。
- 端末側（DocumentViewer、工具管理端末）には `/usr/local/bin/tool-dist-sync.sh` を配置する。

### 手順
1. 担当者が `TM-DIST` を端末に挿す。
2. 端末側の udev ルールが `/.toolmaster/role` を確認し、`DIST` であることを検証。
3. `tool-dist-sync.sh` は USB メモリの `master/`、`docviewer/` を読み込み、端末ローカルのデータディレクトリを上書きコピーする。
4. コピー完了後、ログを `/var/log/tool-dist-sync.log` に追記し、端末のアプリケーション（DocumentViewer や工具管理 UI）へリロード通知を送る。

### 注意事項
- 端末は USB メモリへ書き込まない。`DIST` を誤ってサーバーに挿した場合はスクリプトが処理を中断し、ログで警告する。
- 大容量 PDF の同期が必要な場合は、端末側の空き容量を事前に確認する。
- ミラー検証期間中は、日次チェックリスト（`docs/test-notes/mirror-check-template.md`）で USB コピー結果を確認・記録する。端末側で更新されたファイル名と時刻をメモし、○/×判定に反映させる。

## 4. バックアップ（BACKUP）

### 前提
- サーバーは cron または systemd timer で `/srv/rpi-server` 配下のデータを日次スナップショット（7 世代）として保持する（`/srv/rpi-server/snapshots/YYYY-MM-DD/`）。
- バックアップ専用 USB メモリ（`TM-BACKUP`）を準備し、64 GB 以上の容量を確保する。

### 手順
1. 管理者が `TM-BACKUP` をサーバーに挿す。
2. `usb-backup@<デバイス>.service` が起動し、シグネチャを確認。
3. 最新スナップショットを `tar` + `zstd` で圧縮し、USB メモリ直下に `YYYY-MM-DD_full.tar.zst` という名前で保存する。
4. USB メモリ上のアーカイブが 4 ファイルを超えた場合は最も古いものから削除。
5. 結果は `/srv/rpi-server/logs/backup.log` に追記。完了後に安全な取り外しを実施する。

### エラー時の対処
- 容量不足の場合は処理を中断し、ログに必要容量を記録する。必要に応じて上位のバックアップ手順（外付け SSD 等）へエスカレーション。
- 圧縮中にエラーが発生した場合は `tar` / `zstd` の標準エラーをログに取り込み、再実行前にディスク状態とファイル破損を確認する。
- ミラー検証期間中はバックアップ完了を日次チェックシートに記録し、アーカイブ名（例: `2025-10-26_full.tar.zst`）を備考欄に残す。

## 5. 手動同期コマンド例

### サーバーで INGEST 用 USB メモリを最新化
```bash
sudo /usr/local/bin/tool-ingest-sync.sh --refresh
```

### サーバーで DIST 用 USB メモリへ書き出し
```bash
sudo /usr/local/bin/tool-dist-export.sh --target /media/TM-DIST
```

### 日次スナップショット作成（systemd timer から呼び出し）
```bash
/usr/local/bin/tool-snapshot.sh --dest /srv/rpi-server/snapshots
```

### 最新スナップショットを BACKUP 用 USB メモリへコピー
```bash
sudo /usr/local/bin/tool-backup-export.sh --target /media/TM-BACKUP
```

## 6. 今後の実装タスク

- `tool-ingest-sync.sh` / `tool-dist-export.sh` / `tool-backup-export.sh` の実装（ラベル・シグネチャ検証、例外処理、ログ出力）
- `udev` ルールと systemd unit（`usb-ingest@.service`、`usb-backup@.service`）の作成
- 既存 Window A の USB スクリプトからの差分洗い出しと移植計画策定
- エラー発生時の運用ルール整備（担当者連絡先、USB メモリ交換手順など）

## 7. systemd / udev 設計案

### 7.1 udev ルール

サンプル: `udev/90-toolmaster.rules`

コピー先: `/etc/udev/rules.d/90-toolmaster.rules`

```
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="TM-INGEST", \
    ENV{SYSTEMD_WANTS}="usb-ingest@%k.service"

ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="TM-BACKUP", \
    ENV{SYSTEMD_WANTS}="usb-backup@%k.service"

ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="TM-DIST", \
    ENV{SYSTEMD_WANTS}="usb-dist-export@%k.service"
```

> `TM-DIST` をサーバーに挿した場合は自動で最新データを書き出す運用。端末側で扱う場合は `tool-dist-sync.sh` を手動で実行する。

### 7.2 systemd unit テンプレート

サンプル: `systemd/usb-ingest@.service`

設置先: `/etc/systemd/system/usb-ingest@.service`

```ini
[Unit]
Description=Toolmaster USB ingest for %I
Requires=local-fs.target
After=local-fs.target

[Service]
Type=oneshot
Environment=SERVER_ROOT=/srv/rpi-server
Environment=USB_INGEST_LABEL=TM-INGEST
ExecStart=/usr/local/bin/tool-ingest-sync.sh --device /dev/%I
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

同梱テンプレート:

- `systemd/usb-backup@.service`
- `systemd/usb-dist-export@.service`
- `systemd/tool-snapshot.service`
- `systemd/tool-snapshot.timer`

配置後は `systemctl daemon-reload` を実行し、`systemctl enable --now tool-snapshot.timer` などで有効化する。

### 7.3 スクリプト構成

```
/usr/local/bin/
├── tool-ingest-sync.sh      # INGEST 処理（シグネチャ確認、新旧比較、マージ、USB 更新）
├── tool-dist-export.sh      # サーバー → DIST USB へのエクスポート
├── tool-dist-sync.sh        # 端末側 DIST → ローカルコピー
├── tool-backup-export.sh    # 最新スナップショットの圧縮・USB 退避
└── tool-snapshot.sh         # 日次スナップショット作成（cron / systemd timer 用）
```

各スクリプトは `lib/toolmaster-usb.sh`（共通関数ライブラリ）を参照し、ラベル検証やロギングを共通化する。

> 手動コピーが煩雑な場合は `sudo scripts/install_server_stack.sh` を利用すると、上記配置・systemd/udev 設定まで一括で行える。

### 7.4 ログ出力

- サーバー側: `/srv/rpi-server/logs/usb_ingest.log`、`usb_backup.log`、`usb_guard.log`
- 端末側: `/var/log/tool-dist-sync.log`
- `journalctl -u usb-ingest@*` などで詳細を確認可能

### 7.5 リトライと失敗時のハンドリング

- 失敗時は exit code ≠ 0 を返し、systemd が `StartLimitBurst` に達したら `OnFailure` で通知用スクリプト（LED 点滅・ログ出力など）を呼び出す。
- USB メモリの不整合（シグネチャ不一致、容量不足など）はスクリプト内で `usb_guard.log` に記録し、ユーザーに交換を促す。

## 8. スクリプト仕様とテスト

### 8.1 共通ライブラリ `lib/toolmaster-usb.sh`

- 提供関数
  - `usb_validate_role <mountpoint> <expected_role>`: ラベルとシグネチャファイルの両方を検証し、NG 時はエラーコードを返す。
  - `usb_mount_device <devname>`: `udisksctl` などを利用して安全にマウントし、マウントポイントを返却。
  - `usb_unmount <mountpoint>`: 同上。エラー時はリトライし、最終的に失敗した場合はログに記録。
  - `usb_log <level> <message>`: ログファイルと journal へ二重出力する。
- 環境変数
  - `USB_LOG_DIR=/srv/rpi-server/logs`
  - `USB_MAX_RETRY=3`
- テスト項目
  - 正常マウント・アンマウント
  - シグネチャ不一致時にエラーコード 2 を返す
  - ログ出力フォーマット（JSON or TSV）を固定し、`jq` / `cut` で解析できること

### 8.2 `tool-ingest-sync.sh`

- 引数: `--device /dev/sdX`（udev 経由）、`--dry-run`、`--force`
- 処理概要
  1. `usb_validate_role` で `INGEST` を確認
  2. CSV / PDF を `rsync --ignore-existing` で staging 領域へコピー
  3. `meta.json` と `stat` のタイムスタンプで新旧比較
  4. サーバー側データを更新（`/srv/rpi-server/master/`, `/srv/rpi-server/docviewer/`）
  5. サーバー側最新データを USB メモリへ書き戻し
  6. ログへ成功／失敗を記録し、マウント解除
- テストケース
  - 正常系: 新しい CSV を持ち込んでサーバーへ反映
  - 古いデータ: USB メモリが古い場合はサーバー内容が優先される
  - CSV 欠落: `tool_master.csv` がない場合はエラーとしてログへ警告
  - `--dry-run`: 変更せず差分のみ表示

### 8.3 `tool-dist-export.sh`

- 引数: `--target /media/TM-DIST`
- 処理概要
  - サーバー側の公式データを一時フォルダへコピーし、`rsync --delete` で USB メモリへ反映
  - オプションで `--include-pdf`, `--include-master` を制御可能
- テストケース
  - 初回エクスポートで USB メモリが空の状態
  - 既存ファイルとの差分更新
  - 容量不足時の中断確認

### 8.4 `tool-dist-sync.sh`（端末側）

- 処理概要
  - `DIST` シグネチャ検証後、USB メモリ → 端末ローカルへコピー
  - コピー先は `/opt/toolmaster/data/` 等。終了後にアプリへ HUP/REST API でリロード通知
- テストケース
  - 正常コピー（PDF・CSV 共に更新）
  - コピー途中で USB メモリが抜かれた場合のハンドリング（途中で中断し、再実行で回復できること）
  - 書込み禁止（USB へは書かないこと）

### 8.5 `tool-backup-export.sh`

- 処理概要
  - 最新スナップショットを選択
  - `tar --zstd -cf` で圧縮アーカイブを生成
  - USB メモリへコピーし、4 世代を超えた分は削除
- テストケース
  - 圧縮成功時にログへサイズ・処理時間を記録
  - 圧縮失敗（ディスクフル等）でエラーハンドリング
  - `--dry-run` でサイズ見積のみ実行

### 8.6 `tool-snapshot.sh`

- 処理概要
  - PostgreSQL ダンプ（`pg_dump`）とファイル同期（`rsync`）を組み合わせた日次スナップショットを `/srv/rpi-server/snapshots/YYYY-MM-DD/` に生成
  - 7 世代古いディレクトリを削除
- テストケース
  - 通常スナップショット作成
  - DB 接続失敗時のリトライ、`pg_dump` エラー
  - 古い世代削除（保持数の確認）

### 8.7 自動テスト戦略

- シェルスクリプト用に `bats-core` を導入し、マウント／検証／コピーの主要関数をユニットテスト
- 仮想 USB メモリ（`tmpfs` / ループバック）を用いたインテグレーションテストを GitHub Actions or ローカルスクリプトで実施
- テスト結果は `/srv/rpi-server/logs/test-report/` に保存し、定期的に棚卸しする

### 8.8 テスト用仮想 USB 環境 (`scripts/setup_usb_tests.sh`)

ラズパイ上で物理 USB を使わずに検証する場合は、以下のヘルパースクリプトで 3 種類の仮想 USB イメージ（INGEST/DIST/BACKUP）を作成できる。

```bash
cd ~/RaspberryPiServer
./scripts/setup_usb_tests.sh /home/pi/usb-test
```

- `losetup` が使える Linux 環境を前提とする（macOS では不可）。
- 生成後は `/home/pi/usb-test/*.img` にイメージが作成され、`TM-INGEST` / `TM-DIST` / `TM-BACKUP` ラベルを持つループデバイスが割り当てられる。
- 不要になったら `sudo losetup -d /dev/loopX` とイメージ削除で後片付けする。

### 8.9 主要スクリプトと環境変数

| スクリプト | 主な用途 | 既定ディレクトリ / 環境変数 |
| --- | --- | --- |
| `tool-ingest-sync.sh` | INGEST USB → サーバー同期 | `SERVER_ROOT=/srv/rpi-server`, `SERVER_MASTER_DIR`, `SERVER_DOC_DIR`, `USB_INGEST_LABEL=TM-INGEST` |
| `tool-dist-export.sh` | サーバー → DIST USB へエクスポート | 同上 + `USB_DIST_LABEL=TM-DIST` |
| `tool-dist-sync.sh` | DIST USB → 端末ローカル同期 | `LOCAL_MASTER_DIR=/opt/toolmaster/master`, `LOCAL_DOC_DIR=/opt/toolmaster/docviewer`, `USB_DIST_LABEL=TM-DIST` |
| `tool-backup-export.sh` | スナップショットを BACKUP USB へ退避 | `SNAPSHOT_DIR=/srv/rpi-server/snapshots`, `BACKUP_RETENTION=4`, `USB_BACKUP_LABEL=TM-BACKUP` |
| `tool-snapshot.sh` | 日次スナップショット作成 | `SNAPSHOT_ROOT=/srv/rpi-server/snapshots`, `PG_URI` |
| `lib/toolmaster-usb.sh` | 共通ライブラリ | `USB_LOG_DIR=/srv/rpi-server/logs`, `USB_MAX_RETRY=3` |
| （内部処理）`tool-ingest-sync.sh` | USB から取り込んだ `production_plan.csv` / `standard_times.csv` を API 用ディレクトリへ配置 | `PLAN_DATA_DIR=/srv/rpi-server/data/plan`（環境変数で変更可） |

運用環境に合わせて環境変数で上書きできるよう実装している。systemd unit からは `Environment=` 指定で渡す。

> 物理 USB での検証ログは `docs/test-notes/2025-10-25-physical-usb.md` を参照。

## 9. BACKUP 用 USB メモリ初期化とローテーション

### 9.1 初期化手順

1. 管理者端末で USB メモリを接続し、デバイス名を確認。
2. パーティション作成（単一パーティション、ext4 推奨）。
   ```bash
   sudo wipefs -a /dev/sdX
   sudo parted /dev/sdX --script mklabel gpt
   sudo parted /dev/sdX --script mkpart primary ext4 0% 100%
   sudo mkfs.ext4 -L TM-BACKUP /dev/sdX1
   ```
3. シグネチャディレクトリを配置。
   ```bash
   sudo mount /dev/sdX1 /mnt
   sudo mkdir -p /mnt/.toolmaster
   echo "BACKUP" | sudo tee /mnt/.toolmaster/role
   sudo umount /mnt
   ```
4. `docs/requirements.md` に記載した容量要件（64 GB 以上）を満たしているか確認。

### 9.2 ローテーションルール

- バックアップアーカイブは `YYYY-MM-DD_full.tar.zst` のファイル名で保存。
- 保持数は 4 世代（約 4 週間）とし、保存後に `find` で古いファイルを削除。
  ```bash
  find /media/TM-BACKUP -maxdepth 1 -name "*_full.tar.zst" \
      -printf "%T@ %p\n" | sort -n | head -n -4 | cut -d' ' -f2- | xargs -r rm -f
  ```
- コピー完了後は `/srv/rpi-server/logs/backup.log` に下記のような記録を残す。
  ```json
  {"timestamp":"2025-02-20T02:35:00+09:00","archive":"2025-02-20_full.tar.zst","size_bytes":8123456789,"duration_ms":52340,"status":"success"}
  ```

### 9.3 リストア検証

- 月次で 1 世代を選び、テスト用ディレクトリに展開して整合性を確認。
  ```bash
  mkdir -p /srv/rpi-server/tmp-restore
  sudo tar --zstd -xf /media/TM-BACKUP/2025-02-20_full.tar.zst -C /srv/rpi-server/tmp-restore
  ```
- PostgreSQL ダンプのリストアテスト、マスターデータ同期テストを実施し、結果を `backup.log` に追記。

### 9.4 エスカレーション

- バックアップ失敗が 3 回連続した場合は運用担当へ連絡し、USB メモリ交換や外部ストレージ（HDD 等）での代替手段を検討。
- 予備のバックアップメディアを 2 本準備し、週次でローテーション（A/B 運用）する案も検討対象とする。

この手順書は RUNBOOK 整備時に必要箇所を統合・参照すること。
