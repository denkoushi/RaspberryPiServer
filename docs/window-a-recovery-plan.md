# Window A DocumentViewer 復旧計画

Window A（tool-management-system02）で DocumentViewer 右ペインが表示されない／Playwright テストが失敗する場合の復旧手順をまとめる。計画表の順に対応することで、環境変数不足・サービス起動失敗・DOM 未生成といった問題を切り分ける。

## 復旧ステップ

| # | 作業項目 | 目的 / 成功条件 | 具体的な手順 |
| --- | --- | --- | --- |
| 1 | 環境ファイルの復旧 | `config/window-a-client.env` に必要な環境変数を設定し、systemd が読み込む | 1. `/home/tools02/tool-management-system02/config/window-a-client.env` を作成し以下を記載:<br>　- `DOCUMENT_VIEWER_URL`（例: `http://raspi-server.local:8501/viewer`）<br>　- `DOCUMENT_VIEWER_SOCKET_BASE`（例: `http://raspi-server.local:8501`）<br>　- `DOCUMENT_VIEWER_API_TOKEN`（Pi5 と同じ値）<br>　- `DATABASE_URL`（Pi5 の PostgreSQL へ接続する URL）<br>　- `API_TOKEN`（Pi5 と同じ値）<br>2. `/etc/systemd/system/toolmgmt.service.d/window-a.conf` に `EnvironmentFile=/home/tools02/tool-management-system02/config/window-a-client.env` があることを確認（無ければ作成）<br>3. `sudo systemctl daemon-reload && sudo systemctl restart toolmgmt.service`<br>4. `sudo journalctl -u toolmgmt.service -n 40 --no-pager` で DB 接続エラーが無いことを確認 |
| 2 | DOM 出力の確認 | HTML に `#rightPanel` / `#docViewerSummary` が含まれていることを確認 | `curl -s http://127.0.0.1:8501/ | grep -n 'rightPanel'`、`curl -s http://127.0.0.1:8501/ | grep -n 'docViewerSummary'` がヒットすること |
| 3 | UI 目視チェック | ブラウザ右ペインが DocumentViewer タブとサマリーを表示すること | Window A のブラウザで `Ctrl+Shift+R`（強制リロード）を実行し、右ペインが表示されることを確認 |
| 4 | 事前条件の再確認 | Pi5 の `/viewer` とトークンが正しく整合していることを確認 | `curl -s http://raspi-server.local:8501/viewer | grep docViewerSummary` で要素が取得できること、Pi4/Pi5 の `API_TOKEN` と `DOCUMENT_VIEWER_API_TOKEN` が一致していること |
| 5 | Playwright テスト実行 | `tests/e2e/window-a-live.spec.ts` の 3 ケースが PASS する | `PLAYWRIGHT_ENV_FILE=.env.test npx playwright test tests/e2e/window-a-live.spec.ts --config=tests/e2e/playwright.config.ts` を実行し、結果を記録（失敗時はログ／トレースを解析し再調整） |

## 備考

- 環境ファイルが空、または systemd が読み込めていない場合、右ペイン DOM は生成されない。  
- PostgreSQL 接続エラー（`connection refused`）が出ている場合は、`DATABASE_URL` のホスト・ポート・資格情報を見直す。Pi5 の Docker PostgreSQL を利用する場合は、Pi5 側で `docker compose ps` によりコンテナ稼働を確認すること。  
- Playwright 実行前にブラウザで UI を目視確認し、Socket.IO バッジやサマリーパネルが表示されていることを確かめるとトラブルシュートが容易になる。
