import asyncio
from datetime import datetime, timedelta
from aiogram import Bot
from database.db import get_connection
from config import ADMINS, REQUIRED_CHAT_ID
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

sent_progrev_for_dates = set()  # локальный кэш, чтобы не слать повторно

async def check_and_send_progrev(bot: Bot):
    while True:
        now = datetime.now()

        if now.hour == 13 and now.minute == 0:
            tomorrow = now + timedelta(days=1)
            date_only = tomorrow.date()

            if date_only in sent_progrev_for_dates:
                await asyncio.sleep(60)
                continue

            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, date FROM trainings
                    WHERE status = 'open' AND DATE(date) = ?
                    ORDER BY date ASC
                    LIMIT 1
                """, (date_only.isoformat(),))
                row = cursor.fetchone()

            if row:
                training_id, training_date = row

                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT group_name, COUNT(*) 
                        FROM slots 
                        WHERE training_id = ? AND status IN ('pending', 'confirmed')
                        GROUP BY group_name
                    """, (training_id,))
                    counts = dict(cursor.fetchall())

                fast_free = 5 - counts.get("fast", 0)
                standard_free = 7 - counts.get("standard", 0)

                fast_label = f"{fast_free} мест" if fast_free > 0 else "места закончились"
                standard_label = f"{standard_free} мест" if standard_free > 0 else "места закончились"
                date_fmt = datetime.fromisoformat(training_date).strftime("%d.%m.%Y %H:%M")

                text = (
                    f"🔥 <b>Остались места на ближайшую тренировку!</b>\n"
                    f"📅 <b>{date_fmt}</b>\n\n"
                    f"⚡ Быстрая группа: <b>{fast_label}</b>\n"
                    f"🏁 Стандартная группа: <b>{standard_label}</b>\n\n"
                    f"🚀 Успей записаться, пока есть места!"
                )

                try:
                    await bot.send_message(chat_id=REQUIRED_CHAT_ID, text=text, parse_mode="HTML")
                    sent_progrev_for_dates.add(date_only)
                    print(f"[+] Сообщение про прогрев на {date_only} отправлено")
                except Exception as e:
                    for admin in ADMINS:
                        await bot.send_message(admin, f"❗Ошибка отправки сообщения о прогреве: {e}")

        await asyncio.sleep(60)  # проверяем каждую минуту
full_trainings_sent = set()  # хранит training_id, по которым уже отправлено

async def monitor_full_trainings(bot: Bot):
    while True:
        await asyncio.sleep(300)  # каждые 5 минут

        with get_connection() as conn:
            cursor = conn.cursor()
            # Все открытые тренировки
            cursor.execute("""
                SELECT id, date FROM trainings
                WHERE status = 'open'
            """)
            trainings = cursor.fetchall()

            for training_id, date_str in trainings:
                if training_id in full_trainings_sent:
                    continue

                # Проверяем confirmed-записи по группам
                cursor.execute("""
                    SELECT group_name, COUNT(*)
                    FROM slots
                    WHERE training_id = ? AND status = 'confirmed'
                    GROUP BY group_name
                """, (training_id,))
                counts = dict(cursor.fetchall())

                if counts.get("fast", 0) >= 5 and counts.get("standard", 0) >= 7:
                    date_fmt = datetime.fromisoformat(date_str).strftime("%d.%m %H:%M")
                    text = f"❌ Все места на тренировку <b>{date_fmt}</b> закончились!"
                    try:
                        await bot.send_message(CLUB_CHAT_ID, text)
                        full_trainings_sent.add(training_id)
                    except Exception as e:
                        print(f"[!] Ошибка при отправке уведомления о полной тренировке: {e}")
