from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_connection
from datetime import datetime

# импортируем конфиг групп из booking
from handlers.booking import GROUPS, get_group_label

router = Router()


@router.message(F.text.contains("Участники"))
async def show_participants_list(message: Message):
    today = datetime.now().date()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date FROM trainings
            WHERE status = 'open' AND datetime(date) >= ?
            ORDER BY date ASC
        """, (today.isoformat(),))
        rows = cursor.fetchall()

    if not rows:
        await message.answer("❌ Нет активных тренировок.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=datetime.fromisoformat(date_str).strftime("%d.%m.%Y %H:%M"),
            callback_data=f"participants:{training_id}"
        )]
        for training_id, date_str in rows
    ])

    await message.answer("👥 Выбери тренировку для просмотра участников:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("participants:"))
async def show_participants(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[1])
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT date FROM trainings WHERE id = ?", (training_id,))
        row = cursor.fetchone()
        if not row:
            await callback.answer("❌ Тренировка не найдена", show_alert=True)
            return

        date_str = row[0]
        dt = datetime.fromisoformat(date_str)
        pretty_date = dt.strftime("%d.%m.%Y %H:%M")

        message_lines = [f"📅 Тренировка {pretty_date}\n"]

        # Проходимся по всем группам из конфига
        for group_key, group_cfg in GROUPS.items():
            group_label = get_group_label(group_key)  # например "⚡ Быстрая"
            message_lines.append(f"{group_label} <b>группа</b>")

            CHANNEL_ORDER = group_cfg["channels"]  # например ["R1", "R2", "F2", "F4", "R8"]

            for idx, channel in enumerate(CHANNEL_ORDER, 1):
                cursor.execute("""
                    SELECT s.user_id, u.nickname, u.system
                    FROM slots s
                    LEFT JOIN users u ON s.user_id = u.user_id
                    WHERE s.training_id = ? AND s.group_name = ? AND s.status = 'confirmed' AND s.channel = ?
                """, (training_id, group_key, channel))
                result = cursor.fetchone()

                if result:
                    user_id, nickname, system = result
                    try:
                        chat_member = await callback.bot.get_chat_member(user_id=user_id, chat_id=user_id)
                        username = chat_member.user.username
                        first_name = chat_member.user.first_name
                    except:
                        username = None
                        first_name = "профиль"

                    user_link = (
                        f"@{username}"
                        if username
                        else f"<a href=\"tg://user?id={user_id}\">{first_name}</a>"
                    )
                    message_lines.append(
                        f"{idx}. {channel} — {user_link} "
                        f"(OSD: <code>{nickname or '-'}</code>, VTX: {system or '-'})"
                    )
                else:
                    message_lines.append(f"{idx}. {channel} — свободно")

            message_lines.append("")  # пустая строка между группами

    await callback.message.edit_text("\n".join(message_lines))
