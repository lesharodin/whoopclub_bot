from fastapi import FastAPI, Query, HTTPException, Request
import sqlite3
from datetime import datetime
import os
import json

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

from payments.service import apply_payment
@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    data = await request.json()

    if data.get("event") != "payment.succeeded":
        return {"ok": True}

    payment_obj = data.get("object", {})
    yk_payment_id = payment_obj.get("id")
    metadata = payment_obj.get("metadata", {})

    internal_payment_id = metadata.get("payment_id")
    if not internal_payment_id:
        return {"ok": True}

    db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "database",
        "bot.db"
    )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM payments
        WHERE id = ?
    """, (internal_payment_id,))
    payment = cursor.fetchone()

    if not payment:
        conn.close()
        return {"ok": True}

    if payment["status"] == "succeeded":
        conn.close()
        return {"ok": True}

    cursor.execute("""
        UPDATE payments
        SET
            status = 'succeeded',
            yookassa_payment_id = ?,
            paid_at = ?
        WHERE id = ? AND status != 'succeeded'
    """, (
        yk_payment_id,
        datetime.now().isoformat(),
        internal_payment_id
    ))

    if cursor.rowcount == 0:
        conn.close()
        return {"ok": True}

    conn.commit()

    cursor.execute("""
        SELECT *
        FROM payments
        WHERE id = ?
    """, (internal_payment_id,))
    payment = cursor.fetchone()

    conn.close()

    apply_payment(dict(payment))

    return {"ok": True}
