import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(title="Delivery Scanner API")

DATABASE_URL = os.getenv("DATABASE_URL", "")

def conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(DATABASE_URL)

class OrderIn(BaseModel):
    customer_name: str = ""
    phone: str = ""
    order_amount: float = 0
    delivery_fee: float = 0
    delivery_payer: str = "customer"
    payment_status: str = "cod"
    paid_amount: float = 0
    remaining_amount: float = 0
    collect_amount: float = 0
    notes: str = ""
    status: str = "active"

@app.get("/health")
def health():
    if not DATABASE_URL:
        return {"ok": False, "message": "DATABASE_URL missing"}
    try:
        with conn() as c:
            with c.cursor() as cur:
                cur.execute("SELECT 1")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "message": str(e)}

@app.get("/orders")
def get_orders():
    try:
        with conn() as c:
            with c.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM orders ORDER BY id DESC")
                return cur.fetchall()
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/orders")
def create_order(order: OrderIn):
    try:
        with conn() as c:
            with c.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO orders
                    (customer_name, phone, order_amount, delivery_fee,
                     delivery_payer, payment_status, paid_amount,
                     remaining_amount, collect_amount, notes, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING *
                """, (
                    order.customer_name, order.phone, order.order_amount,
                    order.delivery_fee, order.delivery_payer,
                    order.payment_status, order.paid_amount,
                    order.remaining_amount, order.collect_amount,
                    order.notes, order.status
                ))
                row = cur.fetchone()
                c.commit()
                return row
    except Exception as e:
        raise HTTPException(500, str(e))

@app.put("/orders/{order_id}")
def update_order(order_id: int, order: OrderIn):
    try:
        with conn() as c:
            with c.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    UPDATE orders SET
                    customer_name=%s, phone=%s, order_amount=%s,
                    delivery_fee=%s, delivery_payer=%s,
                    payment_status=%s, paid_amount=%s,
                    remaining_amount=%s, collect_amount=%s,
                    notes=%s, status=%s, updated_at=NOW()
                    WHERE id=%s RETURNING *
                """, (
                    order.customer_name, order.phone, order.order_amount,
                    order.delivery_fee, order.delivery_payer,
                    order.payment_status, order.paid_amount,
                    order.remaining_amount, order.collect_amount,
                    order.notes, order.status, order_id
                ))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(404, "Order not found")
                c.commit()
                return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.delete("/orders/{order_id}")
def delete_order(order_id: int):
    try:
        with conn() as c:
            with c.cursor() as cur:
                cur.execute("DELETE FROM orders WHERE id=%s", (order_id,))
                if cur.rowcount == 0:
                    raise HTTPException(404, "Order not found")
                c.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
