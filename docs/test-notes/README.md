# テストログ一覧

`docs/test-notes/` には RaspberryPiServer の検証結果やチェックリストを日付単位で保存しています。新しいログを追加する際は以下のルールに従ってください。

## ファイル命名規則

- `YYYY-MM-DD-topic.md`（例: `2025-10-26-socketio-verification.md`）
- 長期計画やテンプレートの場合は `templates/` ディレクトリを使用する（例: `../templates/test-log-mirror-daily.md`）。

## 記載テンプレート

- 目的
- 前提（ブランチ、環境、対象機器など）
- 手順 / コマンド
- 結果（成功/失敗、ログ抜粋、スクリーンショット参照）
- フォローアップ（必要な対応、課題）

テンプレートが必要な場合は `docs/templates/` に追加し、この README からリンクする。

## 既存ログの概要

- `2025-10-25-mirrorctl-integration-plan.md` — `mirrorctl`/`mirror_compare` の手動検証計画
- `2025-10-25-physical-usb.md` — 物理 USB 自動化検証ログ
- `2025-10-25-postgres-compose.md` — Docker Compose / PostgreSQL 検証ログ
- `2025-10-25-usb-loopback.md` — USB スクリプト ループバック検証
- `2025-10-26-rest-api.md` — REST API / Pi Zero 結合テスト
- `2025-10-26-socketio-verification.md` — Socket.IO 検証ログ
- `2025-10-26-viewer-check.md` — DocumentViewer 接続方針と検証
- `2025-10-30-end-to-end.md` — Pi4 → Pi5 → DocumentViewer の E2E テスト
- `2025-11-01-14day-check.md` — 14 日間ミラーチェック記録（書式のみ、実施時に追記）

## 更新時の注意

- ログを追加・更新したら `docs/docs-index.md` と必要に応じて `docs/templates/` を更新する。
- センシティブな情報（API トークン、パスワード等）は記載しない。必要ならマスクする。
- 実行コマンドと出力は可能な範囲で記録し、再現性を確保する。
