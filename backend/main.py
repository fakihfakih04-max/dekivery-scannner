import os
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv("DATABASE_URL", "")

app = FastAPI(title="Delivery Scanner API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class OrderIn(BaseModel):
    customer_name: str = ""
    phone: str = ""
    order_amount: Decimal = Field(default=Decimal("0"), ge=0)
    delivery_fee: Decimal = Field(default=Decimal("0"), ge=0)
    delivery_payer: str = "customer"
    payment_status: str = "cod"
    paid_amount: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str = ""
    status: str = "active"
    client_time: Optional[int] = None
    photo_data: Optional[str] = None

class StorePaymentIn(BaseModel):
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str = ""
    client_time: Optional[int] = None


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


def ensure_schema():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id BIGSERIAL PRIMARY KEY,
                    customer_name TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    order_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                    delivery_fee NUMERIC(12,2) NOT NULL DEFAULT 0,
                    delivery_payer TEXT NOT NULL DEFAULT 'customer',
                    payment_status TEXT NOT NULL DEFAULT 'cod',
                    paid_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                    remaining_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                    collect_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS photo_data TEXT")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(phone)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS store_payments (
                    id BIGSERIAL PRIMARY KEY,
                    amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()


@app.on_event("startup")
def startup():
    ensure_schema()


@app.get("/")
def root():
    return {"ok": True, "service": "Delivery Scanner API", "version": "2.0.0"}


@app.get("/health")
def health():
    try:
        ensure_schema()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"ok": True, "database": "connected"}
    except Exception as e:
        return {"ok": False, "database": "error", "detail": str(e)}


@app.get("/orders")
def list_orders():
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, customer_name, phone, order_amount, delivery_fee,
                       delivery_payer, payment_status, paid_amount,
                       remaining_amount, collect_amount, notes, status,
                       photo_data, created_at, updated_at
                FROM orders
                ORDER BY created_at DESC, id DESC
            """)
            return [row_to_json(r) for r in cur.fetchall()]


def validate_order(order: OrderIn):
    if order.delivery_payer not in {"customer", "store", "already_paid"}:
        raise HTTPException(400, "Invalid delivery_payer")
    if order.payment_status not in {"paid", "partial", "cod"}:
        raise HTTPException(400, "Invalid payment_status")


def calculated(order: OrderIn):
    delivery_due = Decimal("0") if order.delivery_payer in {"store", "already_paid"} else order.delivery_fee
    total_due = order.order_amount + delivery_due
    paid = min(order.paid_amount, total_due)
    remaining = max(total_due - paid, Decimal("0"))
    return paid, remaining


@app.post("/orders")
def create_order(order: OrderIn):
    validate_order(order)
    paid, remaining = calculated(order)
    created = datetime.fromtimestamp(order.client_time / 1000, tz=timezone.utc) if order.client_time else datetime.now(timezone.utc)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO orders
                (customer_name, phone, order_amount, delivery_fee, delivery_payer,
                 payment_status, paid_amount, remaining_amount, collect_amount,
                 notes, status, photo_data, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                RETURNING *
            """, (order.customer_name, order.phone, order.order_amount, order.delivery_fee,
                  order.delivery_payer, order.payment_status, paid, remaining, remaining,
                  order.notes, order.status, order.photo_data, created))
            row = cur.fetchone()
        conn.commit()
    return row_to_json(row)


@app.put("/orders/{order_id}")
def update_order(order_id: int, order: OrderIn):
    validate_order(order)
    paid, remaining = calculated(order)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE orders SET
                    customer_name=%s, phone=%s, order_amount=%s, delivery_fee=%s,
                    delivery_payer=%s, payment_status=%s, paid_amount=%s,
                    remaining_amount=%s, collect_amount=%s, notes=%s,
                    status=%s, photo_data=COALESCE(%s, photo_data), updated_at=NOW()
                WHERE id=%s RETURNING *
            """, (order.customer_name, order.phone, order.order_amount, order.delivery_fee,
                  order.delivery_payer, order.payment_status, paid, remaining, remaining,
                  order.notes, order.status, order.photo_data, order_id))
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


@app.get("/store-statement")
def store_statement(
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
):
    ensure_schema()
    where = ["delivery_payer='store'", "status!='cancelled'"]
    params = []
    if from_date:
        where.append("created_at >= %s::date")
        params.append(from_date)
    if to_date:
        where.append("created_at < (%s::date + INTERVAL '1 day')")
        params.append(to_date)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""
                SELECT id, customer_name, phone, order_amount, delivery_fee,
                       delivery_payer, payment_status, paid_amount, remaining_amount,
                       created_at, notes
                FROM orders WHERE {' AND '.join(where)}
                ORDER BY created_at DESC, id DESC
            """, params)
            rows = [row_to_json(r) for r in cur.fetchall()]
            pay_where = []
            pay_params = []
            if from_date:
                pay_where.append("created_at >= %s::date")
                pay_params.append(from_date)
            if to_date:
                pay_where.append("created_at < (%s::date + INTERVAL '1 day')")
                pay_params.append(to_date)
            q = "SELECT COALESCE(SUM(amount),0) AS total FROM store_payments"
            if pay_where:
                q += " WHERE " + " AND ".join(pay_where)
            cur.execute(q, pay_params)
            total_payments = row_to_json(cur.fetchone())["total"]
    total_delivery = round(sum(float(r["delivery_fee"] or 0) for r in rows), 2)
    balance = round(total_delivery - float(total_payments or 0), 2)
    return {"rows": rows, "delivery_total": total_delivery, "store_payments_total": total_payments, "balance": balance}


@app.post("/store-payments")
def add_store_payment(payment: StorePaymentIn):
    created = datetime.fromtimestamp(payment.client_time / 1000, tz=timezone.utc) if payment.client_time else datetime.now(timezone.utc)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("INSERT INTO store_payments(amount,notes,created_at) VALUES (%s,%s,%s) RETURNING *",
                        (payment.amount, payment.notes, created))
            row = cur.fetchone()
        conn.commit()
    return row_to_json(row)
