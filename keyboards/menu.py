from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from config import ADMINS

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Участники")],
            [KeyboardButton(text="Записаться", style="success", icon_custom_emoji_id="5470060791883374114"), KeyboardButton(text="📅 Мои записи")],
            [KeyboardButton(text="Купить абонемент", style="primary", icon_custom_emoji_id="5237971457971067970"), KeyboardButton(text="👤 Мой профиль")]
        ],
        resize_keyboard=True
    )


def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Участники")],
            [KeyboardButton(text="Записаться", style="success", icon_custom_emoji_id="5470060791883374114"), KeyboardButton(text="📅 Мои записи")],
            [KeyboardButton(text="Купить абонемент", style="primary", icon_custom_emoji_id="5237971457971067970"), KeyboardButton(text="👤 Мой профиль")],
            [KeyboardButton(text="Админка")]
        ],
        resize_keyboard=True
    )


def get_user_main_keyboard(user_id: int):
    if user_id in ADMINS:
        return get_admin_keyboard()
    return get_main_keyboard()
