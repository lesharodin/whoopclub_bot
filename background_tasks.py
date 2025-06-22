import asyncio
from datetime import datetime
from aiogram import Bot
from database.db import get_connection
from config import ADMINS
from handlers.booking import notify_admins_about_booking

async def monitor_pending_slots(bot: Bot):
    while True:
        await asyncio.sleep(300)  # Каждые 5 минут

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.training_id, s.user_id, s.group_name, s.channel, s.payment_type, s.created_at,
                    t.date, u.nickname, u.system
                FROM slots s
                JOIN trainings t ON s.training_id = t.id
                JOIN users u ON s.user_id = u.user_id
                WHERE s.status = 'pending'
                AND NOT EXISTS (
                    SELECT 1 FROM admin_notifications n WHERE n.slot_id = s.id
                  )
            """)
            pending = cursor.fetchall()

        for slot in pending:
            slot_id, training_id, user_id, group, channel, payment_type, date_str, username, system, nickname = slot
            full_name = nickname or system or "Пользователь"
            try:
                await notify_admins_about_booking(
                    bot, training_id, user_id, group, channel, slot_id,
                    username, payment_type, full_name, date_str
                )
                print(f"[+] Переотправлено уведомление по записи {slot_id}")
            except Exception as e:
                print(f"[!] Ошибка при переотправке записи {slot_id}: {e}")
