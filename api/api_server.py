from fastapi import FastAPI, Query, HTTPException
import sqlite3
from datetime import datetime
import os

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
            return "Группа ???"

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
