# 2025-10-26 DocumentViewer RaspberryPiServer 接続方針

## 目的
- DocumentViewer の Socket.IO / REST 接続先を RaspberryPiServer へ切り替えるための作業計画を整理する。
- 次回以降の実装・検証で必要なタスクを具体化する。

## 現状
- Socket.IO の接続先は旧サーバー (Window A) を前提としている。
- RaspberryPiServer 側では `/api/v1/scans` が稼働しており、今後工具管理 UI・DocumentViewer 右ペインを統合予定。

## 次のアクション
1. Socket.IO 接続先を環境変数で切り替えられるよう `app/static/app.js` をリファクタリングする。
2. RaspberryPiServer の Socket.IO エンドポイント設計（tool-management-system02 側）と連携し、DocumentViewer が参照する API を統一する。
3. ログ出力（`docviewer.service`）を 14 日チェックで活用できるよう整備し、RUNBOOK へ反映する。
