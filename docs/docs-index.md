# ドキュメント索引

RaspberryPiServer リポジトリのドキュメント配置と役割を一覧化します。追加・削除・大幅改訂を行う際は本索引と `docs/documentation-guidelines.md` の整合を必ず確認してください。

| カテゴリ | ファイル | 主な内容 | 更新トリガ |
| --- | --- | --- | --- |
| ガバナンス | `docs/AGENTS.md` | 作業指針、ウィンドウ構成、コミュニケーションルール | 運用方針・ブランチ戦略が変わったとき |
| ガバナンス | `docs/documentation-guidelines.md` | 文書分類・更新ルール | 文書種別追加、棚卸し手順の見直し |
| 概要 | `README.md` | プロジェクト概要、主要ドキュメントへの入口 | サービス構成やセットアップ手順が変わったとき |
| 概要 | `CHANGELOG.md` | 適用済み変更履歴 | リリース・本番反映時 |
| 運用 | `RUNBOOK.md` | サービス再起動、デプロイ、トラブルシュート | 新しい運用手順が確定したとき |
| 要件/計画 | `docs/requirements.md` | 要件・決定事項・未完タスク | 合意事項や優先度が変わったとき |
| 要件/計画 | `docs/implementation-plan.md` | 機能ロードマップ、マイルストーン | 計画更新、完了報告時 |
| 要件/計画 | `docs/documentviewer-migration.md` | DocumentViewer サーバー移行計画と進捗 | 移行ステータスの更新 |
| 要件/計画 | `docs/api-plan.md` | REST / Socket.IO API の仕様整理 | エンドポイント変更・追加時 |
| Mirror 運用 | `docs/mirror-verification.md` | 14 日検証手順、日次チェック項目 | 検証手順の更新 |
| Mirror 運用 | `docs/mirrorctl-spec.md` | `mirrorctl`/`mirror_compare` の CLI 仕様 | CLI 仕様変更、実装アップデート時 |
| 運用補助 | `docs/usb-operations.md` | USB メディア運用手順 | 運用フロー変更時 |
| テンプレート | `docs/templates/` | テストログ・チェックシートのテンプレート | テンプレート追加・改訂時 |
| テスト記録 | `docs/test-notes/YYYY-MM-DD-*.md` | 実機検証ログ・証跡 | 各検証実施後 |
| アーカイブ | `docs/archive/2025-10-26-client-cutover.md` | Window A 切替当時の作業メモ | 参照専用（更新しない） |

---

**棚卸しルール**
- 月次またはリリース前に `rg --files -g '*.md'` を実行し、索引と実ファイルの差異がないか確認する。  
- 役割が変わった文書は本索引と `docs/AGENTS.md` のリンク集を同時に更新する。  
- アーカイブへ移動した文書は「参照専用」の旨を明記し、現行手順とは区別する。
