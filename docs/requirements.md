# RaspberryPiServer 要件・決定事項

この文書は RaspberryPiServer リポジトリで進めるサーバー構築に関する要件・決定事項・検討中の課題を集約する。更新時は `documentation-guidelines.md` を参照し、一次情報を重複記載しない。

## 最終ゴール

- Window A は DocumentViewer・工具管理 UI などのクライアント機能のみを担い、サーバー機能は RaspberryPiServer（ラズパイ 5）へ全面移行する。
- RaspberryPiServer は API／PostgreSQL／Socket.IO／USB 配布・バックアップを一元的に提供し、Pi Zero 2 W（ハンディリーダ）からの送信を唯一の受信点とする。
- Pi Zero 2 W はハンディリーダ専用端末として運用し、`mirrorctl`／`mirror_compare` の 14 日連続チェックをクリアした状態で本番切替を完了する。
- 上記役割分担を支える RUNBOOK・手順書・ systemd / USB 運用を整備し、旧 Window A サーバー環境を退役できる状態にする。
- Pi Zero 側のクライアント設定は `scripts/install_client_config.sh` で自動生成できるよう整備済み（OnSiteLogistics リポジトリを参照）。

## 移行タスク（旧 Window A サーバー縮退計画）

- [ ] Window A に残るクライアント機能の棚卸し（DocumentViewer、工具管理 UI、標準工数、日程、構内物流など）
- [ ] `docs/implementation-plan.md` に移行順序と依存関係を追記し、RaspberryPiServer へ移すサービスの一覧を整理
- [x] RaspberryPiServer へ DocumentViewer 用 REST API / Socket.IO を移植し、Pi Zero・DocumentViewer 間で連携確認（2025-10-26 ハンドテスト完了、`docs/test-notes/2025-10-26-socketio-verification.md` 参照）
- [ ] Window A の DocumentViewer をクライアント専用構成へ更改し、`VIEWER_API_BASE` 等で RaspberryPiServer を参照
- [ ] USB INGEST / DIST / BACKUP 運用を RaspberryPiServer 中心へ再設計し、TM-* ラベルのメディア準備と手順書更新
- [ ] `mirrorctl` / `mirror_compare` の 14 日連続チェックを完了し、Decision Log に切替判断を記録
- [ ] 旧 Window A サーバー機能の停止手順とロールバック手順を RUNBOOK へ追記し、退役の判断を実施

> 今後、旧システムの改修に着手する際は、必ず事前に必要タスクを洗い出して本ファイルや関連 `.md` に記録し、進捗が可視化された状態で1つずつ消化すること。

## 決定事項（Decision Log）

