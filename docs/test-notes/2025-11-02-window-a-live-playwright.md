# 2025-11-02 Window A ライブ Playwright テスト

## 概要
- Raspberry Pi 5 (raspi-server-3.local) と Raspberry Pi 4 (Window A) を実機構成で起動した状態で、Playwright のライブシナリオ `tests/e2e/window-a-live.spec.ts` を Pi4 上で実行。
- 目的: スキャンイベント→所在一覧→要領書サマリー更新→構内物流タブ更新の流れが自動検証可能か確認。
- 結果: 2 ケースとも成功。所在サマリーは `testpart` の最新スキャンで位置 `RACK-A1`、デバイス `playwright-device-<timestamp>` を表示し、構内物流タブに新規ジョブが反映された。

## 実行環境
- Window A (Pi4): `tool-management-system02` リポジトリ `feature/client-socket-cutover`
- Raspberry Pi 5: `RaspberryPiServer` リポジトリ `feature/server-app`
- `.env.test`:
  ```
  TOOLMGMT_BASE_URL=http://127.0.0.1:8501
  TOOLMGMT_API_TOKEN=raspi-token-20251027
  RASPI_SERVER_BASE=http://raspi-server-3.local:8501
  RASPI_SERVER_API_TOKEN=raspi-token-20251027
  PLAYWRIGHT_HEADLESS=1
  ```

## 実行コマンド
```bash
cd ~/tool-management-system02
PLAYWRIGHT_ENV_FILE=.env.test npx playwright test tests/e2e/window-a-live.spec.ts --config=tests/e2e/playwright.config.ts
```

## Playwright 実行ログ
- scan event → viewer summary: `passed`
- logistics job update → logistics tab: `passed`
- 動画 / trace は `~/tool-management-system02/test-results/` 配下に保存（検証時点）

## 補足・観察事項
- DocumentViewer サマリーの `data-state` は PDF 連携完了前は `empty` のままなので、Playwright では位置・デバイス・部品番号のテキストを検証する方式に変更。
- `part_code` を固定値 `testpart` に指定することで、RaspberryPiServer 側に常備された PDF (`testpart.pdf`) を確実に読み込めるようにした。
- 構内物流タブのシナリオでは API へ事前挿入したジョブが即時反映され、バッジ件数・テーブル内容も更新されたことを確認。
- 今後は `.env.test` を適宜更新して各環境で再現できるようにし、CI などでライブシナリオを任意タイミングで実行可能。

