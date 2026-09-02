
import os
from decimal import Decimal
from datetime import datetime
from typing import Optional
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv("DATABASE_URL", "")

app = FastAPI(title="Delivery Scanner API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock this down to your APK/Desktop domains in production.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    customer_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    order_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    delivery_fee NUMERIC(12,2) NOT NULL DEFAULT 0,
    delivery_payer TEXT NOT NULL DEFAULT 'customer' CHECK (delivery_payer IN ('customer','store','already_paid')),
    payment_status TEXT NOT NULL DEFAULT 'cod' CHECK (payment_status IN ('paid','partial','cod')),
    paid_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    remaining_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    collect_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(phone);
"""

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(DB_SCHEMA)
        conn.commit()

@app.on_event("startup")
def startup():
    init_db()

class OrderIn(BaseModel):
    customer_name: str = ""
    phone: str = ""
    order_amount: Decimal = Field(default=Decimal("0"), ge=0)
    delivery_fee: Decimal = Field(default=Decimal("0"), ge=0)
    delivery_payer: str = "customer"  # customer | store | already_paid
    payment_status: str = "cod"        # paid | partial | cod
    paid_amount: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str = ""
    status: str = "active"             # active | cancelled
    client_time: Optional[int] = None   # original local timestamp in milliseconds

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(DATABASE_URL)

def row_to_json(row):
    if not row:
        return None
    d = dict(row)
    for k, v in list(d.items()):
        if isinstance(v, Decimal):
            d[k] = float(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
    return d

@app.get("/")
def root():
    return {"ok": True, "service": "Delivery Scanner API"}

@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"ok": True, "database": "connected"}
    except Exception as e:
        return {"ok": False, "database": "error", "detail": str(e)}

@app.get("/orders")
def list_orders():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, customer_name, phone, order_amount, delivery_fee,
                       delivery_payer, payment_status, paid_amount,
                       remaining_amount, collect_amount, notes, status,
                       created_at, updated_at
                FROM orders
                ORDER BY id DESC
            """)
            return [row_to_json(r) for r in cur.fetchall()]

@app.post("/orders")
def create_order(order: OrderIn):
    if order.delivery_payer not in {"customer", "store", "already_paid"}:
        raise HTTPException(400, "Invalid delivery_payer")
    if order.payment_status not in {"paid", "partial", "cod"}:
        raise HTTPException(400, "Invalid payment_status")

    # Customer pays delivery unless store covers it or it was already paid.
    delivery_due = Decimal("0") if order.delivery_payer in {"store", "already_paid"} else order.delivery_fee
    total_due = order.order_amount + delivery_due
    paid = min(order.paid_amount, total_due)
    remaining = max(total_due - paid, Decimal("0"))

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO orders
                (customer_name, phone, order_amount, delivery_fee, delivery_payer,
                 payment_status, paid_amount, remaining_amount, collect_amount,
                 notes, status, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
            """, (
                order.customer_name, order.phone, order.order_amount,
                order.delivery_fee, order.delivery_payer, order.payment_status,
                paid, remaining, remaining, order.notes, order.status,
                datetime.fromtimestamp(order.client_time / 1000, tz=timezone.utc) if order.client_time else datetime.now(timezone.utc)
            ))
            row = cur.fetchone()
        conn.commit()
    return row_to_json(row)

@app.put("/orders/{order_id}")
def update_order(order_id: int, order: OrderIn):
    delivery_due = Decimal("0") if order.delivery_payer in {"store", "already_paid"} else order.delivery_fee
    total_due = order.order_amount + delivery_due
    paid = min(order.paid_amount, total_due)
    remaining = max(total_due - paid, Decimal("0"))

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE orders SET
                    customer_name=%s, phone=%s, order_amount=%s, delivery_fee=%s,
                    delivery_payer=%s, payment_status=%s, paid_amount=%s,
                    remaining_amount=%s, collect_amount=%s, notes=%s,
                    status=%s, updated_at=NOW()
                WHERE id=%s
                RETURNING *
            """, (
                order.customer_name, order.phone, order.order_amount,
                order.delivery_fee, order.delivery_payer, order.payment_status,
                paid, remaining, remaining, order.notes, order.status, order_id
            ))
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(404, "Order not found")
    return row_to_json(row)

@app.delete("/orders/{order_id}")
def delete_order(order_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM orders WHERE id=%s", (order_id,))
            deleted = cur.rowcount
        conn.commit()
    if not deleted:
        raise HTTPException(404, "Order not found")
    return {"ok": True, "deleted_id": order_id}
