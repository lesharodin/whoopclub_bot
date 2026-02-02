import asyncio
from datetime import datetime, timedelta
from aiogram import Bot
from database.db import get_connection
from config import ADMINS, REQUIRED_CHAT_ID

# Импортируем не только notify_admins_about_booking, но и конфиг групп
from handlers.booking import (
    notify_admins_about_booking,
    GROUPS,
    MAX_SLOTS_PER_GROUP,
    TOTAL_SLOTS,
    get_group_label,
)


async def monitor_pending_slots(bot: Bot):
    while True:
        await asyncio.sleep(900)  # Каждые 15 минут

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.training_id, s.user_id, s.group_name, s.channel, s.payment_type, s.created_at,
                       t.date, u.nickname, u.system
                FROM slots s
                JOIN trainings t ON s.training_id = t.id
                JOIN users u ON s.user_id = u.user_id
                WHERE s.status = 'pending'
                AND s.created_at < datetime('now', '-2 minutes')
                AND NOT EXISTS (
                    SELECT 1 FROM admin_notifications n WHERE n.slot_id = s.id
                )
            """)
            pending = cursor.fetchall()

        for slot in pending:
            (
                slot_id,
                training_id,
                user_id,
                group,
                channel,
                payment_type,
                created_at,
                training_date,
                nickname,
                system,
            ) = slot

            username = None  # username здесь из базы не получается
            full_name = nickname or system or "Пользователь"

            try:
                await notify_admins_about_booking(
                    bot=bot,
                    training_id=training_id,
                    user_id=user_id,
                    group=group,
                    channel=channel,
                    slot_id=slot_id,
                    username=username,
                    payment_type=payment_type,
                    full_name=full_name,
                    date_str=training_date,
                )
                print(f"[+] Переотправлено уведомление по записи {slot_id}")
            except Exception as e:
                print(f"[!] Ошибка при переотправке записи {slot_id}: {e}")


sent_progrev_for_dates = set()  # локальный кэш, чтобы не слать повторно


async def check_and_send_progrev(bot: Bot):
    """
    Ежедневно в 13:00 шлём прогрев на завтрашнюю тренировку,
    ТОЛЬКО если есть свободные места.
    """
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

            if not row:
                await asyncio.sleep(60)
                continue

            training_id, training_date = row

            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT group_name, COUNT(*)
                    FROM slots
                    WHERE training_id = ? AND status IN ('confirmed')
                    GROUP BY group_name
                """, (training_id,))
                counts = dict(cursor.fetchall())

            # === ВАЖНО: считаем свободные места ===
            free_slots_by_group = {}
            total_free = 0

            for group_name in GROUPS.keys():
                used = counts.get(group_name, 0)
                free = MAX_SLOTS_PER_GROUP[group_name] - used
                free_slots_by_group[group_name] = free
                total_free += max(free, 0)

            # ❌ НЕТ свободных мест — НИЧЕГО НЕ ШЛЁМ
            if total_free <= 0:
                print(f"[i] Прогрев НЕ отправлён — мест нет (training_id={training_id})")
                sent_progrev_for_dates.add(date_only)  # чтобы не проверять снова
                await asyncio.sleep(60)
                continue

            # === Формируем сообщение ===
            lines = []
            for group_name, free in free_slots_by_group.items():
                status = f"{free} мест" if free > 0 else "места закончились"
                lines.append(f"{get_group_label(group_name)}: <b>{status}</b>")

            date_fmt = datetime.fromisoformat(training_date).strftime("%d.%m.%Y %H:%M")

            text = (
                f"🔥 <b>Остались места на ближайшую тренировку!</b>\n"
                f"📅 <b>{date_fmt}</b>\n\n"
                + "\n".join(lines) +
                "\n\n"
                f"🚀 Успей записаться, пока есть места!"
            )

            try:
                await bot.send_message(
                    chat_id=REQUIRED_CHAT_ID,
                    text=text,
                    parse_mode="HTML"
                )
                sent_progrev_for_dates.add(date_only)
                print(f"[+] Сообщение про прогрев на {date_only} отправлено")
            except Exception as e:
                for admin in ADMINS:
                    try:
                        await bot.send_message(admin, f"❗Ошибка отправки сообщения о прогреве: {e}")
                    except:
                        pass

        await asyncio.sleep(60)



async def monitor_full_trainings(bot: Bot):
    """
    Раз в 5 минут проверяем открытые тренировки и, если все слоты заняты,
    шлём в чат сообщение «все места закончились».
    """
    while True:
        await asyncio.sleep(300)  # каждые 5 минут

        with get_connection() as conn:
            cursor = conn.cursor()
            # Все открытые тренировки, по которым ещё не отправляли сообщение
            cursor.execute("""
                SELECT id, date FROM trainings
                WHERE status = 'open' AND full_message_sent = 0
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

                total_confirmed = sum(counts.values())
                if total_confirmed >= TOTAL_SLOTS:
                    # Тренировка полностью забита
                    date_fmt = datetime.fromisoformat(date_str).strftime("%d.%m %H:%M")
                    text = f"❌ Все места на тренировку <b>{date_fmt}</b> закончились!"

                    try:
                        await bot.send_message(REQUIRED_CHAT_ID, text, parse_mode="HTML")
                        cursor.execute("UPDATE trainings SET full_message_sent = 1 WHERE id = ?", (training_id,))
                        conn.commit()
                        full_trainings_sent.add(training_id)
                    except Exception as e:
                        print(f"[!] Ошибка при отправке уведомления о полной тренировке: {e}")
