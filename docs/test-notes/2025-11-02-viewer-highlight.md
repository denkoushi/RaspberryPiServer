# 2025-11-02 DocumentViewer 連携ハイライト確認

## 前提
- Pi4 Window A クライアント（branch: `feature/client-socket-cutover`）
- RaspberryPiServer（branch: `feature/server-app`）で `testpart.pdf` 配信済み
- DocumentViewer 連携のステータスマシン／所在一覧ハイライト API を適用済み (`npm test -- --run` 実行済み)

## 手順
1. Window A で最新コードを取得し再起動
   ```bash
   cd ~/tool-management-system02
   git pull origin feature/client-socket-cutover
   npm install
   sudo systemctl daemon-reload
   sudo systemctl restart toolmgmt.service
   ```
2. 右ペインのタブを切り替え `testpart` を検索。DocumentViewer が PDF を表示できることを確認。
3. `dv-barcode` イベントを送出（Pi5 `/viewer` UI から検索、もしくは Pi Zero のスキャン）し、所在一覧タブが自動ハイライトされることを確認。
4. ハイライト済みの行が `is-flash` クラスで点灯し、他の行は解除されることを確認。行が存在しない場合は手動更新後にハイライトされることも確認。

## 結果
- DocumentViewer 上で `testpart` を検索すると PDF が表示された。
- `dv-barcode` イベント受信後、自動的に所在一覧タブが点灯し該当行がハイライトされた。
- 存在しないオーダーの場合、次回取得時にハイライトされる挙動を確認した。

## 備考
- 本確認により `docs/requirements.md` の「構内物流・所在一覧 UI の整合 (DocumentViewer 連携イベント再テスト)」の検証を完了。
- Playwright での自動化は今後の E2E 整備タスクで実施予定。
