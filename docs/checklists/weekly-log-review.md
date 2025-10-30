# 週次ログ点検チェックリスト

対象: RaspberryPiServer 運用担当  
目的: `/srv/rpi-server/logs/` 配下のログサイズと WARN/ERROR を週次で確認し、異常兆候を早期に検知する。

## 事前条件

- RaspberryPiServer リポジトリを `~/RaspberryPiServer` へ展開済み。
- `scripts/check_storage_logs.sh` を実行できる権限（通常は `sudo`）を持つ。
- 必要に応じて `LOG_ROOT`（標準 `/srv/rpi-server/logs`）や検査期間 `DAYS`、出力行数 `TAIL_LINES` を環境変数で変更する。

## 手順

1. 最新コードへ更新  
   ```bash
   cd ~/RaspberryPiServer
   git pull origin feature/server-app
   ```
   期待結果: `Already up to date.` あるいは Fast-forward で最新化される。

2. 週次点検スクリプトを実行  
   ```bash
   cd ~/RaspberryPiServer
   sudo ./scripts/check_storage_logs.sh
   ```
   期待結果:  
   - ログルートのサイズ、直近更新ファイル一覧、容量上位ファイルの一覧が表示される。  
   - WARN/ERROR パターンが検出されなければ `[OK]` が表示され、終了コード 0。  
   - WARN/ERROR が検出された場合は `[WARN]` と共に該当ログの抜粋が表示され、終了コード 2。

3. 結果の保存（任意だが推奨）  
   ```bash
   cd ~/RaspberryPiServer
   sudo ./scripts/check_storage_logs.sh | sudo tee -a /srv/rpi-server/logs/reports/weekly-log-$(date +%Y%m%d).log
   ```
   期待結果: `/srv/rpi-server/logs/reports/` に点検ログが追記される。`reports` ディレクトリが無い場合は `sudo mkdir -p /srv/rpi-server/logs/reports` で作成。

4. 異常があった場合の対応  
   - `[WARN]` が出たファイルについて `sudo tail -n 200 <該当ログ>` や `journalctl` で詳細を確認。  
   - 重大な障害が疑われる場合は `docs/incident-response.md` を参照し、必要に応じてロールバックやサービス再起動を実施。  
   - 対応内容は `docs/test-notes/` 配下に日付付きで記録する。

## 自動化（cron 例）

`/etc/cron.d/raspi-weekly-log` に以下を設定すると、毎週月曜 07:10 にレポートを生成し `/var/log/raspi-server/weekly-log.log` へ追記できる。

```bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
10 7 * * 1 root /home/denkon5ssd/RaspberryPiServer/scripts/check_storage_logs.sh >> /var/log/raspi-server/weekly-log.log 2>&1
```

初回設定時はログ保存先ディレクトリのパーミッションとストレージ残容量を確認すること。
