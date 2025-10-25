# アーキテクチャ概要

この文書は RaspberryPiServer プロジェクトにおけるシステム構成とデータフローを整理し、現行運用（移行前）とサーバー集約後（移行後）の違いを明確化する。

## 1. システム全体像

### 1.1 現行構成（移行前）

- **Window A（tool-management-system02）**
  - 工具管理 UI（Flask + Socket.IO）
  - USB メモリを活用したマスターデータ同期
  - PostgreSQL（Docker コンテナ）
  - OnSiteLogistics からの所在データ受信 API（`/api/v1/scans`）
- **Window B（DocumentViewer）**
  - PDF 要領書表示
  - USB からの PDF 取り込み
  - 右ペインで Window A の Socket.IO を参照
- **Window D（OnSiteLogistics）**
  - Pi Zero 2 W + ハンディリーダ
  - 二段スキャンで所在データを HTTP POST（先は Window A）
- **共有 USB メモリ**
  - `TOOLMASTER` ラベルでマスターファイルと PDF を持ち運び
  - 挿入した端末が新旧比較し、最新データで上書きする

### 1.2 移行後構成（サーバー集約）

- **Window E（本サーバー：RaspberryPiServer + SSD）**
  - 工具管理アプリ + OnSiteLogistics 受信 API を集約（Docker Compose）
  - PostgreSQL コンテナ＋SSD 永続化
  - Socket.IO / REST API を DocumentViewer や他端末へ提供
  - USB メモリ運用のハブ（INGEST / DIST / BACKUP）
  - 監視・ログ・バックアップの統合
- **Window B（DocumentViewer）**
  - Socket.IO 接続先をサーバーへ切り替え
  - PDF 取り込みはサーバーからの DIST USB を利用
- **Window D（OnSiteLogistics）**
  - ミラー期間中は旧・新サーバーへ二重送信（HTTP POST）
  - 本切替後は新サーバーのみへ送信
- **その他クライアント**
  - 工具管理 UI などはサーバー提供の API を参照

## 2. データフロー

```
[OnSiteLogistics] --HTTP POST--> [RaspberryPiServer (API)]
                                  |
                                  v
                         [PostgreSQL (Docker)]
                                  |
                                  v
                     [Socket.IO / REST on RaspberryPiServer]
                                  |
    +-----------------------------+-----------------------------+
    |                                                             |
    v                                                             v
[DocumentViewer] (右ペイン)                       [工具管理 UI / 他クライアント]
```

USB メモリの流れは以下のとおり。

```
                 ┌──────────────┐
                 │  サーバー    │
                 │ (INGEST端子) │
                 └─────┬────────┘
                       │
           TO̲OLMASTER-INGEST（新旧比較・取り込み）
                       │
                       ▼
                 ┌──────────────┐
                 │ サーバーデータ│
                 └─────┬────────┘
                       │
           TO̲OLMASTER-DIST（エクスポート）
                       │
        ┌──────────────┴──────────────┐
        │                              │
        ▼                              ▼
[DocumentViewer]                [工具管理端末]
        │                              │
        └── USB → 端末へ一方向コピー ──┘

[バックアップ] TO̲OLMASTER-BACKUP（圧縮アーカイブ）
```

## 3. ネットワークとポート

- RaspberryPiServer（Window E）
  - Flask + Socket.IO: `:8501`
  - PostgreSQL: `127.0.0.1:5432`（Docker 内部）
  - 管理用 SSH: `:22`（LAN 内運用前提）
- OnSiteLogistics（Window D）
  - Wi-Fi（2.4 GHz）でサーバーへ HTTP POST（`/api/v1/scans`）
- DocumentViewer（Window B）
  - Socket.IO / REST を `http://<server>:8501` から取得
  - PDF データは DIST USB で配布されたローカルファイルを使用

## 4. 移行ステップ概要

1. RaspberryPiServer（Window E）で Docker Compose 環境と SSD マウントを整備
2. Window A のアプリケーションコードと設定を段階的に移植（API, Socket.IO, USB 周辺）
3. OnSiteLogistics（Window D）から新サーバーへのミラー送信を開始し、差分ログを検証（14 日）
4. DocumentViewer（Window B）の Socket.IO 接続先をサーバーへ切り替え（ロールバック手順を準備）
5. 公式 USB メモリ運用（INGEST / DIST / BACKUP）をサーバー中心へ移行
6. 旧環境（Window A）の役割を縮退 or 退役し、最終的に RaspberryPiServer を単独運用基盤とする

## 5. 残タスク・検討事項

- Window A/B/D のコード移植・設定変更手順の詳細化
- ミラー運用スクリプトと管理コマンドの実装
- 監視ログおよびバックアップ・スナップショットの自動化検証
- RUNBOOK およびトラブルシュートガイドの整備

本書は設計のたたき台として用い、進捗に合わせて更新すること。
