# USB スクリプト ループバック検証ログ（2025-10-25）

本メモは RaspberryPiServer 上で USB 運用スクリプトをループバックデバイスで検証した結果を記録する。  
テスト環境: Raspberry Pi 5（SSD ブート）, RaspberryPiServer ブランチ `feature/server-ops-docs` @ `4774d16`.

## 準備
- `sudo apt install git rsync jq tar zstd bats` を実行し依存パッケージを導入。
- `~/RaspberryPiServer` を `git checkout feature/server-ops-docs && git pull --ff-only` で最新化。
- ループバック用イメージを手動作成（1 GB ×2, 8 GB ×1）し、`TM-INGEST` / `TM-DIST` / `TM-BACKUP` ラベルと `.toolmaster/role` を付与。
- サーバー側ディレクトリ `/srv/rpi-server/master`, `/srv/rpi-server/docviewer` を作成しテストデータを投入。

## 実施項目

| 項目 | コマンド / 手順 | 結果 |
| --- | --- | --- |
| INGEST dry-run | `sudo scripts/tool-ingest-sync.sh --device /dev/loop1 --dry-run` | 差分表示を確認。 |
| INGEST 本実行 | `sudo scripts/tool-ingest-sync.sh --device /dev/loop1` | サーバー側 CSV/`meta.json` が更新。USB 側も書き戻し済み。 |
| Plan cache refresh | `/srv/rpi-server/logs/usb_ingest.log` に `plan cache refresh` ログを確認 | `/internal/plan-cache/refresh` が自動呼び出しされ、REST が即時更新されることを確認。 |
| DIST dry-run | `sudo scripts/tool-dist-export.sh --device /dev/loop2 --dry-run` | 差分表示。 |
| DIST 本実行 | `sudo scripts/tool-dist-export.sh --device /dev/loop2` | USB に `master/` `docviewer/` が出力。 |
| DIST 同期 dry-run | `scripts/tool-dist-sync.sh --device /dev/loop2 --dry-run` | `/srv/rpi-server/logs/usb_dist_sync.log` に差分記録。 |
| DIST 同期 本実行 | `LOCAL_*` 環境変数を指定し `/tmp/toolmaster-test/` へ同期 | 端末ローカル用ディレクトリにデータ反映。 |
| スナップショット dry-run | `sudo scripts/tool-snapshot.sh --dry-run` | `snapshot.log` に想定処理記録。 |
| バックアップ dry-run | `sudo scripts/tool-backup-export.sh --device /dev/loop3 --dry-run` | `usb_backup.log` に差分記録（スナップショット作成後）。 |
| バックアップ 本実行 | `sudo scripts/tool-backup-export.sh --device /dev/loop3` | `/mnt/backup/test-snapshot_full.tar.zst` を生成。 |

## ログ確認
- `usb_ingest.log`, `usb_dist_sync.log`, `usb_backup.log`, `snapshot.log` を tail し、dry-run と本実行の両方が記録されていることを確認。

## 後片付け
- `sudo umount /mnt/dist /mnt/backup`, `sudo losetup -d /dev/loop2 /dev/loop3`。
- 必要に応じて `~/usb-test/*.img` を削除してクリーンアップ。

## メモ
- ext4 ラベルは 16 文字制限のため `TM-INGEST` 等を採用。既存メディアで異なるラベルを使う場合は環境変数 `USB_INGEST_LABEL` 等で上書きする。
- 仮想 USB 作成を自動化する補助スクリプト `scripts/setup_usb_tests.sh` を追加済み（`losetup` が利用できる Linux 環境向け）。
