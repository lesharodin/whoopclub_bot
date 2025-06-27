from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Участники")],
            [KeyboardButton(text="📋 Записаться"), KeyboardButton(text="📅 Мои записи")],
            [KeyboardButton(text="🎟 Купить абонемент"), KeyboardButton(text="👤 Мой профиль")],
            [KeyboardButton(text="📊 Результаты")]
        ],
        resize_keyboard=True
    )
