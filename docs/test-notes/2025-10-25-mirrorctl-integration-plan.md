# 2025-10-25 mirrorctl / mirror_compare 統合テスト計画

## 目的
- RaspberryPiServer 上の `mirrorctl` と `mirror_compare.py`、および Pi Zero 側設定反映の連携動作を検証し、ミラー送信開始〜差分比較までの一連フローを確認する。

## 前提条件
- RaspberryPiServer の `feature/server-ops-docs` ブランチを最新化済み。
- `mirrorctl` / `mirror_compare.py` を `/usr/local/bin` に配置済み、`python3-psycopg2` など必要パッケージ導入済み。
- Pi Zero 側 SSH 鍵認証が完了し、`onsite-handheld.service` が有効。`/etc/onsitelogistics/config.json` への書き込み権限を確認済み。
- Window A 側 PostgreSQL が稼働し、`part_locations` テーブルに最新データが保持されている。

## テスト項目
| # | テスト内容 | 手順 | 期待結果 | 備考 |
| --- | --- | --- | --- | --- |
| 1 | mirrorctl 設定確認 | `mirrorctl status` | タイマー/サービス `inactive/disabled`、OK カウンタ数値が表示される | 初期状態 |
| 2 | ミラー有効化 | `sudo mirrorctl enable` | Pi Zero 設定 `mirror_mode=true`、`mirror-compare.timer` が `enabled/active` | Pi Zero 設定差分を `ssh` で確認 |
| 3 | mirrorctl status 再確認 | `mirrorctl status` | OK カウンタ=0、タイマー/サービス `active/enabled`、最新ログに `enable executed` | |
| 4 | mirror_compare 手動実行 | `sudo mirror_compare.py --strict` | 差分なしなら `mirror_status.log` に `OK` 追記、差分ありなら `mirror_diff.log` に JSON 出力 | 差分発生時は #5 へ |
| 5 | 差分解析 | `jq` で `mirror_diff.log` 最新行確認 | 差分内容（missing/field mismatch）が確認できる | 差分解消できるまで繰り返す |
| 6 | OKストリーク確認 | `sudo cat /var/lib/mirror/ok_counter` | 差分がなければ 1 → タイマー実行毎に加算 | 14 連続で切替条件達成 |
| 7 | タイマー稼働確認 | `systemctl list-timers mirror-compare.timer` | 次回起動時刻・最終実行時刻が表示される | `journalctl -u mirror-compare.service` も確認 |
| 8 | ミラー停止 | `sudo mirrorctl disable` | Pi Zero 設定 `mirror_mode=false`、タイマー `disabled/inactive`、ログに `disable executed` | |
| 9 | ローテーション | `sudo mirrorctl rotate` | 既存ログが `.gz` に圧縮され、30 日より古いものは削除 | `ls /srv/rpi-server/logs` で確認 |

## ケース別チェックリスト
- **差分発生時**: `diff` 情報をもとに Window A / RaspberryPiServer 双方の `part_locations` を再確認し、必要に応じて再同期やログ点検を実施する。
- **SSH エラー時**: `ssh pi@onsite-handheld.local` でログインできるか確認し、鍵配置を修正。`mirrorctl enable` を再実行。
- **timer エラー時**: `journalctl -u mirror-compare.service` のスタックトレースを確認し、DB URI や資格情報を見直す。

## フォローアップ
- テスト完了後、結果を `docs/test-notes/` 配下にログとして追加する。
- 14 日連続 OK 達成後、`docs/requirements.md` のミラー切替条件達成を記録し、RUNBOOK に移行手順を追記する。
