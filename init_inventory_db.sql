-- Initialize inventory database schema
-- Run: psql -h localhost -U mercari -d inventory < init_inventory_db.sql

CREATE TABLE IF NOT EXISTS items (
    id              SERIAL PRIMARY KEY,
    sku             TEXT UNIQUE,
    name            TEXT NOT NULL,
    description     TEXT,
    source_platform TEXT NOT NULL DEFAULT 'other',
    source_item_id  TEXT,
    purchase_price  INTEGER NOT NULL DEFAULT 0,
    purchase_date   TIMESTAMP,
    image_url       TEXT,
    source_url      TEXT,
    location_id     INTEGER,
    status          TEXT NOT NULL DEFAULT 'purchased',
    tags            TEXT DEFAULT '[]',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_source_platform ON items(source_platform);

CREATE TABLE IF NOT EXISTS locations (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    active      BOOLEAN DEFAULT true,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sale_records (
    id            SERIAL PRIMARY KEY,
    item_id       INTEGER NOT NULL REFERENCES items(id),
    sale_price    INTEGER NOT NULL,
    sale_platform TEXT NOT NULL,
    sale_url      TEXT,
    platform_fee  INTEGER NOT NULL DEFAULT 0,
    shipping_cost INTEGER DEFAULT 0,
    other_cost    INTEGER DEFAULT 0,
    net_profit    INTEGER NOT NULL,
    sale_date     TIMESTAMP NOT NULL,
    settled       BOOLEAN DEFAULT false,
    settled_at    TIMESTAMP,
    note          TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sale_records_item ON sale_records(item_id);
CREATE INDEX IF NOT EXISTS idx_sale_records_platform ON sale_records(sale_platform);

CREATE TABLE IF NOT EXISTS status_history (
    id          SERIAL PRIMARY KEY,
    item_id     INTEGER NOT NULL REFERENCES items(id),
    from_status TEXT,
    to_status   TEXT NOT NULL,
    note        TEXT,
    changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_status_history_item ON status_history(item_id);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
