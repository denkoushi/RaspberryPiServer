# mirrorctl CLI 設計メモ

## 1. 目的
OnSiteLogistics のミラー運用を切り替える際に、RaspberryPiServer 上でまとめて制御・状況確認を行う CLI ツールを提供する。`docs/mirror-verification.md` に記載した決定事項を実装するためのインターフェース仕様。

## 2. コマンド構成

| コマンド | 説明 |
| --- | --- |
| `mirrorctl enable` | ミラー送信を有効化し、Pi Zero 設定と比較タイマーを起動する |
| `mirrorctl disable` | ミラー送信を停止し、比較タイマーを無効化する |
| `mirrorctl status` | 現在の設定・比較結果・OK 連続日数を表示する |
| `mirrorctl rotate` | ログファイル（`mirror_requests.log`, `mirror_diff.log`）をローテーションする |

## 3. 主な処理フロー

### 3.1 enable
1. Pi Zero (OnSiteLogistics) へ SSH し、`/etc/onsitelogistics/config.json` の `mirror_mode=true` と `mirror_endpoint` を設定。
2. `sudo systemctl restart onsite-handheld.service` 等、Pi Zero 側のサービス再起動。
3. RaspberryPiServer 側で `mirror-compare.timer` を `systemctl enable --now`。
4. 初期化として OK カウンタを 0 にリセット、ログローテーションを実施。

### 3.2 disable
1. Pi Zero 側設定で `mirror_mode=false` に戻し、`mirror_endpoint` を削除。
2. `mirror-compare.timer` を `systemctl disable --now`。
3. ログ末尾に停止時刻を記録し、必要に応じてアーカイブ。

### 3.3 status
表示項目例:
- ミラー状態（enabled/disabled）
- OK ストリーク日数 / 目標 (例: `5 / 14`)
- 最終比較時刻と結果 (`OK` or 差分件数)
- Pi Zero 側設定 (`primary_endpoint`, `mirror_endpoint`)
- 過去 24 時間の遅延平均（mirror_requests.log から算出）

### 3.4 rotate
- `mirror_requests.log` と `mirror_diff.log` を gzip 圧縮（例: `mirror_requests-20250220.log.gz`）し、30 日より古いファイルを削除。

## 4. 実装メモ
- 言語: Python（`argparse` + `subprocess` + `json`) を想定。
- Pi Zero への SSH: `paramiko` もしくは `ssh` コマンド（公開鍵認証前提）。
- 設定ファイル: `/etc/mirrorctl/config.json` に以下を保持。
  - リポジトリにはサンプルとして `config/mirrorctl-config.sample.json` を配置（デプロイ時に `/etc/mirrorctl/config.json` へ展開）。
  ```json
  {
    "pi_zero_host": "handheld.local",
    "ssh_user": "pi",
    "config_path": "/etc/onsitelogistics/config.json",
    "status_dir": "/var/lib/mirror",
    "log_dir": "/srv/rpi-server/logs",
    "ok_counter_file": "/var/lib/mirror/ok_counter",
    "mirror_timer": "mirror-compare.timer",
    "mirror_service": "mirror-compare.service",
    "pi_zero_service": "onsite-handheld.service",
    "mirror_endpoint": "http://raspi-server.local:8501/api/v1/scans",
    "primary_endpoint": "http://window-a.local:8501/api/v1/scans",
    "log_retention_days": 30
  }
  ```
- OK カウンタ: `/var/lib/mirror/ok_counter` に整数値を保持。
- `mirror_compare.py`: 日次比較スクリプト（Python）で比較結果を JSON ログに記録。依存パッケージ: `python3-psycopg2`。

## 5. TODO
- `mirror_compare.py` の仕様書と連携フォーマット（JSON）確定。
- Pi Zero 側の設定テンプレートを `docs/implementation-plan.md` に追記。
- CI/自動テスト: ループバック環境で `mirrorctl enable` → `status` → `disable` の動作確認手順を用意。

### 実装メモ（2025-10-25 更新）
- `scripts/mirrorctl.py` で `status/enable/disable/rotate` を実装。Pi Zero 設定のバックアップ→書き換え、SSH 経由のサービス再起動、mirror-compare.timer の制御、ログローテーションまで対応。
- 設定テンプレートは `config/mirrorctl-config.sample.json` を参照し、`mirror_endpoint` や `pi_zero_service`、ログ保持日数などを調整可能。
- systemd ユニット `systemd/mirror-compare.service` / `.timer` を用意し、`mirror_compare.py` を日次で実行できるようにした。
