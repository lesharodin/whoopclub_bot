from fastapi import FastAPI, Query, HTTPException, Request
import sqlite3
from datetime import datetime
import os
import uuid
import hmac
import hashlib
import json
import requests
from requests.auth import HTTPBasicAuth
YOOKASSA_API = "https://api.yookassa.ru/v3/payments"
SHOP_ID = os.getenv("YOOKASSA_TEST_SHOP_ID")
SECRET_KEY = os.getenv("YOOKASSA_TEST_SECRET_KEY")
RETURN_URL = os.getenv("YOOKASSA_TEST_RETURN_URL")


YOOKASSA_WEBHOOK_SECRET = os.getenv("YOOKASSA_WEBHOOK_SECRET")

app = FastAPI()

@app.get("/api/participants_by_date")
def get_participants_by_date(date: str = Query(..., description="Формат DD.MM.YYYY")):
    try:
        date_obj = datetime.strptime(date, "%d.%m.%Y")
        iso_prefix = date_obj.strftime("%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты. Используйте DD.MM.YYYY")

    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "test.db"))
    cursor = conn.cursor()

    # Найти ID тренировки
    cursor.execute("""
        SELECT id FROM trainings WHERE date LIKE ? AND  status != 'cancelled' LIMIT 1
    """, (f"{iso_prefix}%",))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    training_id = row[0]

    # Получить пилотов и каналы
    cursor.execute("""
        SELECT u.nickname, s.group_name, s.channel
        FROM slots s
        JOIN users u ON u.user_id = s.user_id
        WHERE s.training_id = ? AND s.status = 'confirmed'
    """, (training_id,))

    def map_group_to_heat(group_name: str) -> str:
        if group_name.lower() == "fast":
            return "Группа 1"
        elif group_name.lower() == "standard":
            return "Группа 2"
        else:
            return "Группа 3"

    return [
        {
            "name": nickname,
            "callsign": nickname,
            "group": group,
            "heat": map_group_to_heat(group),
            "channel": channel
        }
        for nickname, group, channel in cursor.fetchall()
    ]

@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    data = await request.json()

    print("=== YOOKASSA WEBHOOK RECEIVED ===")
    print(data)

    if data.get("event") != "payment.succeeded":
        return {"ok": True}

    payment = data["object"]
    payment_id = payment["id"]
    metadata = payment.get("metadata", {})

    slot_id = int(metadata.get("slot_id"))

    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "test.db"))
    cursor = conn.cursor()

    # 1️⃣ Проверяем, есть ли платёж и не обработан ли он
    cursor.execute("""
        SELECT status FROM payments
        WHERE yookassa_payment_id = ?
    """, (payment_id,))
    row = cursor.fetchone()

    if not row:
        print(f"[YOOKASSA] payment {payment_id} not found")
        conn.close()
        return {"ok": True}

    if row[0] == "succeeded":
        print(f"[YOOKASSA] payment {payment_id} already processed")
        conn.close()
        return {"ok": True}

    # 2️⃣ Обновляем платёж
    cursor.execute("""
        UPDATE payments
        SET status = 'succeeded',
            paid_at = ?
        WHERE yookassa_payment_id = ?
    """, (datetime.now().isoformat(), payment_id))

    # 3️⃣ Подтверждаем слот
    cursor.execute("""
        UPDATE slots
        SET status = 'confirmed'
        WHERE id = ?
    """, (slot_id,))

    conn.commit()
    conn.close()

    print(f"[YOOKASSA] slot {slot_id} confirmed")

    return {"ok": True}


@app.get("/api/slot_status/{slot_id}")
def get_slot_status(slot_id: int):
    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "test.db"))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT status FROM slots WHERE id = ?
    """, (slot_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Slot not found")

    return {
        "slot_id": slot_id,
        "status": row[0]
    }

@app.post("/api/create_payment")
async def create_payment_api(payload: dict):
    slot_id = int(payload["slot_id"])
    user_id = int(payload["user_id"])
    amount = int(payload["amount"])
    description = payload.get("description", "Оплата тренировки WhoopClub (TEST)")

    payment = create_yookassa_payment(
        slot_id=slot_id,
        amount=amount,
        description=description
    )

    payment_id = payment["id"]

    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "test.db"))
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payments (
            slot_id,
            user_id,
            yookassa_payment_id,
            amount,
            payment_method,
            status,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        slot_id,
        user_id,
        payment_id,
        amount,
        "yookassa",
        "pending",
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

    return {
        "id": payment_id,
        "confirmation": payment["confirmation"]
    }
@app.get("/api/payment_status/{payment_id}")
def payment_status(payment_id: str):
    conn = sqlite3.connect(os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "database",
        "test.db"
    ))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT status
        FROM payments
        WHERE yookassa_payment_id = ?
    """, (payment_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"exists": False}

    return {
        "exists": True,
        "status": row[0],
        "paid": row[0] == "succeeded"
    }


def create_yookassa_payment(slot_id: int, amount: int, description: str):
    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": RETURN_URL
        },
        "payment_method_data": {
            "type": "bank_card"
        },
        "description": description,
        "metadata": {
            "slot_id": str(slot_id)
        }
    }

    headers = {
        "Idempotence-Key": str(uuid.uuid4()),
        "Content-Type": "application/json"
    }

    response = requests.post(
        YOOKASSA_API,
        json=payload,
        headers=headers,
        auth=HTTPBasicAuth(SHOP_ID, SECRET_KEY),
        timeout=10
    )

    response.raise_for_status()
    return response.json()