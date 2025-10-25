# OnSiteLogistics ミラー検証設計

この文書は OnSiteLogistics の送信先を新サーバーへ切り替える際に実施するミラー運用の実装設計をまとめる。`docs/requirements.md` の決定事項に基づき、ログ取得・差分検証・ロールバック手順を明確化する。

## 1. 目的

- 旧サーバー（Window A）と新サーバー（RaspberryPiServer）が同じデータを受信していることを 14 日連続で確認する。
- 差分が発生した場合は内容・原因を記録し、再発防止策を立てた上で判定をリセットする。
- ミラー運用の開始・停止を安全に制御し、即時ロールバックが可能な状態を保つ。

## 2. ミラー送信構成

### 2.1 Pi Zero 2 W（OnSiteLogistics）

- 既存の送信処理に「ミラー送信モード」を追加。
- 設定ファイル例:

```json
{
  "primary_endpoint": "http://window-a.local:8501/api/v1/scans",
  "mirror_endpoint": "http://raspi-server.local:8501/api/v1/scans",
  "mirror_mode": true,
  "timeout_ms": 3000,
  "retry": {
    "max_attempts": 3,
    "backoff_ms": 500
  }
}
```

- ミラー送信時は以下の順序を徹底する。
  1. プライマリ（旧サーバー）へ送信し、HTTP 200 を確認。
  2. ミラー（新サーバー）へ同一 payload を送信し、レスポンスのステータス・所要時間を計測。
  3. どちらかが失敗した場合はローカルキューに残し、後続の再送ジョブでリトライ。

### 2.2 再送ジョブ

- ローカル SQLite もしくはファイルキューに送信 payload を保持。
- `mirror_mode` 中は「旧サーバー成功／新サーバー失敗」のケースもロギングしてリトライ対象に含める。

## 3. 新サーバー側ログ収集

- 受信した payload を JSON で `/srv/rpi-server/logs/mirror_requests.log` に追記。
- ログ形式（1 行 1 レコード）:

```json
{
  "timestamp": "2025-02-20T10:15:03Z",
  "device_id": "HANDHELD-01",
  "payload": {"station":"A","location":"SHELF-03","lot":"LOT-123"},
  "response_ms": 128,
  "status": 200
}
```

- ログ肥大化を防ぐため、`logrotate` で日次ローテーション（保管 30 日）。

## 4. 差分検証スクリプト

- スクリプト: `/usr/local/bin/mirror-compare.sh`
- 実行タイミング: systemd timer `mirror-compare.timer`（毎日 02:00）

### 4.1 処理フロー

1. 旧サーバー（Window A）の PostgreSQL へリモート接続し、`part_locations` の最新行（`ORDER BY updated_at DESC LIMIT 1000`）を取得。
2. 新サーバー側の `part_locations` から同条件で抽出。
3. 各レコードをキー（`tag_id`, `order_id` など）で突き合わせ、タイムスタンプと値を比較。
4. 差分がゼロ → `mirror_status.log` に `OK` を記録。
5. 差分が存在 → `mirror_diff.log` に詳細（キー、旧値、新値、検出時刻）を JSON で追記し、`mirror_status.log` に `NG` を記録。
6. 結果に応じて連続 OK 日数を `/var/lib/mirror/ok_counter` に保管。NG 時はカウンタをリセット。

### 4.2 差分の扱い

- `NG` の場合はドキュメントに沿って原因調査を行い、修正後に再度 OK カウントを積み上げる。
- 14 日連続で `OK` になった時点で切替条件を満たす。

## 5. ミラー制御コマンド

- `mirrorctl enable` : `mirror_mode=true` に設定し、Pi Zero 2 W へコマンドを push。また systemd timer（`mirror-compare.timer`）を有効化。
- `mirrorctl disable`: `mirror_mode=false` に戻し、ミラー用ログのローテーションと圧縮を実施。
- `mirrorctl status` : 現在のミラー状態、最新比較結果、カウンタ値を表示。

