# Mirror Daily Check Template

| 日付 | 担当者 | Pi Zero スキャン | API/DB 確認 | DocumentViewer | DIST USB | 備考 |
| --- | --- | --- | --- | --- | --- | --- |
| YYYY-MM-DD | 名前 | ☐ | ☐ | ☐ | ☐ | |

## 実施メモ

- **Pi Zero スキャン**: `mirrorctl status` 結果とスキャン可否を記入（成功/失敗、端末名、時刻）。
- **API/DB 確認**: `mirror_requests.log`・`mirror_status.log`・`part_locations` クエリの結果を要約。
- **DocumentViewer**: 所在一覧の更新状況やスクリーンショット有無、エラー時の console ログなどを記載。
- **DIST USB**: 作成・配布手順を実施した際のログ・完了時刻・端末での反映状況を記録。
- **備考**: 上記で異常があった場合は詳細と暫定対処を記載。NG があれば翌日のカウントをリセットし、別途詳細ログを保存する。

> 14 日連続で全項目がチェック済みになったら、Decision Log へ記録し本番切替判定の資料とする。
