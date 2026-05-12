#!/usr/bin/env python3
"""
Inventory Manager — Backend API
Reselling inventory management with profit tracking.
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from db import (
    VALID_STATUSES,
    STATUS_LABELS,
    DEFAULT_SETTINGS,
    get_connection,
    init_db,
)

import yaml

# ── Init ────────────────────────────────────────────────
init_db()

app = FastAPI(title="Inventory Manager")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
import os
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ── Pydantic Models ─────────────────────────────────────
class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1)
    source_platform: str = "other"
    source_item_id: str | None = None
    purchase_price: int = 0
    purchase_date: str | None = None
    image_url: str | None = None
    source_url: str | None = None
    location_id: int | None = None
    tags: list[str] = []
    description: str = ""


class ItemUpdate(BaseModel):
    name: str | None = None
    source_platform: str | None = None
    source_item_id: str | None = None
    purchase_price: int | None = None
    purchase_date: str | None = None
    image_url: str | None = None
    source_url: str | None = None
    location_id: int | None = None
    tags: list[str] | None = None
    description: str | None = None


class StatusChange(BaseModel):
    to_status: str
    note: str = ""


class SaleCreate(BaseModel):
    sale_price: int = Field(..., gt=0)
    sale_platform: str
    sale_url: str | None = None
    platform_fee: int = 0
    shipping_cost: int = 0
    other_cost: int = 0
    sale_date: str | None = None
    note: str = ""


class SaleUpdate(BaseModel):
    sale_price: int | None = None
    sale_platform: str | None = None
    sale_url: str | None = None
    platform_fee: int | None = None
    shipping_cost: int | None = None
    other_cost: int | None = None
    sale_date: str | None = None
    note: str | None = None
    settled: bool | None = None


class LocationCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


# ── Helpers ─────────────────────────────────────────────
def row_to_dict(row) -> dict:
    return dict(row) if row else {}


def generate_sku() -> str:
    now = datetime.now()
    return f"INV-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"


def dict_to_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


# ── Items API ───────────────────────────────────────────
@app.get("/api/items")
async def list_items(
    status: str | None = Query(None),
    platform: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    conn = get_connection()
    try:
        where = []
        params: list = []

        if status:
            where.append("status = ?")
            params.append(status)
        if platform:
            where.append("source_platform = ?")
            params.append(platform)
        if search:
            where.append("(name LIKE ? OR description LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_sql = " WHERE " + " AND ".join(where) if where else ""
        offset = (page - 1) * per_page

        rows = conn.execute(
            f"SELECT i.*, l.name as location_name "
            f"FROM items i LEFT JOIN locations l ON i.location_id = l.id "
            f"{where_sql} ORDER BY i.created_at DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

        total = conn.execute(
            f"SELECT COUNT(*) FROM items{where_sql}", params
        ).fetchone()[0]

        # Get latest sale record for each item
        item_ids = [r["id"] for r in rows]
        sales = {}
        if item_ids:
            placeholders = ",".join("?" * len(item_ids))
            sale_rows = conn.execute(
                f"SELECT item_id, sale_price, sale_platform, sale_date, net_profit, settled "
                f"FROM sale_records WHERE item_id IN ({placeholders}) "
                f"ORDER BY sale_date DESC",
                item_ids,
            ).fetchall()
            for sr in sale_rows:
                if sr["item_id"] not in sales:
                    sales[sr["item_id"]] = dict(sr)

        return {
            "items": [
                {**row_to_dict(r), "sale": sales.get(r["id"])}
                for r in rows
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    finally:
        conn.close()


@app.get("/api/items/{item_id}")
async def get_item(item_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT i.*, l.name as location_name "
            "FROM items i LEFT JOIN locations l ON i.location_id = l.id "
            "WHERE i.id = ?", (item_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Item not found")

        sales = conn.execute(
            "SELECT * FROM sale_records WHERE item_id = ? ORDER BY sale_date DESC",
            (item_id,),
        ).fetchall()

        history = conn.execute(
            "SELECT * FROM status_history WHERE item_id = ? ORDER BY changed_at DESC",
            (item_id,),
        ).fetchall()

        return {
            "item": row_to_dict(row),
            "sales": [row_to_dict(s) for s in sales],
            "history": [row_to_dict(h) for h in history],
        }
    finally:
        conn.close()


@app.post("/api/items")
async def create_item(item: ItemCreate):
    sku = generate_sku()
    tags_json = dict_to_json(item.tags)
    purchase_date = item.purchase_date or datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO items (sku, name, description, source_platform, source_item_id, "
            "purchase_price, purchase_date, image_url, source_url, location_id, status, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sku, item.name, item.description, item.source_platform,
             item.source_item_id, item.purchase_price, purchase_date,
             item.image_url, item.source_url, item.location_id,
             "purchased", tags_json),
        )
        # Record initial status
        conn.execute(
            "INSERT INTO status_history (item_id, from_status, to_status, note) "
            "VALUES (?, NULL, 'purchased', '新規登録')",
            (cursor.lastrowid,),
        )
        conn.commit()
        return {"id": cursor.lastrowid, "sku": sku, "status": "created"}
    finally:
        conn.close()


@app.patch("/api/items/{item_id}")
async def update_item(item_id: int, item: ItemUpdate):
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Item not found")

        updates = item.model_dump(exclude_none=True)
        if "tags" in updates:
            updates["tags"] = dict_to_json(updates["tags"])

        if not updates:
            return {"status": "no changes"}

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        set_clause += ", updated_at = CURRENT_TIMESTAMP"
        values = list(updates.values()) + [item_id]

        conn.execute(f"UPDATE items SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return {"status": "updated"}
    finally:
        conn.close()


@app.delete("/api/items/{item_id}")
async def delete_item(item_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM status_history WHERE item_id = ?", (item_id,))
        conn.execute("DELETE FROM sale_records WHERE item_id = ?", (item_id,))
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
        return {"status": "deleted"}
    finally:
        conn.close()


@app.post("/api/items/{item_id}/status")
async def change_status(item_id: int, change: StatusChange):
    if change.to_status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Valid: {VALID_STATUSES}")

    conn = get_connection()
    try:
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(404, "Item not found")

        old_status = item["status"]
        conn.execute(
            "UPDATE items SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (change.to_status, item_id),
        )
        conn.execute(
            "INSERT INTO status_history (item_id, from_status, to_status, note) "
            "VALUES (?, ?, ?, ?)",
            (item_id, old_status, change.to_status, change.note),
        )
        conn.commit()
        return {
            "status": "changed",
            "from": old_status,
            "to": change.to_status,
        }
    finally:
        conn.close()


@app.post("/api/items/{item_id}/sale")
async def record_sale(item_id: int, sale: SaleCreate):
    conn = get_connection()
    try:
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(404, "Item not found")

        sale_date = sale.sale_date or datetime.now().strftime("%Y-%m-%d")
        net_profit = (sale.sale_price - sale.platform_fee - item["purchase_price"]
                      - sale.shipping_cost - sale.other_cost)

        cursor = conn.execute(
            "INSERT INTO sale_records (item_id, sale_price, sale_platform, sale_url, "
            "platform_fee, shipping_cost, other_cost, net_profit, sale_date, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, sale.sale_price, sale.sale_platform, sale.sale_url,
             sale.platform_fee, sale.shipping_cost, sale.other_cost,
             net_profit, sale_date, sale.note),
        )
        # Auto change status to sold
        conn.execute(
            "UPDATE items SET status = 'sold', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (item_id,),
        )
        conn.execute(
            "INSERT INTO status_history (item_id, from_status, to_status, note) "
            "VALUES (?, ?, 'sold', ?)",
            (item_id, item["status"], f"販売記録: ¥{sale.sale_price}"),
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "net_profit": net_profit,
            "status": "sold",
        }
    finally:
        conn.close()


# ── Sales API ───────────────────────────────────────────
@app.get("/api/sales")
async def list_sales(
    platform: str | None = None,
    settled: bool | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    conn = get_connection()
    try:
        where = []
        params: list = []

        if platform:
            where.append("sr.sale_platform = ?")
            params.append(platform)
        if settled is not None:
            where.append("sr.settled = %s::boolean")
            params.append(1 if settled else 0)

        where_sql = " WHERE " + " AND ".join(where) if where else ""
        offset = (page - 1) * per_page

        rows = conn.execute(
            f"SELECT sr.*, i.name as item_name, i.purchase_price, i.sku "
            f"FROM sale_records sr JOIN items i ON sr.item_id = i.id "
            f"{where_sql} ORDER BY sr.sale_date DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

        total = conn.execute(
            f"SELECT COUNT(*) FROM sale_records sr JOIN items i ON sr.item_id = i.id{where_sql}",
            params,
        ).fetchone()[0]

        return {
            "sales": [row_to_dict(r) for r in rows],
            "total": total,
        }
    finally:
        conn.close()


@app.patch("/api/sales/{sale_id}")
async def update_sale(sale_id: int, sale: SaleUpdate):
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM sale_records WHERE id = ?", (sale_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Sale not found")

        updates = sale.model_dump(exclude_none=True)
        if not updates:
            return {"status": "no changes"}

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [sale_id]
        conn.execute(f"UPDATE sale_records SET {set_clause} WHERE id = ?", values)

        # If settled changed to True, record timestamp
        if updates.get("settled") is True and not existing["settled"]:
            conn.execute(
                "UPDATE sale_records SET settled_at = CURRENT_TIMESTAMP WHERE id = ?",
                (sale_id,),
            )

        # Recalculate net_profit if relevant fields changed
        if any(k in updates for k in ("sale_price", "platform_fee", "shipping_cost", "other_cost")):
            item = conn.execute("SELECT purchase_price FROM items WHERE id = ?",
                                (existing["item_id"],)).fetchone()
            new_price = updates.get("sale_price", existing["sale_price"])
            new_fee = updates.get("platform_fee", existing["platform_fee"])
            new_ship = updates.get("shipping_cost", existing["shipping_cost"])
            new_other = updates.get("other_cost", existing["other_cost"])
            new_profit = new_price - new_fee - item["purchase_price"] - new_ship - new_other
            conn.execute(
                "UPDATE sale_records SET net_profit = ? WHERE id = ?",
                (new_profit, sale_id),
            )

        conn.commit()
        return {"status": "updated"}
    finally:
        conn.close()


@app.post("/api/sales/{sale_id}/settle")
async def settle_sale(sale_id: int):
    conn = get_connection()
    try:
        sale = conn.execute("SELECT * FROM sale_records WHERE id = ?", (sale_id,)).fetchone()
        if not sale:
            raise HTTPException(404, "Sale not found")

        conn.execute(
            "UPDATE sale_records SET settled = 1, settled_at = CURRENT_TIMESTAMP WHERE id = ?",
            (sale_id,),
        )
        # Also update item status
        conn.execute(
            "UPDATE items SET status = 'settled' WHERE id = ?",
            (sale["item_id"],),
        )
        conn.commit()
        return {"status": "settled"}
    finally:
        conn.close()


# ── Locations API ───────────────────────────────────────
@app.get("/api/locations")
async def list_locations():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT l.*, COUNT(i.id) as item_count "
            "FROM locations l LEFT JOIN items i ON l.id = i.location_id "
            "WHERE l.active = 1 GROUP BY l.id ORDER BY l.name"
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.post("/api/locations")
async def create_location(loc: LocationCreate):
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO locations (name, description) VALUES (?, ?)",
            (loc.name, loc.description),
        )
        conn.commit()
        return {"id": cursor.lastrowid, "status": "created"}
    finally:
        conn.close()


@app.delete("/api/locations/{location_id}")
async def delete_location(location_id: int):
    conn = get_connection()
    try:
        conn.execute("UPDATE locations SET active = 0 WHERE id = ?", (location_id,))
        conn.execute("UPDATE items SET location_id = NULL WHERE location_id = ?", (location_id,))
        conn.commit()
        return {"status": "deleted"}
    finally:
        conn.close()


# ── Dashboard API ───────────────────────────────────────
@app.get("/api/dashboard/summary")
async def dashboard_summary():
    conn = get_connection()
    try:
        # Status counts
        status_rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM items GROUP BY status"
        ).fetchall()
        status_counts = {r["status"]: r["count"] for r in status_rows}

        # Total cost (items not settled/discarded)
        inventory_value = conn.execute(
            "SELECT COALESCE(SUM(purchase_price), 0) FROM items WHERE status IN ('purchased', 'in_stock', 'listed')"
        ).fetchone()[0]

        # Sales totals
        total_revenue = conn.execute(
            "SELECT COALESCE(SUM(sale_price), 0) FROM sale_records"
        ).fetchone()[0]
        total_cost = conn.execute(
            "SELECT COALESCE(SUM(purchase_price), 0) FROM items i JOIN sale_records sr ON i.id = sr.item_id"
        ).fetchone()[0]
        total_fees = conn.execute(
            "SELECT COALESCE(SUM(platform_fee + shipping_cost + other_cost), 0) FROM sale_records"
        ).fetchone()[0]
        total_profit = conn.execute(
            "SELECT COALESCE(SUM(net_profit), 0) FROM sale_records"
        ).fetchone()[0]

        # This month
        now = datetime.now()
        month_start = now.strftime("%Y-%m-01")
        month_profit = conn.execute(
            "SELECT COALESCE(SUM(net_profit), 0) FROM sale_records WHERE sale_date >= ?",
            (month_start,),
        ).fetchone()[0]
        month_revenue = conn.execute(
            "SELECT COALESCE(SUM(sale_price), 0) FROM sale_records WHERE sale_date >= ?",
            (month_start,),
        ).fetchone()[0]

        # Pending settlement
        pending = conn.execute(
            "SELECT COALESCE(SUM(sale_price), 0) FROM sale_records WHERE settled = FALSE"
        ).fetchone()[0]

        # Recent activity
        recent = conn.execute(
            "SELECT sh.*, i.name as item_name, i.sku "
            "FROM status_history sh JOIN items i ON sh.item_id = i.id "
            "ORDER BY sh.changed_at DESC LIMIT 10"
        ).fetchall()

        return {
            "status_counts": status_counts,
            "inventory_value": inventory_value,
            "total_revenue": total_revenue,
            "total_cost": total_cost,
            "total_fees": total_fees,
            "total_profit": total_profit,
            "profit_margin": round(total_profit / total_revenue * 100, 1) if total_revenue > 0 else 0,
            "month_profit": month_profit,
            "month_revenue": month_revenue,
            "pending_settlement": pending,
            "recent_activity": [row_to_dict(r) for r in recent],
        }
    finally:
        conn.close()


@app.get("/api/dashboard/profit")
async def profit_report(platform: str | None = None):
    conn = get_connection()
    try:
        where = " WHERE sr.sale_platform = ?" if platform else ""
        params = [platform] if platform else []

        rows = conn.execute(
            f"SELECT sr.sale_platform, COUNT(*) as count, "
            f"SUM(sr.sale_price) as revenue, "
            f"SUM(i.purchase_price) as cost, "
            f"SUM(sr.platform_fee + sr.shipping_cost + sr.other_cost) as fees, "
            f"SUM(sr.net_profit) as profit "
            f"FROM sale_records sr JOIN items i ON sr.item_id = i.id "
            f"{where} GROUP BY sr.sale_platform ORDER BY profit DESC",
            params,
        ).fetchall()

        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/dashboard/profit/monthly")
async def monthly_profit(months: int = 6):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT TO_CHAR(sale_date, 'YYYY-MM') as month, "
            "COUNT(*) as count, "
            "SUM(sale_price) as revenue, "
            "SUM(net_profit) as profit "
            "FROM sale_records GROUP BY month ORDER BY month DESC LIMIT ?",
            (months,),
        ).fetchall()

        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ── Settings API ────────────────────────────────────────
@app.get("/api/settings")
async def get_settings():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


@app.patch("/api/settings")
async def update_settings(update: SettingsUpdate):
    conn = get_connection()
    try:
        for k, v in update.settings.items():
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (k, v),
            )
        conn.commit()
        return {"status": "updated"}
    finally:
        conn.close()


@app.get("/api/statuses")
async def get_statuses():
    """Return valid statuses with labels."""
    return [{
        "code": s,
        "label": STATUS_LABELS.get(s, s),
    } for s in VALID_STATUSES]

# ── Scraper DB Config (from env) ────────────────────────
def get_mercari_pg_conn():
    """Get psycopg2 connection to mercari-hunter DB."""
    import psycopg2
    from db import get_mercari_db_config
    db = get_mercari_db_config()
    if not db.get("password"):
        raise HTTPException(503, "Mercari hunter not configured (set MERCARI_DB_PASSWORD)")
    try:
        return psycopg2.connect(**db, connect_timeout=5)
    except Exception as e:
        raise HTTPException(503, f"Mercari DB connection failed: {e}")


def get_amazon_pg_conn():
    """Get psycopg2 connection to amazon-outlet-hunter DB."""
    import psycopg2
    from db import get_amazon_db_config
    db = get_amazon_db_config()
    if not db.get("password"):
        raise HTTPException(503, "Amazon outlet hunter not configured (set AMAZON_DB_PASSWORD)")
    try:
        return psycopg2.connect(**db, connect_timeout=5)
    except Exception as e:
        raise HTTPException(503, f"Amazon DB connection failed: {e}")


# ── Scraper Discovery API ──────────────────────────────
@app.get("/api/scrapers/sources")
async def scraper_sources():
    """Return configured scraper sources."""
    cfg = _load_scraper_config()
    sources = []
    if cfg.get("mercari_hunter"):
        sources.append({
            "id": "mercari",
            "name": "Mercari Hunter",
            "configured": True,
        })
    if cfg.get("amazon_outlet_hunter"):
        sources.append({
            "id": "amazon_outlet",
            "name": "Amazon Hunter",
            "configured": True,
        })
    return {"sources": sources}


@app.get("/api/scrapers/mercari/items")
async def mercari_items(
    search: str | None = Query(None),
    price_min: int | None = Query(None),
    price_max: int | None = Query(None),
    brand: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
):
    """Browse mercari-hunter items for inventory import."""
    conn = get_mercari_pg_conn()
    try:
        cur = conn.cursor()
        where = []
        params = []
        if search:
            where.append("(name ILIKE %s OR description ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        if price_min is not None:
            where.append("price >= %s")
            params.append(price_min)
        if price_max is not None:
            where.append("price <= %s")
            params.append(price_max)
        if brand:
            where.append("brand ILIKE %s")
            params.append(f"%{brand}%")
        where_sql = " AND ".join(where)
        where_sql = f"WHERE {where_sql}" if where_sql else ""
        offset = (page - 1) * per_page

        cur.execute(f"""
            SELECT id, mercari_id, name, price, url, image_url, brand, model,
                   category, condition, seller_username, listed_at, crawled_at, is_flagged
            FROM items {where_sql}
            ORDER BY crawled_at DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]

        cur.execute(f"SELECT COUNT(*) FROM items {where_sql}", params)
        total = cur.fetchone()[0]

        return {
            "items": [dict(zip(cols, row)) for row in rows],
            "total": total,
            "page": page,
        }
    finally:
        conn.close()


