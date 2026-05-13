#!/usr/bin/env python3
"""
Inventory Manager — Backend API
Reselling inventory management with profit tracking.
"""

import asyncio
import json
import os
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
    import uuid
    return f"INV-{uuid.uuid4().hex[:12].upper()}"


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
            where.append("(i.name LIKE ? OR i.description LIKE ?)")
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
            f"SELECT COUNT(*) FROM items i LEFT JOIN locations l ON i.location_id = l.id{where_sql}", params
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


# ── Mercari Cookie Storage ──────────────────────────────
# Cookie is stored in .env file as MERCARI_COOKIE=...
# This avoids storing sensitive data in the database.

_ENV_FILE = Path(__file__).parent / ".env"


def _read_env_value(key: str) -> str | None:
    """Read a value from .env file."""
    if not _ENV_FILE.exists():
        return None
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip("\"").strip("'")
    return None


def _write_env_value(key: str, value: str):
    """Write or update a value in .env file."""
    lines = []
    found = False
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            line_stripped = line.strip()
            if line_stripped.startswith("#") or "=" not in line_stripped:
                lines.append(line)
                continue
            k, _, _ = line_stripped.partition("=")
            if k.strip() == key:
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n")


def _remove_env_value(key: str):
    """Remove a key from .env file."""
    if not _ENV_FILE.exists():
        return
    lines = []
    for line in _ENV_FILE.read_text().splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("#") or "=" not in line_stripped:
            lines.append(line)
            continue
        k, _, _ = line_stripped.partition("=")
        if k.strip() != key:
            lines.append(line)
    _ENV_FILE.write_text("\n".join(lines) + "\n")


# ── Cookie Settings API ─────────────────────────────────
class CookieSaveRequest(BaseModel):
    cookie: str


@app.post("/api/settings/mercari-cookie")
async def save_mercari_cookie(req: CookieSaveRequest):
    """Save Mercari cookie to .env file."""
    cookie = req.cookie.strip()
    if not cookie:
        raise HTTPException(400, "Cookie が空です")
    _write_env_value("MERCARI_COOKIE", cookie)
    return {"status": "saved", "message": "Cookie を保存しました"}


@app.get("/api/settings/mercari-cookie/status")
async def get_mercari_cookie_status():
    """Check if Mercari cookie is set."""
    cookie = _read_env_value("MERCARI_COOKIE")
    has_cookie = bool(cookie)
    return {
        "has_cookie": has_cookie,
        "cookie_length": len(cookie) if cookie else 0,
    }


@app.delete("/api/settings/mercari-cookie")
async def delete_mercari_cookie():
    """Remove Mercari cookie from .env file."""
    _remove_env_value("MERCARI_COOKIE")
    return {"status": "deleted", "message": "Cookie を削除しました"}


# ── Mercari Owned Items Sync (Playwright) ───────────────
# Global sync state for polling
_sync_state: dict = {"running": False, "progress": "", "result": None, "error": None}


class MercariOwnedItem(BaseModel):
    name: str
    price: int
    status: str = ""
    url: str | None = None
    image_url: str | None = None


class MercariOwnedBatch(BaseModel):
    items: list[MercariOwnedItem]


def _save_items_to_db(items: list[MercariOwnedItem]) -> dict:
    """Core logic for syncing Mercari owned items into inventory DB."""
    conn = get_connection()
    try:
        created = 0
        updated = 0
        skipped = 0

        for item in items:
            name = item.name.strip()
            price = item.price
            status_text = item.status or ""
            source_url = item.url
            image_url = item.image_url
            # Normalize: /sell/inventory/ → /inventory/
            if source_url:
                source_url = source_url.replace('/sell/inventory/', '/inventory/')

            # Determine inventory status
            if "出品中" in status_text:
                inv_status = "listed"
            elif "出品する" in status_text:
                inv_status = "in_stock"
            else:
                inv_status = "in_stock"

            # Check if item already exists (by name + price + platform)
            existing = conn.execute(
                "SELECT id, status, source_url, image_url FROM items "
                "WHERE name = ? AND purchase_price = ? AND source_platform = 'mercari_owned'",
                (name, price),
            ).fetchone()

            if existing:
                # Update status, source_url, and image_url if changed
                needs_update = False
                updates = []
                if existing["status"] != inv_status:
                    updates.append("status = ?")
                    needs_update = True
                if source_url and (not existing["source_url"] or existing["source_url"] != source_url):
                    updates.append("source_url = ?")
                    needs_update = True
                if image_url and (not existing["image_url"] or existing["image_url"] != image_url):
                    updates.append("image_url = ?")
                    needs_update = True

                if needs_update:
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    update_values = []
                    if existing["status"] != inv_status:
                        update_values.append(inv_status)
                    if source_url and (not existing["source_url"] or existing["source_url"] != source_url):
                        update_values.append(source_url)
                    if image_url and (not existing["image_url"] or existing["image_url"] != image_url):
                        update_values.append(image_url)
                    update_values.append(existing["id"])
                    conn.execute(
                        f"UPDATE items SET {', '.join(updates)} WHERE id = ?",
                        update_values,
                    )
                    conn.commit()
                    updated += 1
                else:
                    skipped += 1
            else:
                # Create new item
                sku = generate_sku()
                tags_json = dict_to_json(["mercari_owned"])
                purchase_date = datetime.now().strftime("%Y-%m-%d")

                cursor = conn.execute(
                    "INSERT INTO items (sku, name, description, source_platform, source_item_id, "
                    "purchase_price, purchase_date, image_url, source_url, location_id, status, tags) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (sku, name, "", "mercari_owned", None,
                     price, purchase_date, image_url, source_url, None,
                     inv_status, tags_json),
                )

                conn.execute(
                    "INSERT INTO status_history (item_id, from_status, to_status, note) "
                    "VALUES (?, NULL, ?, 'Mercari持ち物同期')",
                    (cursor.lastrowid, inv_status),
                )
                conn.commit()
                created += 1

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "total": len(items),
        }
    finally:
        conn.close()


