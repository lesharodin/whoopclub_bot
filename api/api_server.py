from fastapi import FastAPI, Query, HTTPException, Request
import sqlite3
from datetime import datetime
import os
import hmac
import hashlib
import json

YOOKASSA_WEBHOOK_SECRET = os.getenv("YOOKASSA_WEBHOOK_SECRET")

app = FastAPI()

@app.get("/api/participants_by_date")
def get_participants_by_date(date: str = Query(..., description="Формат DD.MM.YYYY")):
    try:
        date_obj = datetime.strptime(date, "%d.%m.%Y")
        iso_prefix = date_obj.strftime("%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты. Используйте DD.MM.YYYY")

    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "bot.db"))
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
    # тело запроса
    body = await request.body()

    # подпись от ЮKassa
    signature = request.headers.get("Content-HMAC-SHA256")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    # проверка подписи
    expected_signature = hmac.new(
        YOOKASSA_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = json.loads(body)

    # нас интересует только успешная оплата
    if data.get("event") != "payment.succeeded":
        return {"ok": True}

    payment = data["object"]

    slot_id = int(payment["metadata"]["slot_id"])
    yookassa_payment_id = payment["id"]

    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "bot.db"))
    cursor = conn.cursor()

    # отмечаем платёж
    cursor.execute("""
        UPDATE payments
        SET status = 'succeeded'
        WHERE yookassa_payment_id = ?
    """, (yookassa_payment_id,))

    # подтверждаем слот
    cursor.execute("""
        UPDATE slots
        SET status = 'confirmed'
        WHERE id = ?
    """, (slot_id,))

    conn.commit()
    conn.close()

    print(f"[YOOKASSA] payment succeeded, slot_id={slot_id}")

    return {"ok": True}
