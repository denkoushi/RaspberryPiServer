# 2025-10-25 Docker Compose/PostgreSQL 検証ログ

## 概要
- 目的: `docker-compose.yml` ベースの PostgreSQL サービスが起動し、永続化ディレクトリと既存バックアップスクリプト（`tool-snapshot.sh` / `tool-backup-export.sh`）と連携できるかを確認する。
- ブランチ: `feature/server-ops-docs`
- 対象環境: 開発用 macOS（RaspberryPiServer リポジトリ）※ Docker Desktop 未起動のため本番 Pi では未検証。

## 手順と結果
| 手順 | コマンド | 結果 |
| --- | --- | --- |
| `.env` 作成 | ```bash<br>cp .env.example .env``` | `.env` をリポジトリ直下に作成。差分なし。 |
| コンテナ起動 | ```bash<br>docker compose up -d``` | **失敗**: Docker デーモンへ接続できずエラー。 |

### エラーログ
```bash
time="2025-10-25T15:55:59+09:00" level=warning msg="/Users/tsudatakashi/RaspberryPiServer/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
unable to get image 'postgres:15-alpine': Cannot connect to the Docker daemon at unix:///Users/tsudatakashi/.docker/run/docker.sock. Is the docker daemon running?
```

## 考察
- 開発マシン側で Docker デーモンが起動していないため、Compose による PostgreSQL 起動を確認できていない。
- Raspberry Pi 本体では Docker/Compose を事前導入済みのため、Pi 上で再現すれば検証を継続可能。

## 次に行うべき作業（Raspberry Pi 上）
1. Docker デーモンの稼働確認: `sudo systemctl status docker` で `active (running)` を確認。停止時は `sudo systemctl start docker`。
2. `.env` の配置見直し: `/srv/rpi-server`（想定配置先）へリポジトリ一式を配置し `.env` を最新化。
3. コンテナ起動: `sudo docker compose up -d` → `sudo docker compose ps` の順でヘルスチェック列が `healthy` になることを確認。
4. データ永続化確認: `sudo docker volume inspect postgres-data` で `Mountpoint` を確認し、`/var/lib/docker/volumes/postgres-data/_data` が生成されているかをチェック。
5. `tool-snapshot.sh` との連携: `sudo PG_URI="postgresql://app:app_password@localhost:5432/appdb" tool-snapshot.sh --dest /srv/rpi-server/snapshots` を実行し、`pg_dump` が成功することを確認（必要に応じて環境変数で `PATH` に `/usr/bin` などを追加）。
6. `tool-backup-export.sh` のリハーサル: `--dry-run` 付きで実行し、最新スナップショットを検出できることを確認。完全実行はバックアップ USB (`TM-BACKUP`) 挿入後に行う。
7. バックアップディレクトリの点検: `/srv/rpi-server/snapshots/*/db/pg_dump.sql` が生成され、USB 側に `*_full.tar.zst` が作成されることを確認。

## フォローアップ
- 上記手順を Pi 上で実施した結果を追記し、成功時には RUNBOOK の Docker/PostgreSQL セクションへ詳細手順を反映させる。
- テスト完了後、本ログに成功可否と確認日時を追記予定。
