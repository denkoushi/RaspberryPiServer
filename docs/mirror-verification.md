# OnSiteLogistics ミラー検証設計

この文書は、移行期間中に RaspberryPiServer を単独の受信先として運用しつつ、Pi Zero（OnSiteLogistics）・DocumentViewer・USB 配布フローが期待どおり動作することを手動で検証するための手順をまとめる。`docs/requirements.md` に定義した「14 日間の連続確認」を達成するためのチェック項目と記録方法を規定する。

## 1. 検証のゴール

- Pi Zero から送信した所在データが RaspberryPiServer で正しく受信・保存される。
- 受信データが工具管理 UI や DocumentViewer で表示され、USB 配布フローにも反映される。
- これらを 1 日 1 セット、14 日連続で実施し、チェックリストに記録できたら本切替条件を満たす。
- 問題発生時は `mirrorctl disable` でミラーを停止し、ログと記録をもとに再検証する。

## 2. 検証スコープ

| 区分 | 検証対象 | 主な確認内容 |
| --- | --- | --- |
| Pi Zero（OnSiteLogistics） | ハンディリーダ + Pi Zero 2 W | `mirror_mode=true` で送信が成功し、ローカルキューに残件がないこと。 |
| RaspberryPiServer | API / PostgreSQL / mirror_compare | 受信 API が 200 を返し、`part_locations` に最新データが記録される。`mirror_status.log` に OK が出力される。 |
| DocumentViewer | Socket.IO / PDF 表示 | 工具一覧画面に最新所在が反映される。必要に応じて PDF 側で変化を確認。 |
| USB フロー | DIST/INGEST の一連操作 | サーバーから DIST USB をエクスポートし、端末で読み込むと最新データが反映される。 |

## 3. 日次チェックリスト

以下の手順を 1 セットとして実施し、チェックリスト（テンプレートは `docs/test-notes/` 配下に追加予定）に記録する。

1. **Pi Zero 操作**  
   - `mirrorctl status` で `mirror_mode=true`、タイマーが `active/enabled` であることを確認。  
   - ハンディリーダでサンプルの部品票 + 棚を読み取る。成功時の確認音・表示を記録。
2. **サーバー確認**  
   - `sudo tail -n 3 /srv/rpi-server/logs/mirror_requests.log` で最新エントリを確認。  
   - `PGPASSWORD=app psql -h localhost -U app -d sensordb -c "SELECT order_code, location_code, updated_at FROM part_locations ORDER BY updated_at DESC LIMIT 1;"` で更新を確認。  
   - `sudo /usr/local/bin/mirror_compare.py --strict` を実行し、`mirror_status.log` に `status: OK` が追記されることを確認（エラー時は専用欄に記録）。
3. **DocumentViewer**  
   - UI の所在一覧が更新されるか、または該当オーダーが表示されるかを確認。  
   - 必要に応じて Screenshot またはログに証跡を残す。
4. **USB フロー**  
   - `sudo mirrorctl rotate`（必要に応じて）でログを整備した後、`tool-dist-sync.sh` など既存手順で DIST USB を作成。  
   - 対象端末で USB を読み込み、最新データが反映されることを確認。
5. **記録**  
   - 日次チェックシートに結果（○/×）、メモ、対応者名、時刻を記入。  
   - 異常時は `mirror_diff.log` / `mirror_status.log` に残った内容を添付し、再実施前に原因究明を行う。

## 4. mirror_compare.py の位置付け

`mirror_compare.py` は旧サーバー比較ではなく、RaspberryPiServer 内での健全性チェックに用途を変更する。

- 比較対象: `primary_db_uri` と `mirror_db_uri` はどちらも RaspberryPiServer の `sensordb` を指す。  
- 目的: DB 接続・ログ出力・OK カウンタの更新が正常に行われるかを確認する。  
- `--strict` でエラーが出た場合は、接続情報やテーブル状態を調査し、日次チェックリストを失敗として扱う。  
- 手動検証の補助として、異常時は `mirror_status.log` と `mirror_diff.log` の内容をチェックリストに転記する。

## 5. mirrorctl CLI の運用方針

- `mirrorctl enable`: Pi Zero 設定を `mirror_mode=true` にし、日次検証を開始。実行時刻と担当者を記録する。  
- `mirrorctl disable`: 検証を中断する場合に実施し、`mirror_mode=false` に戻す。停止理由を記録。  
- `mirrorctl status`: 日次検証の冒頭で必ず実行し、タイマー状態・OK カウンタをチェックリストに転記。  
- `mirrorctl rotate`: ログが肥大化した場合や週次の整理タイミングで実行し、ログ保管状況を記録する。

## 6. ロールバックと再検証

異常が発生した場合は以下の順序で対応する。

1. `sudo mirrorctl disable` で Pi Zero のミラー送信を停止。  
2. `mirror_requests.log` / `mirror_status.log` / `mirror_diff.log` を保存し、異常内容を記録。  
3. RaspberryPiServer 側の API / DB / network を切り分けし、必要に応じて Pi Zero のローカルキューを確認。  
4. 原因解消後、`mirrorctl enable` → 日次チェック（再実施）を行い、連続日数カウントをリセットする。  
5. 再検証結果を `docs/test-notes/` 配下に追記し、RUNBOOK のトラブルシュートに反映する。

## 7. 記録と判定

- 日次チェックの結果は `docs/test-notes/` に日付ごとのログファイル（例: `2025-11-01-mirror-check.md`）として保存する。  
- 14 日連続で「全項目 OK」を達成したら、Decision Log に実施期間と判定者を追記し、RUNBOOK に切替作業のチェックリストを掲載する。  
- 途中で NG が発生した場合はカウントをリセットし、原因と再発防止策を次回検証の冒頭で共有する。

## 8. 今後の拡張案

- 日次チェックシートの電子フォーム化（例: Google Form や Notion）で記録の一元化を図る。  
- `mirror_compare.py` を拡張し、API レスポンスやログサイズの監視など手動検証の補助情報を収集する。  
- DocumentViewer への自動スクリーンショット取得スクリプトを追加し、視覚的な証跡を残す。

本手順に従い、手動検証を継続することで旧サーバー比較を行わずに移行可否を判断できる。必要に応じてチェックリストやログフォーマットを `docs/test-notes/` に追加し、運用に合わせて更新すること。
