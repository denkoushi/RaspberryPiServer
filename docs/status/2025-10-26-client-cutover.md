# 2025-10-26 クライアント切替準備メモ

本メモは RaspberryPiServer への切替に向け、各リポジトリの現行ブランチで実施した作業と残タスクを整理する。  
対象日は 2025-10-26、ブランチ名は作業時点のものを記載する。

## 1. Window A（tool-management-system02 / feature/client-socket-cutover）

- 実施済み
  - `UPSTREAM_SOCKET_*` 環境変数で Socket.IO 接続先を切り替えられるよう改修。
  - `scripts/install_window_a_env.sh --with-dropin` を追加し、環境ファイルと systemd drop-in の展開を自動化。
  - README / RUNBOOK / `docs/right-pane-plan.md` に設定手順を追記。
- 未実施（要実機）
  - `/etc/systemd/system/toolmgmt.service.d/window-a.conf` の適用と `toolmgmt.service` 再起動。
  - 実機ブラウザでの LIVE 表示確認、`/api/v1/scans` 発行後の自動更新確認。

## 2. Window D（OnSiteLogistics / feature/logging-enhancements）

- 実施済み
  - `scripts/install_client_config.sh` を追加し、Pi Zero の `/etc/onsitelogistics/config.json` 生成を自動化。
  - README / `docs/handheld-reader.md` にスクリプト利用例、再起動手順、`curl` での疎通確認手順を追記。
  - `tests/test_config_sample.py` を追加し、サンプル設定の必須項目を検証（pytest 実行済み）。
- 未実施（要実機）
  - `sudo ./scripts/install_client_config.sh --api-url http://raspi-server.local:8501/api/v1/scans ...` の実行。
  - `handheld@<user>.service` の再起動と `curl` → HTTP 201 ↩︎ の確認。
  - Pi Zero から送信したイベントが RaspberryPiServer の `part_locations` に反映されるか現地で点検。

## 3. DocumentViewer（feature/api-endpoint）

- 実施済み
  - `VIEWER_SOCKET_*` 環境変数に対応し、Socket.IO イベント受信で PDF を自動表示。
  - `docs/documentviewer-migration.md` に完了状況を反映。
- 未実施（要実機）
  - Window A 側 iframe 切替後の実機表示確認。

## 4. 大枠スケジュールの次アクション

1. Window A 実機で環境ファイル＋ drop-in を適用 → `toolmgmt.service` 再起動 → Socket.IO LIVE 表示確認。
2. Pi Zero 実機で `install_client_config.sh` を実行 → サービス再起動 → `curl` + `journalctl` で送信確認。
3. 2台が新サーバー接続で安定したら、14 日試運転チェックリスト（`docs/mirror-verification.md`）を開始。
4. 手順確認後、RUNBOOK / CHANGELOG を更新し、本番切替時期を決定する。

必要に応じ、各リポジトリのブランチをマージ or リリースブランチへ統合する。
