# yookassa.py
import uuid
import requests
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_RETURN_URL
import os
from database.db import get_connection
from datetime import datetime


YOOKASSA_API = "https://api.yookassa.ru/v3/payments"
TEST_API_URL = os.getenv("TEST_API_URL")
ENV = os.getenv("ENV")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_TEST_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_TEST_SECRET_KEY")

def _create_payment_test(slot_id: int, user_id: int, amount: int, description: str):
    resp = requests.post(
        f"{TEST_API_URL}/api/create_payment",
        json={
            "slot_id": slot_id,
            "user_id": user_id,
            "amount": amount,
            "description": description
        },
        timeout=10
    )

    resp.raise_for_status()
    return resp.json()


def _create_payment_prod(slot_id: int, user_id: int, amount: int, description: str):
    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL
        },
        "capture": True,
        "description": description,
        "metadata": {
            "slot_id": str(slot_id)
        },
        "payment_method_data": {
            "type": "bank_card"
        }
    }

    headers = {
        "Idempotence-Key": str(uuid.uuid4())
    }

    r = requests.post(
        YOOKASSA_API,
        json=payload,
        auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        headers=headers,
        timeout=15
    )
    r.raise_for_status()
    payment = r.json()

    payment_id = payment["id"]

    # ✅ ОБЯЗАТЕЛЬНО: сохраняем в БД
    with get_connection() as conn:
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

    return {
        "payment_id": payment_id,
        "confirmation_url": payment["confirmation"]["confirmation_url"]
    }


#def create_payment(slot_id: int, user_id: int, amount: int, description: str):
#    if ENV == "TEST":
#        return _create_payment_test(slot_id, user_id, amount, description)
#
#    if ENV == "PROD":
#        return _create_payment_prod(slot_id, user_id, amount, description)
#
#    raise RuntimeError(f"Unknown ENV={ENV}")

def create_payment(*, slot_id: int, user_id: int, amount: int, description: str):
    resp = requests.post(
        f"{TEST_API_URL}/api/create_payment",
        json={
            "slot_id": slot_id,
            "user_id": user_id,
            "amount": amount,
            "description": description
        },
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()