# 2025-10-26 DocumentViewer RaspberryPiServer 接続方針

## 目的
- DocumentViewer の Socket.IO / REST 接続先を RaspberryPiServer へ切り替えるための作業計画を整理する。
- 次回以降の実装・検証で必要なタスクを具体化する。

## 現状
- Socket.IO の接続先は旧サーバー (Window A) を前提としている。
- RaspberryPiServer 側では `/api/v1/scans` が稼働しており、今後工具管理 UI・DocumentViewer 右ペインを統合予定。

## 次のアクション
1. Window A 実機で `scripts/install_window_a_env.sh --with-dropin` を実行し、Socket.IO 接続先を RaspberryPiServer へ切り替える。
2. DocumentViewer（Window A）と RaspberryPiServer との通信を Pi Zero からのスキャンで確認（Socket.IO イベント受信、自動表示）。
3. `docviewer.service` のログを 14 日チェックの記録で活用できるよう RUNBOOK を整備する。