## 6. ロールバック手順

- 新サーバーで問題が発生した場合:
  1. `mirrorctl disable` でミラーを停止。
  2. Pi Zero 2 W 設定から `mirror_endpoint` を削除。
  3. 旧サーバーのみで運用を継続し、差分ログを調査。
  4. 原因が解消したら再度 `mirrorctl enable` でミラーを再開。

## 7. 監視・アラート

- `mirror_status.log` の結果を日次でチェックする systemd timer を設定し、`NG` が続く場合はローカル通知（LED 点灯／警告ログ）を行う。
- 必要に応じて Slack などの外部通知へ拡張できるようインタフェースを分離。

## 8. 実装タスク

- OnSiteLogistics 側のミラー送信モード実装（HTTP 二重送信とキュー管理）
- RaspberryPiServer 側のログ・比較スクリプト実装と systemd timer 設定
- `mirrorctl` CLI の実装（Python または Bash）
- 運用ドキュメント（RUNBOOK）への切替判断フロー追記

## 9. `mirrorctl` CLI 仕様

### 9.1 コマンド一覧

| コマンド | 機能 | 主要処理 | 戻り値 |
| --- | --- | --- | --- |
| `mirrorctl enable` | ミラー送信開始 | Pi Zero 2 W へ `mirror_mode=true` を適用し、`mirror-compare.timer` を `systemctl enable --now` | 成功:0, 失敗:≠0 |
| `mirrorctl disable` | ミラー送信停止 | `mirror_mode=false` を適用し、タイマーを無効化。ログをアーカイブ | 成功:0, 失敗:≠0 |
| `mirrorctl status` | 現在状況表示 | OK カウンタ、最新比較結果、ミラー送信遅延の統計を表示 | 成功:0 |
| `mirrorctl rotate` | ログローテーション | `mirror_requests.log`, `mirror_diff.log` を gzip 圧縮し、30 日より古いファイルを削除 | 成功:0 |

### 9.2 設定ファイル

- `/etc/mirrorctl/config.json`

```json
{
  "pi_zero_host": "onsite-handheld.local",
  "ssh_user": "pi",
  "config_path": "/etc/onsitelogistics/config.json",
  "status_dir": "/var/lib/mirror"
}
```

### 9.3 ステータス表示フォーマット

```
Mirror Mode   : enabled
OK Streak     : 5 days (target 14)
Last Compare  : 2025-02-20 02:00 JST (OK)
Last Diff     : 2025-02-17 02:00 JST (2 records)
Avg Latency   : primary 110 ms / mirror 130 ms (24h)
```

### 9.4 テスト計画

- 単体テスト
  - `mirrorctl status` が設定ファイルから値を取得できるか（設定ファイル欠落時はエラー）
  - SSH 通信失敗時のエラーハンドリング（タイムアウト、認証エラー）
- 結合テスト
  - ミラー有効化後、Pi Zero 2 W の設定が更新されるか（`jq` で `mirror_mode` を確認）
  - タイマー起動後に `systemctl list-timers` で `mirror-compare.timer` が稼働しているか
  - `mirrorctl disable` 実行後にカウンタ・設定が正しく停止するか
- フェイルオーバーテスト
  - 新サーバー停止状態で `mirrorctl enable` を実行し、エラーメッセージが適切か
  - `mirrorctl rotate` が大きなログファイルを適切に圧縮・削除するか（テスト用ダミーファイルで検証）

### 9.5 ログとエラー通知

- `mirrorctl` 実行ログは `/srv/rpi-server/logs/mirrorctl.log` に保存。
- エラー時には exit code とともに `journalctl` に出力し、必要に応じて LED 点滅や通知スクリプトへ連携する仕組みを用意する。

本設計は基盤実装前のたたき台として扱い、進捗に応じて更新する。
