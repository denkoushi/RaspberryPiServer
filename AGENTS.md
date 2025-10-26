# AGENTS.md

このリポジトリでエージェント／タスクを実行するときの前提と手順をまとめた指針です。新しいスレッドや自動化フローを開始する際は、最初にこのファイルを確認してください。

## 1. プロジェクト構成

### 1.1 ウィンドウとパス
- **ウィンドウA**: `/Users/tsudatakashi/tool-management-system02`
- **ウィンドウB**: `/Users/tsudatakashi/DocumentViewer`
- **ウィンドウC**: `/Users/tsudatakashi/RaspberryPizero2W_withDropbox`
- **ウィンドウD**: `/Users/tsudatakashi/OnSiteLogistics`
- **ウィンドウE**: `/Users/tsudatakashi/RaspberryPiServer`（本プロジェクト）

各ウィンドウのコンテキストは独立して扱います。別ウィンドウの情報を参照する場合は、ユーザーへ確認を行い了承を得てから共有してください。

### 1.2 初期タスク
- この `RaspberryPiServer` リポジトリの目的と現状を把握する。
- ドキュメント作成は `documentation-guidelines.md` のルールに従う。
- 追加で作成する設計書・手順書の置き場は `docs/` ディレクトリを基本とし、作成時に必ずこのファイルへリンクを追記する。

## 2. コミュニケーション指針
- 使用言語は日本語を基本とし、必要に応じて英語を補足する。
- コマンドやコードは必ずフェンス付きコードブロックで提示する。
- ラズベリーパイでの操作提案時は、以下の4点をセットで共有すること:
  1. 実行コマンド
  2. 想定される出力または状態変化
  3. エラー時の診断手順や関連ログの確認方法
  4. 必要なら再起動・ロールバック手順

## 3. 開発プロセス
- ブランチ戦略:
  - 軽微な修正は `main` ブランチへ直接コミット可能。
  - 影響範囲が広い変更、デプロイ前検証が必要な変更はブランチを切り、ラズベリーパイ上で検証してから `main` へ統合する。
- 実装前に複数案が考えられる場合は、比較表か箇条書きで案を提示し、推奨案と理由を明確にする。
- 不明点や前提条件に疑義がある場合は作業着手前にユーザーへ確認し、確認結果を関連ドキュメントへ記録する。
- 最終ゴールに向けて主体的にタスクを選定し、実行前に選択肢・理由・推奨を提示する。必要な許可がある場合はその旨と背景を明示する。

## 4. ドキュメントとコンテキスト
- ドキュメント整備は `documentation-guidelines.md` を必ず参照する。
- 機能追加・運用手順・構築手順・トラブルシュートは、必要になった時点で適切なドキュメント（README、RUNBOOK、`docs/` 配下など）へ整理する。
- 新規に作成したドキュメントは、必要に応じてこのファイルのリンク集に追記する。

## 5. 作業前チェックリスト
- `git status -sb` で現在のブランチとローカル変更を確認する。
- 参照中のウィンドウ／リポジトリが依頼内容と一致しているか再確認する。
- 更新予定のドキュメントやコードと整合する既存情報（README、RUNBOOK、`docs/requirements.md` 等）があるかを確認する。
- 依存関係や環境変数が必要な場合は、手元の `.env` などを更新した上で共有可否を判断する。

## 6. 障害発生時の対応
- エラーが発生した場合は原因、影響範囲、暫定対処、恒久対策の順に整理する。
- 自動ロールバックやサービス再起動が必要な場合は、事前にユーザーへ方針を確認する。
- ログや診断コマンド結果を提示する際は、機微情報が含まれていないか確認してから共有する。

## 7. 提案と合意形成
- 重要な決定は候補案・メリット・デメリットを明確に提示し、ユーザーと合意したら `docs/requirements.md`（未作成の場合は新規作成）へ記録する。
- 合意事項を実装に反映させたタイミングで `CHANGELOG.md` などへ履歴を残す。

## 8. リンク集
- ドキュメント運用ガイドライン: `documentation-guidelines.md`
- 決定事項・要件管理: `docs/requirements.md`
- アーキテクチャ概要: `docs/architecture.md`
- USB メモリ運用手順: `docs/usb-operations.md`
- ミラー検証設計: `docs/mirror-verification.md`
- 実装ロードマップ: `docs/implementation-plan.md`
- テストログ: `docs/test-notes/2025-10-25-usb-loopback.md`
- テストログ（物理 USB）: `docs/test-notes/2025-10-25-physical-usb.md`
- テストログ（PostgreSQL Compose）: `docs/test-notes/2025-10-25-postgres-compose.md`
- テスト計画（mirrorctl/mirror_compare）: `docs/test-notes/2025-10-25-mirrorctl-integration-plan.md`
- テストログ（Docker Compose app サービス）: `docs/test-notes/2025-10-26-app-compose.md`
- テストログ（Socket.IO 検証）: `docs/test-notes/2025-10-26-socketio-verification.md`
- DocumentViewer サーバー移行計画: `docs/documentviewer-migration.md`
- 運用手順: `RUNBOOK.md`
- 障害対応テンプレート: `docs/incident-response.md`（必要に応じて新規作成）

この指針を定期的に見直し、プロジェクトの進捗に合わせて更新してください。
