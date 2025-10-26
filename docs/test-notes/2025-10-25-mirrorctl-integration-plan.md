# 2025-10-25 mirrorctl / mirror_compare 手動検証計画

## 目的
- `mirrorctl` と `mirror_compare.py` を用いたミラー運用で、Pi Zero → RaspberryPiServer → DocumentViewer → USB 配布までのフローが確実に成立することを手動で確認する。
- 14 日間連続で日次チェックを実施し、問題があれば即時ロールバック・再検証できる体制を整える。

## 前提条件
- RaspberryPiServer の `feature/server-ops-docs` ブランチを最新化済み。
- `mirrorctl` / `mirror_compare.py` を `/usr/local/bin` に配置済み。依存パッケージ（`python3-psycopg` など）を導入済み。
- Pi Zero への SSH 鍵認証が完了し、`/etc/onsitelogistics/config.json` を `mirrorctl` で編集できる。
- DocumentViewer が RaspberryPiServer の Socket.IO へ接続できる状態である。

## 日次検証メニュー

| # | 項目 | 手順 | 期待結果 | 記録欄 |
|---|---|---|---|---|
| 1 | `mirrorctl status` | `mirrorctl status` を実行 | `mirror_mode=true`、タイマー `active/enabled`、OK カウンタ確認 | ○/×・メモ |
| 2 | Pi Zero 送信 | ハンディリーダでサンプルの部品票 + 棚を読み取り | 成功音・表示、Pi Zero ローカルログにエラーなし | ○/×・メモ |
| 3 | API ログ確認 | `sudo tail -n 3 /srv/rpi-server/logs/mirror_requests.log` | 最新エントリに本日の送信が記録される | ○/×・メモ |
| 4 | DB 反映 | `PGPASSWORD=app psql -h localhost -U app -d sensordb -c "...ORDER BY updated_at DESC LIMIT 1"` | `order_code` と `location_code` が最新に更新されている | ○/×・メモ |
| 5 | mirror_compare | `sudo /usr/local/bin/mirror_compare.py --strict` | `mirror_status.log` に `status: OK` が追記される | ○/×・メモ |
| 6 | DocumentViewer | 所在一覧画面で該当オーダーが表示されるか確認 | 画面更新で最新データが反映される | ○/×・メモ |
| 7 | USB フロー | `tool-dist-sync.sh` 等で DIST USB を作成し、端末で取り込み | 端末側で最新データが反映される | ○/×・メモ |
| 8 | 記録 | 上記を日次チェックシートへ記入、異常時はログを添付 | チェックシートが更新される | 実施者・時刻 |

テンプレートは `docs/test-notes/mirror-check-template.md` を利用し、日付ごとに行を追記する。

## 異常時の対応
- いずれかの項目が × になった場合は即座に `sudo mirrorctl disable` を実行し、Pi Zero の送信を停止する。
- `mirror_requests.log` / `mirror_status.log` / `mirror_diff.log` の該当箇所を控え、原因を調査する。
- 原因解消後、再度 `mirrorctl enable` を実行。日次チェックはその日からカウントし直す。

## 14 日連続達成の判定
- 連続日数カウンタは、チェックリストで全項目が ○ だった日に +1 する。
- 途中で × が発生したらカウンタを 0 にリセットし、再度 14 日のカウントを開始する。
- 達成後は Decision Log へ日付と担当者を追記し、RUNBOOK に切替作業の実施記録を残す。

## 参考ログ（2025-10-25 実施）
- 22:05 `/etc/mirrorctl/config.json` の `primary_db_uri` を `postgresql://app:app@localhost:5432/sensordb` へ更新。
- 22:08 `sensordb` に `part_locations` テーブルを新規作成。
- 22:12 `sudo mirrorctl enable` → `mirror-compare.service` が `status=0/SUCCESS`。
- 22:13 `sudo /usr/local/bin/mirror_compare.py --dry-run` → `diff_count=0`、`ok_streak=1` を確認。

> ※ 2025-10-26 にホスト公開ポートを `15432` へ切り替え済み。以降の接続確認は `127.0.0.1:15432` を利用する。

## 参考ログ（2025-10-26 実施）
- `sudo mirrorctl enable` → `mirror-compare.service` が `status=0/SUCCESS`、`mirror-compare.timer` が `active (waiting)`。
- `sudo docker compose down && sudo docker compose up -d` で Postgres ボリュームを再作成し、`curl http://127.0.0.1:8501/healthz` でアプリ正常を確認。
- Pi Zero (`handheld_scan_display.py`) から 3 件のスキャンを送信し、`raspi-server.local` の `/api/v1/scans` が全件受理、`~/.onsitelogistics/scan_queue.db` は 0 件。
- RaspberryPiServer の `postgres` コンテナで `SELECT order_code, location_code FROM part_locations ORDER BY updated_at DESC LIMIT 5;` を実行し、Pi Zero 送信分が反映されていることを確認。
- Pi Zero の `/etc/onsitelogistics/config.json` に RaspberryPiServer 用 API トークンを再設定し、再送時のエラーが解消されることを確認。
- 03:31 `sudo /usr/local/bin/mirror_compare.py --strict` → `status: OK`, `ok_streak: 2`。PostgreSQL をホスト `127.0.0.1:15432` で公開し、`mirrorctl status` でも OK カウンタが 2 へ更新されたことを確認。
