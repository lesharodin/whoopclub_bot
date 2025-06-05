from aiogram import Router, F
from aiogram.types import Message
from database.db import get_connection

router = Router()

@router.message(F.text == "👤 Мой профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, system, subscription FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

    if row:
        nickname, system, subscription = row
        nickname = nickname or "-"
        system = system or "-"
        subscription = subscription if subscription is not None else 0

        await message.answer(
            f"👤 <b>Ваш профиль</b>\n"
            f"🪪 ID: <code>{user_id}</code>\n"
            f"🎮 OSD: <b>{nickname}</b>\n"
            f"🎥 Видео: <b>{system}</b>\n"
            f"🎟 Осталось занятий по абонементу: <b>{subscription}</b>"
        )
    else:
        await message.answer("⚠️ Профиль не найден. Зарегистрируйтесь заново командой /start")

