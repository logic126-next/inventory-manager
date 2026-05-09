# Inventory Manager — Design Document

> 転売用在庫管理システム | Reselling Inventory Management System  
> Tech stack: Python / SQLite / FastAPI + Uvicorn / Pure HTML+CSS+JS  
> Deploy: WSL (Ubuntu) at `~/workspace/inventory-manager`

---

## 1. 系统总览 (System Overview)

```
┌─────────────────────────────────────────────────────────────┐
│                    inventory-manager                         │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌────────────────────────┐  │
│  │  Frontend │   │  FastAPI  │   │    SQLite DB           │  │
│  │ (HTML/    │   │  REST API │   │    inventory.db        │  │
│  │  CSS/JS)  │   │  + Uvicorn│   │                        │  │
│  └─────┬─────┘   └─────┬─────┘   └────────────────────────┘  │
│        │               │               ▲                      │
│        └───────┬───────┘               │                      │
│                │                       │  一键入库             │
│                ▼                       │  (one-click import)  │
│        ┌───────────────┐              │                      │
│        │  External DBs  │──────────────┘                      │
│        │  mercari.db    │  ◄── 读取发现的好货                   │
│        │  amazon_outlet │  ◄── 读取发现的好货                   │
│        │  .db           │                                      │
│        └───────────────┘                                      │
└─────────────────────────────────────────────────────────────┘
```

核心流程：  
爬虫发现好货 → 浏览/筛选 → 一键入库 → 购入确认 → 在库管理 → 上架出售 → 售出记录 → 利润结算

---

## 2. 数据库设计 (Database Schema)

### 2.1 表结构总览

| 表名 | 说明 |
|------|------|
| `items` | 商品主表 — 核心库存记录 |
| `status_history` | 状态变更流水 — 全流程审计追踪 |
| `sale_records` | 销售记录 — 售价、平台、手续费、利润 |
| `locations` | 仓库位置 — 物理存放位置管理 |
| `import_sources` | 外部导入源 — 记录从哪个爬虫导入 |
| `settings` | 系统设置 — 平台费率、汇率等 |

### 2.2 详细建表语句

