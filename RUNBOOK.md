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