@app.get("/api/scrapers/amazon/items")
async def amazon_items(
    search: str | None = Query(None),
    price_min: int | None = Query(None),
    price_max: int | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
):
    """Browse amazon-outlet-hunter items for inventory import."""
    conn = get_amazon_pg_conn()
    try:
        cur = conn.cursor()
        where = []
        params = []
        if search:
            where.append("title ILIKE %s")
            params.append(f"%{search}%")
        if price_min is not None:
            where.append("price >= %s")
            params.append(price_min)
        if price_max is not None:
            where.append("price <= %s")
            params.append(price_max)
        where_sql = " AND ".join(where)
        where_sql = f"WHERE {where_sql}" if where_sql else ""
        offset = (page - 1) * per_page

        cur.execute(f"""
            SELECT asin, title, price, original_price, discount_percent, url,
                   image_url, category, in_stock, first_seen, last_seen
            FROM items {where_sql}
            ORDER BY last_seen DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]

        cur.execute(f"SELECT COUNT(*) FROM items {where_sql}", params)
        total = cur.fetchone()[0]

        return {
            "items": [dict(zip(cols, row)) for row in rows],
            "total": total,
            "page": page,
        }
    finally:
        conn.close()


@app.post("/api/scrapers/mercari/items/{item_id}/import")
async def import_mercari_item(item_id: int):
    """Import a mercari-hunter item into inventory."""
    conn = get_mercari_pg_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT name, price, url, image_url, source_url, brand, model,
                   category, condition, description, seller_username, listed_at
            FROM items WHERE id = %s
        """, (item_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Item not found in mercari-hunter")

        cols = [desc[0] for desc in cur.description]
        data = dict(zip(cols, row))
    finally:
        conn.close()

    # Create inventory item
    inv_conn = get_connection()
    try:
        sku = generate_sku()
        tags = []
        if data.get("brand"):
            tags.append(data["brand"])
        if data.get("category"):
            tags.append(data["category"])
        tags_json = dict_to_json(tags)

        cursor = inv_conn.execute(
            "INSERT INTO items (sku, name, description, source_platform, source_item_id, "
            "purchase_price, purchase_date, image_url, source_url, location_id, status, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sku, data["name"], data.get("description") or "",
             "mercari", str(data.get("seller_username") or ""),
             data["price"], data.get("listed_at") or datetime.now().strftime("%Y-%m-%d"),
             data.get("image_url"), data.get("url"), None,
             "purchased", tags_json),
        )
        inv_conn.execute(
            "INSERT INTO status_history (item_id, from_status, to_status, note) "
            "VALUES (?, NULL, 'purchased', 'Mercari Hunter からインポート')",
            (cursor.lastrowid,),
        )
        inv_conn.commit()
        return {"id": cursor.lastrowid, "sku": sku, "status": "imported"}
    finally:
        inv_conn.close()


@app.post("/api/scrapers/amazon/items/{asin}/import")
async def import_amazon_item(asin: str):
    """Import an amazon-outlet-hunter item into inventory."""
    conn = get_amazon_pg_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT title, price, original_price, discount_percent, url, image_url, category
            FROM items WHERE asin = %s
        """, (asin,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Item not found in amazon-outlet-hunter")

        cols = [desc[0] for desc in cur.description]
        data = dict(zip(cols, row))
    finally:
        conn.close()

    desc = ""
    if data.get("category"):
        desc = f"カテゴリ: {data['category']}"
    if data.get("discount_percent"):
        desc += f" | 割引: {data['discount_percent']}%"

    inv_conn = get_connection()
    try:
        sku = generate_sku()
        tags = []
        if data.get("category"):
            tags.append(data["category"])
        tags_json = dict_to_json(tags)

        cursor = inv_conn.execute(
            "INSERT INTO items (sku, name, description, source_platform, source_item_id, "
            "purchase_price, purchase_date, image_url, source_url, location_id, status, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sku, data["title"], desc,
             "amazon_outlet", asin,
             data["price"], datetime.now().strftime("%Y-%m-%d"),
             data.get("image_url"), data.get("url"), None,
             "purchased", tags_json),
        )
        inv_conn.execute(
            "INSERT INTO status_history (item_id, from_status, to_status, note) "
            "VALUES (?, NULL, 'purchased', 'Amazon Hunter からインポート')",
            (cursor.lastrowid,),
        )
        inv_conn.commit()
        return {"id": cursor.lastrowid, "sku": sku, "status": "imported"}
    finally:
        inv_conn.close()


# ── Frontend ────────────────────────────────────────────
@app.get("/")
async def index():
    # Try both __file__-relative and cwd-relative paths
    for base in [Path(__file__).parent, Path.cwd()]:
        html_path = base / "static" / "index.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>Inventory Manager</h1><p>Frontend not found.</p>")


# ── Main ────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn as uv
    uv.run(app, host="0.0.0.0", port=8000)
