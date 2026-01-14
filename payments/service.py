import sqlite3
import uuid
import requests
from datetime import datetime
from requests.auth import HTTPBasicAuth
import os
from logging_config import logger

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "database",
    "bot.db"
)


def create_payment(
    *,
    user_id: int,
    amount: int,
    target_type: str,
    target_id: int,
    chat_id: int,
    message_id: int,
    payment_method: str = "bank_card",
    description: str | None = None,
) -> str:
    """
    Создаёт платёж в Юкассе и запись в payments.
    UI-данные (chat_id, message_id) сохраняются сразу.
    """

    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1️⃣ создаём payment у себя
    cursor.execute("""
        INSERT INTO payments (
            user_id,
            amount,
            currency,
            payment_method,
            status,
            target_type,
            target_id,
            chat_id,
            message_id,
            ui_status,
            created_at
        )
        VALUES (?, ?, 'RUB', ?, 'pending', ?, ?, ?, ?, 'shown', ?)
    """, (
        user_id,
        amount,
        payment_method,
        target_type,
        target_id,
        chat_id,
        message_id,
        now
    ))

    payment_id = cursor.lastrowid
    conn.commit()

    # 2️⃣ payload для Юкассы
    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": "https://whoopclub.ru/payment/success"
        },
        "description": description or f"Оплата {target_type}",
        "metadata": {
            "payment_id": str(payment_id)
        }
    }

    if payment_method == "sbp":
        payload["payment_method_data"] = {"type": "sbp"}
    else:
        payload["payment_method_data"] = {"type": "bank_card"}

    headers = {
        "Idempotence-Key": str(uuid.uuid4()),
        "Content-Type": "application/json"
    }

    # 3️⃣ запрос в Юкассу
    response = requests.post(
        YOOKASSA_API_URL,
        json=payload,
        headers=headers,
        auth=HTTPBasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        timeout=10
    )

    if response.status_code not in (200, 201):
        cursor.execute("""
            UPDATE payments
            SET status = 'canceled'
            WHERE id = ?
        """, (payment_id,))
        conn.commit()
        conn.close()

        raise RuntimeError(
            f"YooKassa error {response.status_code}: {response.text}"
        )

    data = response.json()

    # 4️⃣ сохраняем yookassa_payment_id
    cursor.execute("""
        UPDATE payments
        SET yookassa_payment_id = ?
        WHERE id = ?
    """, (
        data["id"],
        payment_id
    ))

    conn.commit()
    conn.close()

    return data["confirmation"]["confirmation_url"]


def apply_payment(payment: dict):
    """
    Применяет успешный платёж к бизнес-логике.
    payment — dict / sqlite3.Row из таблицы payments
    """

    if payment["status"] != "succeeded":
        logger.warning(
            f"[apply_payment] payment {payment['id']} has status {payment['status']}"
        )
        return

    target_type = payment["target_type"]
    target_id = payment["target_id"]

    if target_type == "slot":
        confirm_slot(target_id)

    elif target_type == "subscription":
        activate_subscription(target_id)

    else:
        logger.warning(
            f"[apply_payment] unknown target_type: {target_type}"
        )

def confirm_slot(slot_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1️⃣ проверяем слот
    cursor.execute("""
        SELECT status
        FROM slots
        WHERE id = ?
    """, (slot_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        logger.error(f"[confirm_slot] slot {slot_id} not found")
        return

    if row[0] == "confirmed":
        # идемпотентность
        conn.close()
        return

    # 2️⃣ подтверждаем
    cursor.execute("""
        UPDATE slots
        SET status = 'confirmed'
        WHERE id = ?
    """, (slot_id,))

    conn.commit()
    conn.close()

    logger.info(f"[confirm_slot] slot {slot_id} confirmed")


def activate_subscription(subscription_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1️⃣ получаем подписку
    cursor.execute("""
        SELECT user_id, count, status
        FROM subscriptions
        WHERE id = ?
    """, (subscription_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        logger.error(
            f"[activate_subscription] subscription {subscription_id} not found"
        )
        return

    user_id, count, status = row

    if status == "confirmed":
        # идемпотентность
        conn.close()
        return

    # 2️⃣ подтверждаем подписку
    cursor.execute("""
        UPDATE subscriptions
        SET status = 'confirmed'
        WHERE id = ?
    """, (subscription_id,))

    # 3️⃣ начисляем тренировки
    cursor.execute("""
        UPDATE users
        SET subscription = COALESCE(subscription, 0) + ?
        WHERE user_id = ?
    """, (count, user_id))

    conn.commit()
    conn.close()

    logger.info(
        f"[activate_subscription] subscription {subscription_id} activated for user {user_id}"
    )
