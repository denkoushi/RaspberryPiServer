# USB メモリ運用手順（INGEST / DIST / BACKUP）

この文書は RaspberryPiServer で運用する USB メモリの役割と操作手順を定義する。サーバー移行後は本手順に従ってデータ同期とバックアップを実施すること。

## 1. 役割と識別方法

| ラベル例 | シグネチャファイル | 主目的 | 挿入先 | 備考 |
| --- | --- | --- | --- | --- |
| `TOOLMASTER-INGEST` | `/.toolmaster/role` に `INGEST` | 外部で更新したマスターデータや PDF をサーバーへ持ち込む | サーバーのみ（書き込みあり） | サーバーが新旧比較後に公式データへマージし、USB メモリ内容を最新化する |
| `TOOLMASTER-DIST` | `/.toolmaster/role` に `DIST` | サーバーの公式データを各端末へ配布 | 端末（DocumentViewer / 工具管理端末） | 端末は常に USB メモリ → 端末への一方向コピー。書き戻しは禁止 |
| `TOOLMASTER-BACKUP` | `/.toolmaster/role` に `BACKUP` | サーバーの世代バックアップを外部保管 | サーバーのみ（書き込みあり） | `udev` 連携で挿入時に最新スナップショットを `tar + zstd` 形式で出力 |

シグネチャファイルが欠落している、または内容が一致しない場合は処理を中断し、`/srv/rpi-server/logs/usb_guard.log` に警告を出力する。

## 2. サーバーへの持込み（INGEST）

### 前提
- USB メモリに以下の構成でファイルを用意しておくこと。

```
TOOLMASTER-INGEST/
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
1. サーバー管理者が `TOOLMASTER-INGEST` をサーバーに挿す。
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
- サーバー側で定期的または必要に応じて `TOOLMASTER-DIST` へ最新データを書き出しておく（手動コマンド例をセクション 5 参照）。
- 端末側（DocumentViewer、工具管理端末）には `/usr/local/bin/tool-dist-sync.sh` を配置する。

### 手順
1. 担当者が `TOOLMASTER-DIST` を端末に挿す。
2. 端末側の udev ルールが `/.toolmaster/role` を確認し、`DIST` であることを検証。
3. `tool-dist-sync.sh` は USB メモリの `master/`、`docviewer/` を読み込み、端末ローカルのデータディレクトリを上書きコピーする。
4. コピー完了後、ログを `/var/log/tool-dist-sync.log` に追記し、端末のアプリケーション（DocumentViewer や工具管理 UI）へリロード通知を送る。

### 注意事項
- 端末は USB メモリへ書き込まない。`DIST` を誤ってサーバーに挿した場合はスクリプトが処理を中断し、ログで警告する。
- 大容量 PDF の同期が必要な場合は、端末側の空き容量を事前に確認する。

## 4. バックアップ（BACKUP）

### 前提
- サーバーは cron または systemd timer で `/srv/rpi-server` 配下のデータを日次スナップショット（7 世代）として保持する（`/srv/rpi-server/snapshots/YYYY-MM-DD/`）。
- バックアップ専用 USB メモリ（`TOOLMASTER-BACKUP`）を準備し、64 GB 以上の容量を確保する。

### 手順
1. 管理者が `TOOLMASTER-BACKUP` をサーバーに挿す。
2. `usb-backup@<デバイス>.service` が起動し、シグネチャを確認。
3. 最新スナップショットを `tar` + `zstd` で圧縮し、USB メモリ直下に `YYYY-MM-DD_full.tar.zst` という名前で保存する。
4. USB メモリ上のアーカイブが 4 ファイルを超えた場合は最も古いものから削除。
5. 結果は `/srv/rpi-server/logs/backup.log` に追記。完了後に安全な取り外しを実施する。

### エラー時の対処
- 容量不足の場合は処理を中断し、ログに必要容量を記録する。必要に応じて上位のバックアップ手順（外付け SSD 等）へエスカレーション。
- 圧縮中にエラーが発生した場合は `tar` / `zstd` の標準エラーをログに取り込み、再実行前にディスク状態とファイル破損を確認する。

## 5. 手動同期コマンド例

### サーバーで INGEST 用 USB メモリを最新化
```bash
sudo /usr/local/bin/tool-ingest-sync.sh --refresh
```

### サーバーで DIST 用 USB メモリへ書き出し
```bash
sudo /usr/local/bin/tool-dist-export.sh --target /media/TOOLMASTER-DIST
```

### 日次スナップショット作成（systemd timer から呼び出し）
```bash
/usr/local/bin/tool-snapshot.sh --dest /srv/rpi-server/snapshots
```

### 最新スナップショットを BACKUP 用 USB メモリへコピー
```bash
sudo /usr/local/bin/tool-backup-export.sh --target /media/TOOLMASTER-BACKUP
```

## 6. 今後の実装タスク

- `tool-ingest-sync.sh` / `tool-dist-export.sh` / `tool-backup-export.sh` の実装（ラベル・シグネチャ検証、例外処理、ログ出力）
- `udev` ルールと systemd unit（`usb-ingest@.service`、`usb-backup@.service`）の作成
- 既存 Window A の USB スクリプトからの差分洗い出しと移植計画策定
- エラー発生時の運用ルール整備（担当者連絡先、USB メモリ交換手順など）

## 7. systemd / udev 設計案

### 7.1 udev ルール

`/etc/udev/rules.d/90-toolmaster.rules`

```
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="TOOLMASTER-INGEST", \
    ENV{SYSTEMD_WANTS}="usb-ingest@%k.service"

ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="TOOLMASTER-BACKUP", \
    ENV{SYSTEMD_WANTS}="usb-backup@%k.service"

ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="TOOLMASTER-DIST", \
    ENV{SYSTEMD_WANTS}="usb-dist-notify@%k.service"
```

※ `TOOLMASTER-DIST` は端末側での自動実行用に使用する。サーバー側では通知のみ。

### 7.2 systemd unit テンプレート

`/etc/systemd/system/usb-ingest@.service`

```ini
[Unit]
Description=Toolmaster USB ingest for %I
Requires=local-fs.target
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/tool-ingest-sync.sh --device /dev/%I
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

`usb-backup@.service` と `usb-dist-notify@.service` も同様に `ExecStart` のスクリプトを差し替えて用意する。

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

### 7.4 ログ出力

- サーバー側: `/srv/rpi-server/logs/usb_ingest.log`、`usb_backup.log`、`usb_guard.log`
- 端末側: `/var/log/tool-dist-sync.log`
- `journalctl -u usb-ingest@*` などで詳細を確認可能

### 7.5 リトライと失敗時のハンドリング

- 失敗時は exit code ≠ 0 を返し、systemd が `StartLimitBurst` に達したら `OnFailure` で通知用スクリプト（LED 点滅・ログ出力など）を呼び出す。
- USB メモリの不整合（シグネチャ不一致、容量不足など）はスクリプト内で `usb_guard.log` に記録し、ユーザーに交換を促す。

この手順書は RUNBOOK 整備時に必要箇所を統合・参照すること。
