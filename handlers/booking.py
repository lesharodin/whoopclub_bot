from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from database.db import get_connection
from config import ADMINS
from datetime import datetime
import asyncio

router = Router()

CHANNELS = {
    "fast": 5,
    "standard": 7
}

@router.message(F.text.contains("Записаться"))
async def show_trainings_list(message: Message):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date FROM trainings
            WHERE status = 'open'
            ORDER BY date ASC
        """)
        rows = cursor.fetchall()

    if not rows:
        await message.answer("❌ Пока нет открытых тренировок.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=datetime.fromisoformat(date_str).strftime("%d.%m.%Y %H:%M"), callback_data=f"select_training:{training_id}")]
        for training_id, date_str in rows
    ])

    await message.answer("📅 Выбери тренировку:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("select_training:"))
async def show_training_groups(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[1])

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡ Быстрая группа", callback_data=f"book:{training_id}:fast"),
            InlineKeyboardButton(text="🏁 Стандартная группа", callback_data=f"book:{training_id}:standard")
        ]
    ])

    await callback.message.edit_text(f"Выбери группу для тренировки {training_id}:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("book:"))
async def choose_channel(callback: CallbackQuery):
    _, training_id, group = callback.data.split(":")
    training_id = int(training_id)

    total = CHANNELS.get(group)
    all_channels = [f"Канал {i+1}" for i in range(total)]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT channel FROM slots
            WHERE training_id = ? AND group_name = ? AND status IN ('pending', 'confirmed')
        """, (training_id, group))
        taken = [row[0] for row in cursor.fetchall()]

    available = [ch for ch in all_channels if ch not in taken]

    if not available:
        await callback.message.edit_text("❌ В этой группе нет свободных каналов.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ch, callback_data=f"reserve:{training_id}:{group}:{ch}")]
        for ch in available
    ])

    await callback.message.edit_text(f"🧩 Свободные каналы в группе <b>{'Быстрая' if group == 'fast' else 'Стандартная'}</b>:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("reserve:"))
async def reserve_slot(callback: CallbackQuery):
    _, training_id, group, channel = callback.data.split(":")
    training_id = int(training_id)
    user_id = callback.from_user.id
    username = callback.from_user.username

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM slots
            WHERE training_id = ? AND user_id = ?
        """, (training_id, user_id))
        already = cursor.fetchone()[0]
        if already:
            await callback.answer("Вы уже записаны на эту тренировку.", show_alert=True)
            return

        cursor.execute("""
            INSERT INTO slots (training_id, user_id, group_name, channel, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            training_id,
            user_id,
            group,
            channel,
            "pending",
            datetime.now().isoformat()
        ))
        slot_id = cursor.lastrowid
        conn.commit()

    await notify_admins_about_booking(callback.bot, training_id, user_id, group, channel, slot_id, username)

    await callback.message.edit_text(
        f"✅ Вы забронировали <b>{channel}</b> в группе <b>{'Быстрая' if group == 'fast' else 'Стандартная'}</b>.\n"
        f"💸 Ожидается подтверждение оплаты от администратора."
    )

async def notify_admins_about_booking(bot, training_id, user_id, group, channel, slot_id, username):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, system FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        cursor.execute("SELECT date FROM trainings WHERE id = ?", (training_id,))
        training_row = cursor.fetchone()

    nickname = user[0] if user else "-"
    system = user[1] if user else "-"
    training_date = datetime.fromisoformat(training_row[0]).strftime("%d.%m.%Y %H:%M") if training_row else "?"
    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>профиль</a>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{slot_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{slot_id}")
        ]
    ])

    text = (
        f"📥 Новая запись на тренировку <b>{training_date}</b>:\n"
        f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
        f"🏁 Группа: <b>{'Быстрая' if group == 'fast' else 'Стандартная'}</b>\n"
        f"📡 Канал: <b>{channel}</b>\n"
        f"🎮 OSD: <b>{nickname}</b>\n"
        f"🎥 Видео: <b>{system}</b>\n"
        f"⏳ Ожидает подтверждения оплаты"
    )

    for admin in ADMINS:
        await bot.send_message(admin, text, reply_markup=kb)

@router.callback_query(F.data.startswith("confirm:"))
async def confirm_booking(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])
    with get_connection() as conn:
        cursor = conn.cursor()

        # Получаем пользователя и статус абонемента
        cursor.execute("SELECT user_id FROM slots WHERE id = ?", (slot_id,))
        row = cursor.fetchone()
        if not row:
            await callback.message.edit_text("❌ Запись не найдена.")
            return

        user_id = row[0]

        # Обновляем статус
        cursor.execute("UPDATE slots SET status = 'confirmed' WHERE id = ?", (slot_id,))

        # Если у пользователя есть занятия по абонементу — списываем одно
        cursor.execute("SELECT subscription FROM users WHERE user_id = ?", (user_id,))
        sub_row = cursor.fetchone()
        if sub_row and sub_row[0] and sub_row[0] > 0:
            cursor.execute("UPDATE users SET subscription = subscription - 1 WHERE user_id = ?", (user_id,))

        conn.commit()

    await callback.message.edit_text("✅ Оплата подтверждена")
    await callback.bot.send_message(user_id, "✅ Ваша запись подтверждена! Ждём вас на тренировке 🛸")


@router.callback_query(F.data.startswith("reject:"))
async def reject_booking(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM slots WHERE id = ?", (slot_id,))
        row = cursor.fetchone()
        user_id = row[0] if row else None
        cursor.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
        conn.commit()

    await callback.message.edit_text("❌ Запись отклонена")
    if user_id:
        await callback.bot.send_message(user_id, "❌ Ваша запись была отклонена. Попробуйте снова или свяжитесь с админом.")