```sql
-- ============================================================
-- items: 商品主表
-- ============================================================
CREATE TABLE items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT UNIQUE,                       -- 内部SKU码，自动生成 INV-YYYYMMDD-NNNN
    name            TEXT NOT NULL,                     -- 商品名
    description     TEXT,                              -- 备注/描述
    source_platform TEXT NOT NULL,                     -- 购入来源: mercari, amazon_outlet, other
    source_item_id  TEXT,                              -- 外部商品ID (mercari_id / asin)
    purchase_price  INTEGER NOT NULL,                  -- 购入价 (日元)
    purchase_date   TIMESTAMP NOT NULL,                -- 购入日期
    image_url       TEXT,                              -- 商品图片URL
    source_url      TEXT,                              -- 商品链接 (原始来源)
    location_id     INTEGER,                           -- 存放位置 FK -> locations.id
    status          TEXT NOT NULL DEFAULT 'purchased', -- 当前状态
    tags            TEXT DEFAULT '[]',                 -- 标签 JSON: ["3C","限定"]
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_items_status ON items(status);
CREATE INDEX idx_items_source_platform ON items(source_platform);
CREATE INDEX idx_items_name ON items(name);
CREATE INDEX idx_items_sku ON items(sku);

-- ============================================================
-- status_history: 状态变更流水
-- ============================================================
CREATE TABLE status_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL,
    from_status     TEXT,                              -- 变更前状态 (首次为 NULL)
    to_status       TEXT NOT NULL,                     -- 变更后状态
    note            TEXT,                              -- 变更备注
    changed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(id)
);

CREATE INDEX idx_status_history_item ON status_history(item_id);

-- ============================================================
-- sale_records: 销售记录
-- ============================================================
CREATE TABLE sale_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL,
    sale_price      INTEGER NOT NULL,                  -- 售价 (日元)
    sale_platform   TEXT NOT NULL,                     -- 出售平台: mercari, amazon, other
    sale_url        TEXT,                              -- 上架/售出链接
    platform_fee    INTEGER NOT NULL DEFAULT 0,        -- 平台手续费 (日元)
    shipping_cost   INTEGER DEFAULT 0,                 -- 运费成本 (日元)
    other_cost      INTEGER DEFAULT 0,                 -- 其他费用 (日元)
    net_profit      INTEGER NOT NULL,                  -- 净利润 = sale_price - platform_fee - purchase_price - shipping_cost - other_cost
    sale_date       TIMESTAMP NOT NULL,                -- 售出日期
    settled         BOOLEAN DEFAULT FALSE,             -- 是否已结算 (钱已到手)
    settled_at      TIMESTAMP,                         -- 结算时间
    note            TEXT,                              -- 备注
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(id)
);

CREATE INDEX idx_sale_records_item ON sale_records(item_id);
CREATE INDEX idx_sale_records_platform ON sale_records(sale_platform);
CREATE INDEX idx_sale_records_settled ON sale_records(settled);

-- ============================================================
-- locations: 仓库位置
-- ============================================================
CREATE TABLE locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,                     -- 位置名: "A棚-3排", "地下室-纸箱2"
    description     TEXT,                              -- 描述
    active          BOOLEAN DEFAULT TRUE,              -- 是否在用
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- import_sources: 外部爬虫导入源配置
-- ============================================================
CREATE TABLE import_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,              -- 源名: mercari-hunter, amazon-outlet-hunter
    db_path         TEXT NOT NULL,                     -- SQLite 路径
    platform        TEXT NOT NULL,                     -- 对应平台: mercari, amazon_outlet
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- settings: 系统设置
-- ============================================================
CREATE TABLE settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.3 状态机 (Status Flow)

```
purchased  ──→  in_stock  ──→  listed  ──→  sold  ──→  settled
(已购入)         (在库)        (上架)       (已售)      (已结算)

可选:
  purchased ──→ discarded    (丢弃/报废)
  listed    ──→ in_stock     (下架)
  sold      ──→ returned     (退货) ──→ in_stock
```

| 状态码 | 中文 | 日文 | 说明 |
|--------|------|------|------|
| `purchased` | 已购入 | 購入済み | 已确认购入，待入库 |
| `in_stock` | 在库 | 在庫 | 已入库，存放在某位置 |
| `listed` | 上架 | 出品済み | 已在平台挂牌出售 |
| `sold` | 已售 | 販売済み | 已成交，待结算 |
| `settled` | 已结算 | 決済済み | 钱已到手，完成 |
| `discarded` | 报废 | 廃棄 | 无法出售，已丢弃 |
| `returned` | 退货 | 返品 | 买家退货 |

### 2.4 手续费费率 (Platform Fee Rates)

```sql
-- 预置默认值
INSERT INTO settings (key, value) VALUES
    ('fee_rate_mercari', '0.10'),           -- Mercari: 10%
    ('fee_rate_amazon', '0.15'),             -- Amazon: ~15%
    ('fee_rate_other', '0.10'),              -- 其他: 默认10%
    ('currency', 'JPY'),                     -- 货币: 日元
    ('timezone', 'Asia/Tokyo');              -- 时区: JST
```

---

## 3. API 端点设计 (API Endpoints)

### 3.1 商品管理 (Items)

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/items` | 商品列表 (支持分页、状态过滤、平台过滤、标签搜索) |
| `GET` | `/api/items/{id}` | 商品详情 |
| `POST` | `/api/items` | 新增商品 (手动入库) |
| `PATCH` | `/api/items/{id}` | 更新商品信息 |
| `DELETE` | `/api/items/{id}` | 删除商品 |
| `POST` | `/api/items/{id}/status` | 状态变更 (触发 status_history 记录) |
| `POST` | `/api/items/{id}/sale` | 记录销售 (创建 sale_record，自动更新状态为 sold) |

