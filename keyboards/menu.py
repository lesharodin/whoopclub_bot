from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Участники")],
            [KeyboardButton(text="📋 Записаться", style="success", icon_custom_emoji_id="5470060791883374114"), KeyboardButton(text="📅 Мои записи")],
            [KeyboardButton(text="🎟 Купить абонемент", style="primary"), KeyboardButton(text="👤 Мой профиль")]
        ],
        resize_keyboard=True
    )
