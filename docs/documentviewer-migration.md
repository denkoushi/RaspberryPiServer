# DocumentViewer サーバー機能移行計画

## 1. 現状整理（Window A = tool-management-system02）

- Flask ベースのメインアプリ `app_flask.py` が Socket.IO / REST API / USB 連携をすべて担っている。
- DocumentViewer フロントエンド（右ペイン）は Window A 上で Flask サーバーから配信され、`/api/documents/<部品番号>` で PDF 情報を取得、`/documents/<filename>` から PDF を配信している。
- DocumentViewer への URL は環境変数 `DOCUMENT_VIEWER_URL` として他機能から参照されている。
- 同アプリケーションが工具管理 UI、標準工数、生産計画、構内物流ダッシュボード等の API/UI をまとめて提供しているため、サーバー縮退前に依存関係を分離する必要がある。

## 2. 目標状態（RaspberryPiServer）

- Flask アプリ（`app/server.py`）へ DocumentViewer 用エンドポイントを統合し、以下を提供する。
  - `/viewer` : UI（必要であれば Window A 側でホストしても良いが、RaspberryPiServer でも動作可能にする）
  - `/api/documents/<part_number>` : JSON レスポンス（`found` / `filename` / `url`）
  - `/documents/<filename>` : PDF 配信。`/srv/rpi-server/documents` をデフォルト格納場所とする。
- API は環境変数 `VIEWER_DOCS_DIR`、`VIEWER_DEFAULT_HOST` などでパスやベース URL を切り替えられるようにする。
- CORS 設定を有効化し、Window A（DocumentViewer クライアント）が `http://raspi-server.local:8501` へ fetch してもブロックされないようにする。
- 認証が必要な場合に備え、API トークン（`VIEWER_API_TOKEN`）を Bearer で受け付ける仕組みを実装（DocumentViewer フロントから送信）。
- RaspberryPiServer 側へログを統合し、`/srv/rpi-server/logs/document_viewer.log` へアクセスログを残す。

## 3. 実装ステップ

1. **DocumentViewer Blueprint の追加** ✅ 2025-10-26 完了  
   - `app/document_viewer.py` を新規作成し、Flask Blueprint で `/api/documents` と `/documents` を提供。  
   - PDF ディレクトリは `VIEWER_DOCS_DIR`（既定 `/srv/rpi-server/documents`）を参照し、存在しなければ自動生成。

2. **CORS / 認証対応** ✅ 2025-10-26 完了  
   - `/api/documents/*` に CORS ヘッダー（`VIEWER_CORS_ORIGINS` 環境変数で制御）を付与。  
   - `VIEWER_API_TOKEN` を Bearer 認証で検証できるようにした。

3. **RaspberryPiServer への登録** ✅ 2025-10-26 完了 / 2025-10-26 ログ整備  
   - `app/server.py` の `create_app()` で Blueprint を登録。  
   - systemd 環境ファイル（`/etc/default/raspi-server`）で `VIEWER_DOCS_DIR` / `VIEWER_API_TOKEN` / `VIEWER_CORS_ORIGINS` / `VIEWER_LOG_PATH` を設定できるようにした。  
   - `VIEWER_LOG_PATH`（既定 `/srv/rpi-server/logs/document_viewer.log`）にローテート付きで REST アクセス、未検出、拒否事象を記録。Docker bind mount で `/srv/rpi-server/logs/` を永続化する。  
   - ※ UI ルート `/viewer` は未実装。Window A 側でクライアント UI を配信する場合は不要。必要に応じて別工程で追加する。

4. **Socket.IO イベント送出** ✅ 2025-10-26 完了  
   - `Flask-SocketIO` / `gevent` (+ `gevent-websocket`) を採用し、`/api/v1/scans` 成功時に `part_location_updated` / `scan_update` を broadcast。  
   - 依存不足で発生していた `ConnectionError` を解消するため `websocket-client==1.8.0` を追加。  
   - RaspberryPiServer 上で `docker compose exec -T app python /app/tests/socketio_listener.py` → `curl -X POST http://127.0.0.1:8501/api/v1/scans ...` の手動確認によりイベント受信を検証済み。  
   - Window A のクライアント側実装へ Socket.IO エンドポイントを切り替える作業は別途対応する。

5. **Window A 側の調整**
   - DocumentViewer クライアント（Window A）を RaspberryPiServer の `/viewer` へ向けるか、Window A 側 Flask をクライアント専用に縮退させる。
   - `DOCUMENT_VIEWER_URL` を `http://raspi-server.local:8501/viewer` に更新。
   - `/etc/default/docviewer` は DocumentViewer リポジトリの `config/docviewer.env.sample` をベースに作成し、`VIEWER_API_BASE` / `VIEWER_SOCKET_BASE` / `VIEWER_LOCAL_DOCS_DIR` / `VIEWER_LOG_PATH` などを設定する。
   - API トークンを RaspberryPiServer 側に合わせて再発行し、環境変数 `VIEWER_API_TOKEN` を DocumentViewer フロント／tool-management-system02 双方で設定。
   - DocumentViewer リポジトリ側で `VIEWER_SOCKET_*` 環境変数に対応し、`part_location_updated` 受信時に PDF を自動表示できるようにした（2025-10-26）。

6. **データ移行**
   - 既存 PDF（Window A の `documents/`）を RaspberryPiServer の `/srv/rpi-server/documents` へ同期。
   - USB / git 管理されている PDF 更新手順を RUNBOOK に追記し、DocumentViewer が常に RaspberryPiServer 上の最新ファイルを参照するようにする（ログ確認項目を含む）。

7. **検証手順**
   - 手動テスト: Pi Zero からの送信 → DocumentViewer で表示 → USB DIST で PDF が更新される流れを確認。
   - 14 日チェック: DocumentViewer 連携が問題なく稼働することを日次記録へ追加。

## 4. 残タスク・検討事項

- tool-management-system02 の Socket.IO イベント（`scan_update`, `part_location_updated` 等）を RaspberryPiServer へ移植する際の互換性。DocumentViewer の右ペインが Socket.IO を参照している場合、同タイミングで移行する必要がある。
- Window A 側の Docker / systemd サービスをクライアント専用に再構成し、不要な API を停止。
- CORS 設定の詳細（許可するオリジン、認証ヘッダーの扱い）を最終決定。
- DocumentViewer の UI を RaspberryPiServer 側でホストするか、Window A 側で引き続きホストするかの選択。前者は集約が容易、後者は無停止移行が簡単。
- 自動テスト（API レスポンス、PDF 配信、CORS）を `docs/test-notes/2025-10-26-viewer-check.md` に追加し、将来の回帰を防ぐ。
