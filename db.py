#!/usr/bin/env python3
"""
Database initialization and connection helpers — PostgreSQL backend.

Provides a sqlite3-compatible interface over psycopg2 so server.py code
doesn't need to change: conn.execute(sql, params) works with ? placeholders.
"""

import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from pathlib import Path
from typing import Any

# Load .env file
load_dotenv(Path(__file__).parent / ".env")


def _env_db(prefix: str, defaults: dict) -> dict:
    """Load DB config from environment variables with a given prefix."""
    env_prefix = f"{prefix}_DB"
    return {
        "host": os.getenv(f"{env_prefix}_HOST", defaults.get("host", "localhost")),
        "port": int(os.getenv(f"{env_prefix}_PORT", str(defaults.get("port", 5432)))),
        "dbname": os.getenv(f"{env_prefix}_NAME", defaults.get("dbname", "")),
        "user": os.getenv(f"{env_prefix}_USER", defaults.get("user", "")),
        "password": os.getenv(f"{env_prefix}_PASSWORD", defaults.get("password", "")),
    }


def _load_db_config() -> dict:
    """Load inventory DB config from environment variables."""
    return _env_db("INV", {
        "host": "localhost",
        "port": 5432,
        "dbname": "inventory",
        "user": "mercari",
        "password": "",
    })


def get_mercari_db_config() -> dict:
    """Load Mercari Hunter DB config from environment variables."""
    return _env_db("MERCARI", {
        "host": "localhost",
        "port": 5432,
        "dbname": "mercari",
        "user": "mercari",
        "password": "",
    })


def get_amazon_db_config() -> dict:
    """Load Amazon Outlet Hunter DB config from environment variables."""
    return _env_db("AMAZON", {
        "host": "localhost",
        "port": 5432,
        "dbname": "amazon_outlet",
        "user": "amazon_outlet",
        "password": "",
    })


SCHEMA_SQL = """
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
    image_url_original TEXT,
    source_url      TEXT,
    location_id     INTEGER,
    status          TEXT NOT NULL DEFAULT 'purchased',
    tags            TEXT DEFAULT '[]',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_source_platform ON items(source_platform);
CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);

CREATE TABLE IF NOT EXISTS status_history (
    id              SERIAL PRIMARY KEY,
    item_id         INTEGER NOT NULL,
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    note            TEXT,
    changed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(id)
);

CREATE INDEX IF NOT EXISTS idx_status_history_item ON status_history(item_id);

CREATE TABLE IF NOT EXISTS sale_records (
    id              SERIAL PRIMARY KEY,
    item_id         INTEGER NOT NULL,
    sale_price      INTEGER NOT NULL,
    sale_platform   TEXT NOT NULL,
    sale_url        TEXT,
    platform_fee    INTEGER NOT NULL DEFAULT 0,
    shipping_cost   INTEGER DEFAULT 0,
    other_cost      INTEGER DEFAULT 0,
    net_profit      INTEGER NOT NULL,
    sale_date       TIMESTAMP NOT NULL,
    settled         BOOLEAN DEFAULT FALSE,
    settled_at      TIMESTAMP,
    note            TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(id)
);

CREATE INDEX IF NOT EXISTS idx_sale_records_item ON sale_records(item_id);
CREATE INDEX IF NOT EXISTS idx_sale_records_platform ON sale_records(sale_platform);

CREATE TABLE IF NOT EXISTS locations (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

DEFAULT_SETTINGS = {
    "fee_rate_mercari": "0.10",
    "fee_rate_amazon": "0.15",
    "fee_rate_other": "0.10",
    "currency": "JPY",
    "timezone": "Asia/Tokyo",
}

VALID_STATUSES = [
    "purchased", "in_stock", "listed", "sold", "settled", "discarded", "returned",
]

STATUS_LABELS = {
    "purchased": "購入済み",
    "in_stock": "在庫",
    "listed": "出品済み",
    "sold": "販売済み",
    "settled": "決済済み",
    "discarded": "廃棄",
    "returned": "返品",
}


class _PGRow(dict):
    """Dict-like row supporting both row['col'] and row[0] numeric index access."""

    def __init__(self, data: dict):
        super().__init__(data)
        self._keys = list(data.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._keys[key])
        return super().__getitem__(key)


class _PGCursor:
    """Cursor wrapper that makes psycopg2 behave like sqlite3."""

    def __init__(self, pg_conn):
        self._conn = pg_conn
        self._cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        self.lastrowid = None

    def execute(self, sql: str, params: tuple | list | None = None):
        # Convert ? placeholders to %s for psycopg2
        if "?" in sql and params:
            sql = sql.replace("?", "%s")
        elif "%" in sql and not params:
            # No params but SQL has % (e.g. LIKE '%foo%') — escape for psycopg2
            sql = sql.replace("%", "%%")
        # For INSERT into items/sale_records/status_history/locations, add RETURNING id
        upper = sql.strip().upper()
        is_insert = upper.startswith("INSERT")
        has_returning = "RETURNING" in upper
        has_id_table = any(t in upper for t in ("INTO ITEMS", "INTO SALE_RECORDS", "INTO STATUS_HISTORY", "INTO LOCATIONS"))
        if is_insert and not has_returning and has_id_table:
            sql = sql.rstrip() + " RETURNING id"
            self._cur.execute(sql, params or ())
            row = self._cur.fetchone()
            if row:
                self.lastrowid = row["id"]
            else:
                self.lastrowid = None
        else:
            self._cur.execute(sql, params or ())
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return _PGRow(dict(row)) if row else None

    def fetchall(self):
        return [_PGRow(dict(r)) for r in self._cur.fetchall()]

    def fetchval(self, column=0):
        row = self._cur.fetchone()
        if row is None:
            return None
        if isinstance(column, int):
            return list(row.values())[column]
        return row[column]


class _PGConnection:
    """Connection wrapper that mimics sqlite3 interface over psycopg2."""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql: str, params: tuple | list | None = None):
        cur = _PGCursor(self._conn)
        cur.execute(sql, params)
        return cur

    def executescript(self, script: str):
        self._conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        cur = self._conn.cursor()
        try:
            cur.execute(script)
        finally:
            cur.close()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_connection() -> _PGConnection:
    """Get a sqlite3-compatible connection wrapping psycopg2."""
    cfg = _load_db_config()
    pg_conn = psycopg2.connect(**cfg, connect_timeout=5)
    return _PGConnection(pg_conn)


def init_db():
    """Initialize database schema and default settings."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        # Migration: add image_url_original column if it doesn't exist
        conn.executescript("ALTER TABLE items ADD COLUMN IF NOT EXISTS image_url_original TEXT")
        # Insert default settings (ignore if exists)
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO NOTHING",
                (k, v),
            )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized (PostgreSQL)")