**查询参数 (GET /api/items):**
```
?status=in_stock&platform=mercari&tag=3C&search=MacBook&page=1&per_page=50
```

**POST /api/items 请求体:**
```json
{
    "name": "MacBook Air M2 256GB",
    "source_platform": "mercari",
    "source_item_id": "c/123456789",
    "purchase_price": 55000,
    "purchase_date": "2026-05-09",
    "image_url": "https://...",
    "source_url": "https://mercari.jp/items/...",
    "location_id": 1,
    "tags": ["Mac", "3C", "限定"],
    "description": "成色很好，箱说全"
}
```

### 3.2 销售记录 (Sales)

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/sales` | 销售记录列表 |
| `GET` | `/api/sales/{id}` | 销售详情 |
| `PATCH` | `/api/sales/{id}` | 更新销售记录 (如修改运费) |
| `POST` | `/api/sales/{id}/settle` | 标记为已结算 |

**POST /api/items/{id}/sale 请求体:**
```json
{
    "sale_price": 85000,
    "sale_platform": "mercari",
    "sale_url": "https://mercari.jp/items/...",
    "platform_fee": 8500,          -- 可前端计算后传入，后端也做校验
    "shipping_cost": 650,
    "other_cost": 0,
    "sale_date": "2026-05-15"
}
```

### 3.3 仓库位置 (Locations)

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/locations` | 位置列表 |
| `POST` | `/api/locations` | 新增位置 |
| `PATCH` | `/api/locations/{id}` | 更新位置 |
| `DELETE` | `/api/locations/{id}` | 删除位置 |

### 3.4 利润统计 (Dashboard / Analytics)

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/dashboard/summary` | 总览: 总商品数、各状态数、总利润、本月利润 |
| `GET` | `/api/dashboard/profit` | 利润报表: 按平台/时间/商品分类 |
| `GET` | `/api/dashboard/profit/monthly` | 月度利润趋势 |
| `GET` | `/api/dashboard/profit/platform` | 按出售平台分组的利润 |
| `GET` | `/api/dashboard/inventory/value` | 库存总价值 (购入价总和) |

**GET /api/dashboard/summary 响应:**
```json
{
    "total_items": 156,
    "status_counts": {
        "purchased": 5,
        "in_stock": 42,
        "listed": 28,
        "sold": 15,
        "settled": 64,
        "discarded": 2
    },
    "total_cost": 4250000,
    "total_revenue": 6800000,
    "total_profit": 1800000,
    "profit_margin": 0.42,
    "month_cost": 350000,
    "month_revenue": 580000,
    "month_profit": 180000,
    "pending_settlement": 450000,
    "inventory_value": 1250000
}
```

### 3.5 爬虫联动 (Import from Scrapers)

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/imports/sources` | 可用导入源列表 |
| `GET` | `/api/imports/candidates` | 从爬虫 DB 拉取可入库的商品候选 |
| `POST` | `/api/imports/import` | 一键入库 (从候选商品创建 item) |
| `POST` | `/api/imports/sync-sources` | 重新扫描爬虫 DB 路径 |

**GET /api/imports/candidates 查询参数:**
```
?source=mercari-hunter&is_flagged=true&limit=50
?source=amazon-outlet-hunter&keyword=SSD&min_discount=30
```

**GET /api/imports/candidates 响应:**
```json
{
    "source": "mercari-hunter",
    "platform": "mercari",
    "count": 23,
    "items": [
        {
            "external_id": "c/987654321",
            "name": "Nintendo Switch OLED ホワイト",
            "price": 18500,
            "url": "https://mercari.jp/items/c/987654321",
            "image_url": "https://...",
            "market_median": 25000,
            "potential_profit": 6500,
            "ratio": 0.74,
            "flagged": true
        }
    ]
}
```