def _extract_items_from_page(page) -> list[MercariOwnedItem]:
    """Extract items from the Mercari inventory page using Playwright."""
    items = []

    # Get all item links
    item_links = page.query_selector_all('a[href*="/inventory/m"]')
    links = []
    for link in item_links:
        href = link.get_attribute("href")
        if href:
            links.append(href.replace('/sell/inventory/', '/inventory/'))
    links = list(dict.fromkeys(links))  # deduplicate preserving order

    # Get all image URLs
    all_imgs = page.query_selector_all('img')
    images = []
    for img in all_imgs:
        candidates = [
            img.get_attribute("src") or "",
            img.get_attribute("data-src") or "",
            img.get_attribute("data-lazy-src") or "",
            img.get_attribute("data-original") or "",
        ]
        for c in candidates:
            if c and not c.startswith("data:") and "/photos/m" in c and c not in images:
                images.append(c)

    # Get text content and parse items
    body_text = page.inner_text("body")
    lines = [l.strip() for l in body_text.split("\n") if l.strip()]

    link_idx = 0
    img_idx = 0

    for i in range(len(lines) - 3):
        if lines[i + 1] == "¥":
            name = lines[i].strip()
            price_str = lines[i + 2].strip()
            status = lines[i + 3].strip()

            try:
                price = int(price_str.replace(",", ""))
            except ValueError:
                continue

            url = links[link_idx] if link_idx < len(links) else None
            image_url = images[img_idx] if img_idx < len(images) else None

            if len(name) >= 2 and price > 0 and status:
                items.append(MercariOwnedItem(
                    name=name, price=price, status=status,
                    url=url, image_url=image_url
                ))
                link_idx += 1
                img_idx += 1
                i += 3

    return items


def _run_playwright_sync() -> dict:
    """Run the Playwright sync in a synchronous function (called from async task)."""
    from playwright.sync_api import sync_playwright

    cookie = _read_env_value("MERCARI_COOKIE")
    if not cookie:
        return {"error": "Mercari Cookie が設定されていません。まず Cookie を入力してください。"}

    _sync_state["running"] = True
    _sync_state["progress"] = "ブラウザを起動中..."
    _sync_state["error"] = None
    _sync_state["result"] = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )

            # Parse and set cookies
            _sync_state["progress"] = "Cookie を設定中..."
            # Cookie can be a single string or multiple key=value pairs
            cookie_pairs = []
            for part in cookie.split(";"):
                part = part.strip()
                if "=" in part:
                    k, _, v = part.partition("=")
                    cookie_pairs.append({"name": k.strip(), "value": v.strip(), "domain": ".mercari.com"})

            context.add_cookies(cookie_pairs)

            # Navigate to inventory page
            _sync_state["progress"] = "Mercari 持ち物一覧にアクセス中..."
            page = context.new_page()
            page.goto("https://jp.mercari.com/mypage/inventory", wait_until="networkidle", timeout=30000)

            # Wait for content to load (SPA might need extra time)
            _sync_state["progress"] = "ページ内容を読み込み中..."
            page.wait_for_timeout(3000)

            # Try scrolling to load more items if there's a scrollbar
            _sync_state["progress"] = "すべての商品を読み込み中..."
            for _ in range(5):
                page.evaluate("window.scrollBy(0, 500)")
                page.wait_for_timeout(800)

            # Extract items
            _sync_state["progress"] = "商品データを抽出中..."
            items = _extract_items_from_page(page)
            browser.close()

            if not items:
                return {"error": "商品が見つかりませんでした。Mercari 持ち物一覧ページにログインしているか確認してください。"}

            _sync_state["progress"] = f"{len(items)} 件の商品が見つかりました。データベースに保存中..."

            # Save to DB
            result = _save_items_to_db(items)
            _sync_state["result"] = result
            return result

    except Exception as e:
        error_msg = f"同期に失敗しました: {str(e)}"
        _sync_state["error"] = error_msg
        return {"error": error_msg}
    finally:
        _sync_state["running"] = False


@app.post("/api/scrapers/mercari/owned/sync")
async def trigger_mercari_sync():
    """Trigger server-side Mercari owned items sync using Playwright with stored cookie."""
    if _sync_state["running"]:
        return {
            "status": "running",
            "progress": _sync_state["progress"],
            "message": "すでに同期が実行中です",
        }

    # Run sync in background task
    asyncio.create_task(_async_sync_wrapper())
    return {
        "status": "started",
        "message": "同期を開始しました",
    }


async def _async_sync_wrapper():
    """Wrapper to run synchronous Playwright code in a thread pool."""
    import concurrent.futures
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, _run_playwright_sync)
    # Store result for polling
    if "error" in result and result["error"]:
        _sync_state["result"] = result


@app.get("/api/scrapers/mercari/owned/status")
async def mercari_owned_sync_status():
    """Return sync status for polling or last sync info."""
    conn = get_connection()
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM items WHERE source_platform = 'mercari_owned'"
        ).fetchone()[0]
        last_sync = conn.execute(
            "SELECT MAX(updated_at) FROM items WHERE source_platform = 'mercari_owned'"
        ).fetchone()[0]
    finally:
        conn.close()

    return {
        "total_synced": total,
        "last_sync_at": last_sync,
        "sync_running": _sync_state["running"],
        "sync_progress": _sync_state["progress"],
        "sync_result": _sync_state.get("result"),
        "sync_error": _sync_state.get("error"),
    }


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
