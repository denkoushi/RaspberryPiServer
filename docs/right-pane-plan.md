# Window A 右ペイン機能モジュール化プラン

このドキュメントは、旧 Window A（Raspberry Pi 4 No.1）上で稼働していた複合クライアント機能をモジュール化し、新しい三層構成（Pi5 サーバー / Pi Zero 2 W ハンディ / Pi4 クライアント）へ段階的に移行するための計画をまとめる。

## 1. ゴールと前提

- Pi5 (RaspberryPiServer) が REST API・Socket.IO・USB 配布・バックアップの単一ハブとなる。
- Pi Zero 2 W はハンディリーダ専用の軽量クライアントとして `mirrorctl` / `mirror_compare` の 14 日連続安定運用を達成する。
- Window A (Pi4) は右ペイン UI 群（DocumentViewer、工具管理、構内物流、標準工数、生産日程）をクライアント専用として再構成し、必要なデータ／イベントをすべて Pi5 から取得する。
- 新構成では Pi4 側でサーバー処理を持たず、環境ファイルと systemd サービスでクライアント機能を個別に起動・停止できることを最小要件とする。

## 2. 対象機能の棚卸し

| 機能カテゴリ | 旧構成の役割 | 新構成での方針 | 主要リポジトリ | メモ |
| --- | --- | --- | --- | --- |
| DocumentViewer | REST + Socket.IO + PDF 配布まで一体運用 | REST/API は Pi5 へ移行済み。Pi4 は Web UI + Socket.IO クライアントのみ残す | `DocumentViewer` | `VIEWER_API_BASE`、`SOCKETIO_ENDPOINT` を Pi5 参照に固定 |
| 工具管理 UI | 在庫照会・棚卸 CSV 取込をローカル Flask で提供 | UI を React/Vue etc. へ移行せず、既存 Flask をクライアントモード化し API 呼び先を Pi5 へ | `tool-management-system02` | サーバー機能は削除し、`/srv/rpi-server` データを参照する CLI を用意 |
| 構内物流 (OnSiteLogistics) | スキャンイベントと指示書 PDF をローカル DB へ格納 | スキャンは Pi5 REST / Socket.IO。Pi4 はディスプレイ UI とアラート表示のみ | `OnSiteLogistics` | ハンディ連携は Pi5 側で完結、Pi4 は viewer role |
| 標準工数 | Excel 取り込みと参照画面をローカルで完結 | 取り込み処理を Pi5 のバックエンドへ移し、Pi4 は参照画面のみ | `DocumentViewer` (右ペイン) | 取り込みスクリプトは Pi5 側の `tool-ingest-sync.sh` に統合検討 |
| 生産日程 | CSV → SQLite → 表示 | データ取り込みを Pi5 で cron 化し、Pi4 は API から取得して表示 | （未分離、要リポジトリ化） | まず既存ソースを抽出し、`docs/right-pane-plan.md` に移行計画を追記 |

## 3. モジュール化ロードマップ

1. **DocumentViewer クライアント分離**  
   - `DocumentViewer` リポジトリで `VIEWER_API_BASE` を `.env` から読み込み、既定値を `http://raspi-server.local:8501` に変更。  
   - Socket.IO クライアントの接続確認を `docs/test-notes/2025-10-30-end-to-end.md` に追記し、Pi4 → Pi5 で PDF 表示が成立することを記録。  
   - クライアント向け RUNBOOK（Window A 用）を整備し、Pi5 の停止時のロールバック手順を明記。

2. **工具管理 UI のクライアント化**  
   - `tool-management-system02` の server サービスを無効化し、API 呼び出しを Pi5 へリダイレクトする設定ファイル (`/etc/default/toolmgmt-client`) を新設。  
   - Pi5 側に必要なエンドポイントが欠けている場合は `RaspberryPiServer` に追加し、`docs/requirements.md` のタスクへ紐付け。  
   - 統合作業の証跡は `docs/test-notes/<date>-toolmgmt-client.md` に記録。

3. **構内物流 UI の Socket.IO 化**  
   - OnSiteLogistics リポジトリで `scripts/handheld_scan_display.py` 新 CLI を活用し、Pi5 からの `scan_update` を購読する。  
   - Pi4 側で `systemd` ユニット（例: `onsite-display.service`）を作成し、再起動時に自動でソケット接続。  
   - UI 側で Pi5 未接続時のリトライや警告表示を実装。

4. **標準工数 / 生産日程の分割**  
   - 既存ローカル DB / CSV 取り込みスクリプトを抽出し、Pi5 へ REST 経由でアップロードできる CLI を設計。  
   - Pi4 側は参照のみを行い、更新権限を持たないようにする。  
   - 完了後は旧 Pi4 に残る cron / スクリプトを削除し、`docs/requirements.md` Decision Log へ記録。

5. **統合テストと 14 日連続検証**  
   - Pi5 + Pi Zero + Pi4 の組合せで日次チェックを 14 日間連続実施。  
   - `docs/test-notes/` に日次ログを残し、完了したら Decision Log へ「Window A クライアント化完了」を記録。

## 4. 追加課題とメモ

- Pi4 用の共通環境ファイルテンプレート（例: `config/window-a.env.sample`）を整備し、DocumentViewer / 工具管理 / 構内物流で再利用する。  
- Pi4 から Pi5 へアクセスする際のネットワーク要件（mDNS、静的 IP）を整理し、`RUNBOOK` と `docs/requirements.md` へ反映する。  
- 既存ログ（`/var/log/document-viewer`、`/var/log/toolmgmt` など）と新ログ体系の差分を棚卸しし、必要なものを Pi5 へ集約。  
- Pi4 の UI 群で共通に使うコンポーネント（Socket.IO リスナ、API クライアント）をライブラリ化し、重複を排除する。

---

本計画に変更が生じた場合は、`docs/requirements.md` の移行タスクと本ファイルを同時に更新し、`AGENTS.md` のリンク集も忘れずに追随させること。