**POST /api/imports/import 请求体:**
```json
{
    "external_id": "c/987654321",
    "source": "mercari-hunter",
    "purchase_price": 18500,
    "purchase_date": "2026-05-09",
    "location_id": 2,
    "tags": ["3C", "ゲーム機"],
    "description": "メルカリで見つけた安物"
}
```

### 3.6 设置 (Settings)

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/settings` | 获取所有设置 |
| `PATCH` | `/api/settings` | 批量更新设置 |

---

## 4. 前端布局设计 (Frontend Layout)

### 4.1 技术约束
- **纯 HTML/CSS/JS**，无构建步骤，无框架依赖
- **暗色主题 (Dark Theme)**，移动端优先 (Mobile-first responsive)
- **PWA 支持**：可添加到手机主屏幕，离线缓存关键页面
- **语言**：界面中日双语 (默认中文，可切换日文)

### 4.2 页面结构

```
static/
├── index.html              # 主 SPA 入口 (hash routing)
├── css/
│   ├── main.css            # 全局样式 + 暗色主题变量
│   ├── dashboard.css       # 看板页样式
│   ├── inventory.css       # 库存列表/详情样式
│   ├── import.css          # 导入页样式
│   └── profit.css          # 利润页样式
├── js/
│── app.js                  # 主应用: 路由、状态管理、API 封装
│   ├── api.js              # fetch 封装 + 错误处理
│   ├── dashboard.js        # 看板页逻辑
│   ├── inventory.js        # 库存管理逻辑
│   ├── import.js           # 爬虫联动导入逻辑
│   ├── profit.js           # 利润计算逻辑
│   ├── settings.js         # 设置页逻辑
│   └── utils.js            # 格式化、费率计算工具
└── icons/
    └── favicon.ico
```

### 4.3 页面详情

#### 📊 看板页 (`#dashboard`) — 首页

```
┌─────────────────────────────────────────────┐
│  📦 Inventory Manager          [🌐 中/日]   │
├─────────────────────────────────────────────┤
│  [📊 看板] [📦 库存] [💰 利润] [🔍 导入] [⚙️ 设置]│
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 在庫     │ │ 出品済み  │ │ 販売済み  │   │
│  │   42     │ │   28     │ │   15     │   │
│  └──────────┘ └──────────┘ └──────────┘   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │ 💰 累計净利润: ¥1,800,000           │   │
│  │  本月: ¥180,000  |  利润率: 42%     │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │ 最近动态 (Recent Activity)          │   │
│  │ ────────────────────────────────    │   │
│  │ 🟢 MacBook Air M2 → 上架 ¥85,000   │   │
│  │ 🟡 SSD 1TB → 在库 (A棚-3排)         │   │
│  │ 🔴 RTX 3060 → 已售 ¥32,000          │   │
│  │ 🟢 Nintendo Switch → 已购入 ¥18,500 │   │
│  └─────────────────────────────────────┘   │
│                                             │
└─────────────────────────────────────────────┘
```

#### 📦 库存页 (`#inventory`)

**Tab 1: 列表视图**
```
┌─────────────────────────────────────────────┐
│  📦 库存管理                                 │
│  [搜索框🔍] [状态▼] [平台▼] [标签▼] [位置▼] │
├─────────────────────────────────────────────┤
│  ┌─状态─商品名───────────购入价──售价──利润─┐│
│  │ 🟢 SSD 1TB         ¥4,500  ¥8,000 ¥3,500││
│  │ 🔵 RTX 3060        ¥28,000 ¥32,000 ¥4,000││
│  │ 🟡 MacBook Air M2  ¥55,000 ¥85,000 ¥30K ││
│  │ ⚪ Nintendo Switch  ¥18,500  —    —     ││
│  └─────────────────────────────────────────┘│
│                                             │
│  [分页: ← 1/4 →]                            │
└─────────────────────────────────────────────┘
```

