# Inventory Manager

在庫管理・販売記録・利益分析システム。

## 概要

購入した商品の在庫管理から販売・決済までを一貫して管理する Web アプリケーション。
Mercari / Amazon のクローラーで発見した商品をインポートしたり、Mercari の持ち物一覧から同期したりできる。

## アーキテクチャ

```
┌─────────────────────────────┐
│   static/index.html          │
│   (Single-page Web UI)      │
└──────────┬──────────────────┘
           │ REST API
           ▼
┌─────────────────────────────┐
│   server.py (FastAPI)        │
│   port 8080                  │
└──────────┬──────────────────┘
           │ SQLite (ws) / PostgreSQL (本番)
           ▼
┌─────────────────────────────┐
│   db.py (データベース層)      │
│   - inventory DB             │
│   - mercari-hunter DB (PG)  │
│   - amazon-outlet DB (PG)   │
└─────────────────────────────┘
```

## データベース

SQLite（WSL 開発）/ PostgreSQL（Mac Mini 本番）`inventory` データベース。

### テーブル

| テーブル | 説明 |
|---------|------|
| `items` | 商品情報（SKU, 名前, 購入価格, 状態, プラットフォーム, 画像, URL, タグ） |
| `sale_records` | 販売記録（販売価格, 手数料, 送料, 利益, 決済状態） |
| `status_history` | 状態変更履歴（状態遷移のログ） |
| `locations` | 保管場所（名前, 説明, 有効/無効） |
| `settings` | システム設定（キーバリュー） |

### 商品ステータス

| ステータス | 説明 |
|-----------|------|
| `purchased` | 購入済み |
| `in_stock` | 在庫中 |
| `listed` | 出品中 |
| `sold` | 販売済み |
| `settled` | 決済済み |
| `discarded` | 廃棄 |
| `returned` | 返品 |

## 起動方法

### 直接起動

```bash
cd ~/workspace/inventory-manager
source venv/bin/activate
python -m uvicorn server:app --host 0.0.0.0 --port 8080
```

### 管理スクリプト

```bash
cd ~/workspace/inventory-manager

# 起動
python manage.py start

# 停止
python manage.py stop

# 再起動
python manage.py restart
```

## Web Dashboard

**アクセス:** `https://192.168.1.203/inventory/`

### タブ構成

| タブ | 説明 |
|------|------|
| 📊 看板 | 累計利益・今月利益・状態別カウント・最近の活動 |
| 📦 在庫 | 商品一覧（検索・フィルタ・ソート） / 新規登録 / 状態変更 / 販売記録 |
| 🔍 発見 | Mercari Hunter / Amazon Hunter の商品を一覧表示して在庫にインポート |
| 💰 利益 | プラットフォーム別利益 / 月別推移グラフ |
| 🔄 同期 | Mercari 持ち物一覧からの同期（ブラウザスクリプト / JSON アップロード） |

### 機能

- **在庫管理**: 商品 CRUD / 状態変更 / 販売記録 / 保管場所管理
- **利益分析**: 累計利益 / 今月利益 / 利益率 / プラットフォーム別比較 / 月別推移
- **スクレイパー連携**: Mercari Hunter / Amazon Hunter の商品を検索・フィルタして在庫にインポート
- **Mercari 持ち物同期**: ブラウザコンソールスクリプトまたは JSON ファイルアップロードで一括同期
- **保管場所**: 倉庫・部屋などの保管場所管理

## API エンドポイント

### 商品

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/api/items` | 商品一覧（検索・フィルタ・ソート・ページネーション） |
| POST | `/api/items` | 商品追加 |
| GET | `/api/items/{id}` | 商品詳細 |
| PATCH | `/api/items/{id}` | 商品更新 |
| DELETE | `/api/items/{id}` | 商品削除 |
| PATCH | `/api/items/{id}/status` | 状態変更 |

### 販売

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| POST | `/api/items/{id}/sale` | 販売記録追加 |
| GET | `/api/sales` | 販売記録一覧 |
| PATCH | `/api/sales/{id}/settle` | 決済完了 |

### 保管場所

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/api/locations` | 保管場所一覧 |
| POST | `/api/locations` | 保管場所追加 |
| PATCH | `/api/locations/{id}` | 保管場所更新 |
| DELETE | `/api/locations/{id}` | 保管場所削除 |

### ダッシュボード

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/api/dashboard/summary` | 総合サマリー（状態別カウント・累計利益・今月利益） |
| GET | `/api/dashboard/profit?platform=` | プラットフォーム別利益 |
| GET | `/api/dashboard/profit/monthly?months=` | 月別利益推移 |

### スクレイパー連携

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/api/scrapers/sources` | 接続可能なデータソース一覧 |
| GET | `/api/scrapers/mercari/items` | Mercari Hunter 商品一覧（インポート用） |
| GET | `/api/scrapers/amazon/items` | Amazon Hunter 商品一覧（インポート用） |
| POST | `/api/scrapers/mercari/items/{id}/import` | Mercari 商品インポート |
| POST | `/api/scrapers/amazon/items/{asin}/import` | Amazon 商品インポート |
| POST | `/api/scrapers/mercari/owned/sync` | Mercari 持ち物一括同期 |

### 設定

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/api/settings` | 設定取得 |
| PATCH | `/api/settings` | 設定更新 |
| GET | `/api/statuses` | 有効なステータス一覧 |

## 設定

環境変数（または `.env`）:

```env
# inventory-manager 本体 DB (PostgreSQL)
INV_DB_HOST=localhost
INV_DB_PORT=5432
INV_DB_NAME=inventory
INV_DB_USER=inventory
INV_DB_PASSWORD=<password>

# Mercari Hunter DB (スキャナ連携用)
MERCARI_DB_HOST=localhost
MERCARI_DB_PORT=5432
MERCARI_DB_NAME=mercari
MERCARI_DB_USER=mercari
MERCARI_DB_PASSWORD=<password>

# Amazon Outlet Hunter DB (スキャナ連携用)
AMAZON_DB_HOST=localhost
AMAZON_DB_PORT=5432
AMAZON_DB_NAME=amazon_outlet
AMAZON_DB_USER=amazon_outlet
AMAZON_DB_PASSWORD=<password>
```