| 日付 | 区分 | 内容 |
| --- | --- | --- |
| 2025-02-?? | アーキテクチャ | **Docker Compose + PostgreSQL コンテナを継続**し、永続データは SSD（例: `/srv/rpi-server/postgres`）を bind mount して保管する。Window A の運用手順を継承し、Docker の restart/healthcheck の仕組みをそのまま活かす。 |
| 2025-02-?? | 構成 | **OnSiteLogistics 受信 API と工具管理アプリをサーバーへ集約**し、DocumentViewer は従来どおり別 Pi 上で稼働させる。DocumentViewer の右ペインは新サーバーの Socket.IO へ接続先を切り替える。 |
| 2025-02-?? | データ運用 | **USB メモリ同期を並存**させ、オフラインバックアップ兼サテライト端末へのシード媒体として維持する。USB 取り込み後は SSD 上の共有ストレージへ即時反映し、サーバー経由で各クライアントが参照する運用とする。 |
| 2025-02-?? | データ同期 | **USB メモリはサーバーのみ書き込み可とし、クライアント側は Read-Only で利用**する。サーバーに USB メモリを挿入したときだけ新旧比較（`meta.json` / タイムスタンプ）を行い、新しい側（USB メモリ or サーバー側ストレージ）で古い側を上書きする。その後サーバーが公式データとして USB を更新し、端末側は USB からの読み込み（常に USB → 端末）とサーバー API による同期のみに限定する。 |
| 2025-02-?? | USB 配布設計 | **USB メモリの役割を「サーバーへの持込み（INGEST）」「端末への配布（DIST）」で分離**する。INGEST 用は外部で編集したマスターデータや PDF をサーバーへ導入するために使用し、サーバーが新旧比較と書き込みを行う。DIST 用はサーバーが公式データをエクスポートして配布し、各端末では USB → 端末への上書きのみを許容する。ラベルおよびスクリプト上で役割を明示し、誤挿入時は処理を中断する保護を入れる。 |
| 2025-02-?? | USB 識別 | **USB メモリはファイルシステムラベルとシグネチャファイルで二重判定**する。各役割に専用ラベル（例: `TM-INGEST`）と `/.toolmaster/role` を配置し、スクリプトはラベル一致かつシグネチャ内容が想定通りのときのみ処理を実行する。不一致時はログへ警告を残し、処理を中断する。 |
| 2025-02-?? | インフラ | **SSD のマウントは `/etc/fstab` に UUID 指定で固定**し、起動時に `/srv/rpi-server`（仮称）へ自動マウントする。Docker bind mount のベースパスを揃えて運用し、再起動時の自動復旧を優先する。 |
| 2025-02-?? | 移行計画 | **OnSiteLogistics からの送信は RaspberryPiServer を唯一の受信先とし、ミラー期間は新サーバーのみで運用**する。Pi Zero・DocumentViewer・USB メモリ経路の動作を手動検証で確認し、問題発生時は `mirrorctl disable` でミラーを停止してロールバックする体制を整える。 |
| 2025-02-?? | ミラー検証 | **Pi Zero（OnSiteLogistics）、DocumentViewer、USB フローを対象にした手動検証チェックリスト**を運用し、ハンディリーダ入力→新サーバー表示→USB 配布まで一連の確認を 14 日間継続して記録する。差分や不整合が発生した場合は再検証を行い、記録をリセットする。 |
| 2025-02-?? | 運用 | **Docker Compose 起動は systemd ユニット（例: `raspi-server.service`）で管理**し、起動時に `docker compose up` を実行する。ログ収集・依存関係制御を systemd 側で統一し、再起動時の安定性を確保する。 |
| 2025-02-?? | クライアント切替 | **DocumentViewer 右ペインの Socket.IO 接続は 2 週間の並行検証後に新サーバーへ切替**し、遅延（500 ms 未満）とエラーレート（0.1% 以下）を満たすことを条件とする。設定変更のみで旧サーバーへ戻せるロールバック手順を準備する。 |
| 2025-02-?? | 監視 | **systemd + ローカルログ監視を採用**し、`Restart=on-failure` と `OnFailure` で復旧スクリプトを実行。Docker healthcheck の結果は `/var/log/raspi-server/health.log` へ記録し、`journalctl` にも出力を残す。日次点検でログを確認する運用とする。 |
| 2025-02-?? | systemd 設計 | **`raspi-server.service` に docker 依存と起動順序を集約**し、`Requires=docker.service`・`After=network-online.target docker.service` を指定する。`ExecStart=/usr/bin/docker compose -f /srv/rpi-server/docker-compose.yml up --remove-orphans`、`ExecStop=/usr/bin/docker compose -f ... down` を用い、`Restart=on-failure` と `StartLimitIntervalSec` で暴走を防ぐ。 |
| 2025-02-?? | ログ保管 | **運用ログ・バックアップログは SSD 上（例: `/srv/rpi-server/logs/`）に保存**し、USB メモリはログ書き出しには使用しない。必要な場合にのみサーバー経由で外部媒体へコピーする。 |
| 2025-02-?? | バックアップ | **SSD 上で日次スナップショット（7 世代程度）を保持し、バックアップ用 USB メモリを挿入したタイミングで最新スナップショットを自動コピー**する。バックアップ用は専用ラベル（例: `TM-BACKUP`）とし、`udev` 連携でコピー処理を起動、完了ログを `/srv/rpi-server/logs/backup.log` に記録する。USB メモリを抜き忘れても次回挿入時に最新状態へ更新されるよう設計する。USB メモリには `tar + zstd` で圧縮したアーカイブを週次 4 世代保持し、想定容量（PostgreSQL ダンプ + マスターデータ + OnSiteLogistics 連携テーブル ≒ 8 GB/世代）を踏まえて **64 GB 以上のメディア**を採用する。 |

> 日付は決定確定時に YYYY-MM-DD 形式で更新すること。

## 今後検討する項目

- USB INGEST/DIST 運用手順とスクリプト改修（ラベル識別、容量超過時の分割手順、誤挿入検知）—詳細は `docs/usb-operations.md`
- バックアップ用 USB メモリの容量設計とスナップショット整理（保持世代、圧縮方式）—詳細は `docs/usb-operations.md`
- OnSiteLogistics ミラー送信モードおよび `mirrorctl` CLI の実装—詳細は `docs/mirror-verification.md`
- 実装ロードマップに基づく各リポジトリのブランチ戦略と結合テスト計画—`docs/implementation-plan.md`

## 現在の進捗メモ（2025-10-26 時点）
- Docker Compose に Flask ベースの受信 API サービスを追加し、`/api/v1/scans` で `part_locations` へ upsert できる最小構成を実装。健康監視用 `GET /healthz` も提供。
- アプリケーションは PostgreSQL・API トークンを環境変数で切り替え可能。テーブル初期化は起動時に自動で実施。
- DocumentViewer 用 REST / Socket.IO は RaspberryPiServer で稼働中。次フェーズでは工具管理 UI の移設、Window A クライアントの接続先切替、14 日連続試運転に向けた自動テスト整備を進める。
- `/etc/default/raspi-server` のサンプル（`config/raspi-server.env.sample`）に DocumentViewer 用 `VIEWER_LOG_PATH` を追加。Window A クライアント側は DocumentViewer リポジトリの `config/docviewer.env.sample` を基に `/etc/default/docviewer` を作成し、サーバーとクライアントの設定が同期するよう整備する。
- USB INGEST 完了時に `/internal/plan-cache/refresh` を自動実行し、生産計画・標準工数 API が即時に新データを返すようにした。
- DocumentViewer 側の検証手順は `DocumentViewer/docs/test-notes/2025-10-26-docviewer-env.md` を参照し、RaspberryPiServer の RUNBOOK・Mirror 検証と合わせて更新する。