**Tab 2: 商品详情 (点击展开)**
```
┌─────────────────────────────────────────────┐
│  ← 返回                                     │
│  MacBook Air M2 256GB スペースグレイ        │
│  ┌─────────────────────────────────────┐   │
│  │           [商品图片]                 │   │
│  └─────────────────────────────────────┘   │
│  SKU: INV-20260509-0042                     │
│  状态: 🟡 在库 → [▼ 变更状态]               │
│  位置: A棚-3排                               │
│  购入: ¥55,000 (Mercari)  2026/05/09        │
│  标签: #Mac #3C #限定                       │
│  链接: [打开商品页 ↗]                       │
│                                             │
│  ── 销售记录 ──                             │
│  (暂无)                                      │
│                                             │
│  [记录销售] [编辑] [删除]                    │
└─────────────────────────────────────────────┘
```

#### 💰 利润页 (`#profit`)

```
┌─────────────────────────────────────────────┐
│  💰 利润分析                                 │
│  [本月 ▼] [全部平台 ▼]                      │
├─────────────────────────────────────────────┤
│  ┌─────────────────────────────────────┐   │
│  │ 总览                                │   │
│  │ 总购入: ¥4,250,000                  │   │
│  │ 总收入: ¥6,800,000                  │   │
│  │ 手续费:   ¥820,000                  │   │
│  │ 净利润:   ¥1,800,000  (利润率 42%)  │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  按平台:                                     │
│  ┌──────────┬───────┬───────┬───────┐     │
│  │ 平台     │ 收入  │ 成本  │ 利润  │     │
│  ├──────────┼───────┼───────┼───────┤     │
│  │ Mercari  │ ¥4.2M │ ¥2.8M │ ¥1.4M │     │
│  │ Amazon   │ ¥2.6M │ ¥1.4M │ ¥0.4M │     │
│  └──────────┴───────┴───────┴───────┘     │
│                                             │
│  月度趋势:                                   │
│  │ 5月 ████ ¥180K                         │
│  │ 4月 ██████ ¥320K                       │
│  │ 3月 ███ ¥95K                           │
│  └────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

#### 🔍 导入页 (`#import`) — 爬虫联动

```
┌─────────────────────────────────────────────┐
│  🔍 从爬虫导入商品                           │
│  [mercari-hunter ▼] [刷新]                   │
├─────────────────────────────────────────────┤
│  发现 23 个低价商品                          │
├─────────────────────────────────────────────┤
│  ┌─ 商品 ─────────────────────────────────┐│
│  │ Nintendo Switch OLED ホワイト          ││
│  │ 购入价: ¥18,500 | 市场均价: ¥25,000     ││
│  │ 预期利润: ¥6,500 (26%)                  ││
│  │ [📥 入库] [🔗 打开链接]                  ││
│  ├────────────────────────────────────────┤│
│  │ SSD 1TB 外付け                         ││
│  │ 购入价: ¥4,500  | 市场均价: ¥8,000      ││
│  │ 预期利润: ¥3,500 (44%)                  ││
│  │ [📥 入库] [🔗 打开链接]                  ││
│  └────────────────────────────────────────┘│
│                                             │
│  [批量入库选中项]                            │
└─────────────────────────────────────────────┘
```

**入库弹窗 (点击 📥 后):**
```
┌─────────────────────────────────────────────┐
│  📥 入库: Nintendo Switch OLED ホワイト     │
│  购入价: [¥18,500]                          │
│  购入日期: [2026/05/09]                     │
│  存放位置: [A棚-3排 ▼]                      │
│  标签: [3C, ゲーム機]                       │
│  备注: [________________________]           │
│                                             │
│  [确认入库] [取消]                          │
└─────────────────────────────────────────────┘
```

#### ⚙️ 设置页 (`#settings`)

