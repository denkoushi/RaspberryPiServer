# 物理 USB 自動化検証ログ（2025-10-25）

## 概要
- 対象: Raspberry Pi 5 + SSD ブート
- ブランチ: `feature/server-ops-docs` @ 09a99cc
- systemd/udev テンプレート: `systemd/*.service`, `systemd/*.timer`, `udev/90-toolmaster.rules`
- スクリプト配置: `/usr/local/toolmaster/bin`, `/usr/local/lib/toolmaster-usb.sh`

## 手順
1. `systemd/*.service` と `udev/90-toolmaster.rules` を `/etc/systemd/system/`, `/etc/udev/rules.d/` にコピー。
2. `tool-*.sh` を `/usr/local/toolmaster/bin/` に配置、`toolmaster-usb.sh` を `/usr/local/lib/` に配置。
3. シンボリックリンク `/usr/local/bin/tool-*.sh` を作成。
4. `/usr/local/toolmaster/lib/toolmaster-usb.sh` も `/usr/local/lib/` に配置し、`tool-ingest-sync.sh` が読み込めるように修正。
5. `TM-INGEST`, `TM-DIST`, `TM-BACKUP` ラベルの USB メモリを順にテスト。

## 結果
- `TM-INGEST`
  - `journalctl -u usb-ingest@*` に `ingest completed (dry_run=0 force=0)` を確認。
- `TM-DIST`
  - `journalctl -u usb-dist-export@*` に `dist export completed (dry_run=0)` を確認。
- `TM-BACKUP`
  - `journalctl -u usb-backup@*` に `backup export completed archive=...` を確認。
- 失敗原因（`/usr/local/lib/toolmaster-usb.sh` 不在）は再配置で解消。

## メモ
- ラベル変更は `sudo e2label /dev/sdX1 TM-INGEST` のように実施。
- `.toolmaster/role` は手動で `INGEST`, `DIST`, `BACKUP` を書き込む。
- ログは `/srv/rpi-server/logs/usb_ingest.log` などにも出力される。