```
┌─────────────────────────────────────────────┐
│  ⚙️ 系统设置                                 │
├─────────────────────────────────────────────┤
│  平台手续费率:                               │
│  Mercari: [10]%  Amazon: [15]%  其他: [10]%│
│                                             │
│  爬虫数据库路径:                             │
│  mercari-hunter: [/home/logic126/.../mercari.db]│
│  amazon-outlet:  [/home/logic126/.../amazon_outlet.db]│
│  [+ 添加新源]                                │
│                                             │
│  仓库位置管理:                               │
│  ┌─────────────────────────────────────┐   │
│  │ A棚-3排 [编辑] [删除]                │   │
│  │ B棚-1排 [编辑] [删除]                │   │
│  │ 地下室-纸箱2 [编辑] [删除]            │   │
│  └─────────────────────────────────────┘   │
│  [+ 添加位置]                                │
└─────────────────────────────────────────────┘
```

### 4.4 CSS 暗色主题变量

```css
:root {
    --bg-primary: #1a1a2e;
    --bg-secondary: #16213e;
    --bg-card: #0f3460;
    --bg-input: #1a1a3e;
    --text-primary: #e0e0e0;
    --text-secondary: #a0a0a0;
    --accent: #e94560;
    --accent-hover: #ff6b6b;
    --success: #4ecca3;
    --warning: #f9a825;
    --danger: #e94560;
    --border: #2a2a4a;
    --shadow: rgba(0, 0, 0, 0.3);
    --radius: 8px;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', sans-serif;
}
```

---

## 5. 爬虫联动设计 (Scraper Integration)

### 5.1 数据流向

```
┌──────────────────────┐         ┌──────────────────────┐
│  mercari-hunter      │         │  amazon-outlet-hunter│
│  data/mercari.db     │         │  data/amazon_outlet.db│
│                      │         │                      │
│  items 表 ───────────┼────────▶│                      │
│  market_prices 表 ───┼── 读取  │                      │
│  alerts 表 ──────────┼── 读取  │                      │
└──────────────────────┘         └──────────┬───────────┘
                                            │ 读取
                                            │  items 表
                                            │  price_history 表
                                            ▼
                                  ┌──────────────────────┐
                                  │  inventory-manager   │
                                  │  API: /api/imports/  │
                                  │                      │
                                  │  候选列表 → 一键入库  │
                                  │  → items 表          │
                                  └──────────────────────┘
```

### 5.2 Mercari-Hunter 联动

**读取逻辑:**
```python
# 从 mercari.db 拉取候选商品
def get_mercari_candidates(db_path: str, flagged_only: bool = True, limit: int = 50):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    query = """
        SELECT i.*, mp.price_median, mp.price_mean
        FROM items i
        LEFT JOIN market_prices mp ON normalize_name(i.name) = mp.item_name
        WHERE 1=1
        ORDER BY i.crawled_at DESC
        LIMIT ?
    """
    if flagged_only:
        query = query.replace("WHERE 1=1", "WHERE i.is_flagged = 1")
    rows = conn.execute(query, [limit]).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

**字段映射 (mercari → inventory):**

| mercari.db.items | inventory.items |
|-------------------|-----------------|
| `name` | `name` |
| `price` | `purchase_price` (预填，可修改) |
| `url` | `source_url` |
| `image_url` | `image_url` |
| `mercari_id` | `source_item_id` |
| (固定) | `source_platform = "mercari"` |
| `description` | `description` |

**利润预判:**
```python
# 结合 market_prices 计算预期利润
expected_revenue = row['price_median'] or row['price'] * 1.5
platform_fee = int(expected_revenue * 0.10)  # Mercari 10%
potential_profit = expected_revenue - row['price'] - platform_fee
```

### 5.3 Amazon-Outlet-Hunter 联动

**读取逻辑:**
```python
def get_amazon_candidates(db_path: str, keyword: str = None, min_discount: int = 0, limit: int = 50):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    query = """
        SELECT i.*, ph.price as lowest_price
        FROM items i
        LEFT JOIN (
            SELECT asin, MIN(price) as price
            FROM price_history
            GROUP BY asin
        ) ph ON i.asin = ph.asin
        WHERE i.in_stock = 1
        ORDER BY i.discount_percent DESC
        LIMIT ?
    """
    params = []
    if keyword:
        query += " AND i.keyword_name = ?"
        params.append(keyword)
    if min_discount:
        query += " AND i.discount_percent >= ?"
        params.append(min_discount)
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

**字段映射 (amazon → inventory):**

| amazon_outlet.db.items | inventory.items |
|-------------------------|-----------------|
| `title` | `name` |
| `price` | `purchase_price` (预填，可修改) |
| `url` | `source_url` |
| `image_url` | `image_url` |
| `asin` | `source_item_id` |
| (固定) | `source_platform = "amazon_outlet"` |
| `category` | 自动添加为 tag |

### 5.4 一键入库 API 实现要点

```python
@router.post("/imports/import")
async def import_item(req: ImportRequest):
    """
    1. 根据 source + external_id 从爬虫 DB 读取原始数据
    2. 用原始数据预填字段，用户传入的字段覆盖
    3. 生成 SKU (INV-YYYYMMDD-NNNN)
    4. 插入 items 表
    5. 插入 status_history (初始状态: purchased)
    6. 返回新建的商品
    """
    # Step 1: 读取原始数据
    raw_item = fetch_from_source(req.source, req.external_id)
    
    # Step 2: 合并数据
    item_data = {
        "name": raw_item["name"],
        "source_platform": raw_item["platform"],
        "source_item_id": req.external_id,
        "purchase_price": req.purchase_price or raw_item["price"],
        "purchase_date": req.purchase_date or datetime.now().strftime("%Y-%m-%d"),
        "image_url": raw_item.get("image_url"),
        "source_url": raw_item.get("url"),
        "location_id": req.location_id,
        "tags": json.dumps(req.tags or []),
        "status": "purchased",
    }
    
    # Step 3-6: 生成 SKU, 插入, 返回
    sku = generate_sku()
    item_data["sku"] = sku
    db.insert("items", item_data)
    return {"item": item_data, "sku": sku}
```

---

## 6. 项目文件结构

```
~/workspace/inventory-manager/
├── DESIGN.md                     # 本设计文档
├── main.py                       # FastAPI 应用入口
├── requirements.txt              # Python 依赖
├── start.sh                      # 启动脚本
├── config.yaml                   # 配置 (端口、DB路径、爬虫路径)
├── app/
│   ├── __init__.py
│   ├── database.py               # SQLite 连接管理
│   ├── models.py                 # Pydantic 数据模型
│   ├── schemas.py                # 数据库 schema 初始化
│   └── routers/
│       ├── __init__.py
│       ├── items.py              # 商品 CRUD + 状态变更
│       ├── sales.py              # 销售记录
│       ├── dashboard.py          # 统计看板
│       ├── locations.py          # 仓库位置
│       ├── imports.py            # 爬虫联动导入
│       └── settings.py           # 系统设置
├── data/
│   └── inventory.db              # SQLite 数据库 (自动生成)
└── static/
    ├── index.html                # SPA 主页面
    ├── css/
    │   ├── main.css              # 全局 + 暗色主题
    │   ├── dashboard.css
    │   ├── inventory.css
    │   ├── import.css
    │   └── profit.css
    ├── js/
    │   ├── app.js                # 路由 + 状态管理
    │   ├── api.js                # API 封装
    │   ├── dashboard.js
    │   ├── inventory.js
    │   ├── import.js
    │   ├── profit.js
    │   ├── settings.js
    │   └── utils.js              # 工具函数
    └── icons/
        └── favicon.ico
```

### 配置文件 (config.yaml)

```yaml
server:
  host: "0.0.0.0"
  port: 8765
  reload: true

database:
  path: "./data/inventory.db"

scrapers:
  mercari-hunter:
    db_path: "/home/logic126/workspace/mercari-hunter/data/mercari.db"
    platform: "mercari"
  amazon-outlet-hunter:
    db_path: "/home/logic126/workspace/amazon-outlet-hunter/data/amazon_outlet.db"
    platform: "amazon_outlet"

fees:
  mercari: 0.10
  amazon: 0.15
  other: 0.10
```

---

## 7. 关键实现细节

### 7.1 SKU 生成规则

```python
def generate_sku() -> str:
    """生成格式: INV-YYYYMMDD-NNNN"""
    today = datetime.now().strftime("%Y%m%d")
    # 查询当天已有数量
    count = db.execute(
        "SELECT COUNT(*) FROM items WHERE sku LIKE ?", 
        (f"INV-{today}-%",)
    ).fetchone()[0]
    return f"INV-{today}-{count + 1:04d}"
```

### 7.2 利润计算

```python
def calculate_profit(sale_price: int, purchase_price: int, 
                     sale_platform: str, shipping: int = 0, other: int = 0) -> dict:
    fee_rates = {"mercari": 0.10, "amazon": 0.15, "other": 0.10}
    rate = fee_rates.get(sale_platform, 0.10)
    platform_fee = int(sale_price * rate)
    net_profit = sale_price - platform_fee - purchase_price - shipping - other
    return {
        "sale_price": sale_price,
        "platform_fee": platform_fee,
        "shipping_cost": shipping,
        "other_cost": other,
        "net_profit": net_profit,
        "profit_margin": net_profit / sale_price if sale_price else 0,
    }
```

### 7.3 CORS 配置

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # 同机部署，生产可限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 7.4 启动脚本 (start.sh)

```bash
#!/bin/bash
cd /home/logic126/workspace/inventory-manager
python3 -m uvicorn main:app --host 0.0.0.0 --port 8765 --reload
```

---

## 8. 状态变更 API 示例

```http
# 变更状态: purchased → in_stock
POST /api/items/42/status
{
    "to_status": "in_stock",
    "note": "已入库，放A棚",
    "location_id": 1
}

# 记录销售: in_stock → sold
POST /api/items/42/sale
{
    "sale_price": 85000,
    "sale_platform": "mercari",
    "sale_url": "https://mercari.jp/items/xxx",
    "shipping_cost": 650,
    "sale_date": "2026-05-15"
}
# → 自动计算: platform_fee=8500, net_profit=21350
# → 自动创建 sale_record
# → 自动更新 item.status = "sold"
# → 自动记录 status_history

# 结算: sold → settled
POST /api/sales/1/settle
{}
# → 更新 sale_record.settled = true
# → 更新 item.status = "settled"
```

---

## 9. 移动端适配要点

| 特性 | 实现方式 |
|------|----------|
| 响应式布局 | CSS Grid + Flexbox, 断点 768px / 480px |
| 触摸友好 | 按钮最小 44x44px, 间距充足 |
| 图片加载 | 懒加载 + 压缩 (CSS object-fit) |
| PWA | manifest.json + service worker 缓存 |
| 输入优化 | 数字键盘 (`inputmode="numeric"`) |
| 下拉刷新 | 手动刷新按钮 (避免 pull-to-refresh 冲突) |

---

## 10. 安全与备份

| 项目 | 方案 |
|------|------|
| 数据库备份 | 定时脚本 `cp inventory.db inventory.db.bak.$(date +%Y%m%d)` |
| 权限 | 无认证 (内网使用), 可加 Basic Auth |
| 数据导入 | 只读连接爬虫 DB, 不修改原始数据 |
| 并发 | SQLite WAL 模式, 适合单机低并发 |

---

## 总结

| 维度 | 设计要点 |
|------|----------|
| **数据库** | 6 张表, 状态机驱动, 审计流水完整 |
| **API** | RESTful, 18 个端点, 覆盖 CRUD + 统计 + 导入 |
| **前端** | 纯 HTML/CSS/JS SPA, 暗色主题, 移动端优先 |
| **爬虫联动** | 只读连接外部 DB, 候选列表 + 一键入库, 利润预判 |
| **利润计算** | 自动扣手续费 (Mercari 10%, Amazon 15%), 可配置 |
| **部署** | 单文件启动 `./start.sh`, WSL 本地访问 `localhost:8765` |
