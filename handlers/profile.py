from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from database.db import get_connection
from keyboards.menu import get_main_keyboard

router = Router()

class EditProfile(StatesGroup):
    nickname = State()
    system = State()

@router.message(F.text == "👤 Мой профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, system, subscription FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

    if user:
        nickname, system, subscription = user
        profile_text = (
            f"👤 <b>Ваш профиль</b>\n"
            f"🎮 OSD: <b>{nickname or '-'}</b>\n"
            f"🎥 Видео: <b>{system or '-'}</b>\n"
            f"🎟 Остаток абонемента: <b>{subscription or 0}</b> тренировок"
        )
    else:
        profile_text = "Профиль не найден."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="edit_profile")]
    ])

    await message.answer(profile_text, reply_markup=kb)

@router.callback_query(F.data == "edit_profile")
async def handle_edit_button(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите новый OSD / никнейм:")
    await state.set_state(EditProfile.nickname)

@router.message(EditProfile.nickname)
async def process_nickname(message: Message, state: FSMContext):
    await state.update_data(nickname=message.text)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="HDZero"), KeyboardButton(text="Аналог")],
            [KeyboardButton(text="DJI"), KeyboardButton(text="WS")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer("🚁 Выбери систему, на которой ты летаешь:", reply_markup=keyboard)
    await state.set_state(EditProfile.system)

@router.message(EditProfile.system)
async def process_system(message: Message, state: FSMContext):
    data = await state.get_data()
    nickname = data.get("nickname")
    system = message.text
    user_id = message.from_user.id

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, nickname, system)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET nickname=excluded.nickname, system=excluded.system
        """, (user_id, nickname, system))
        conn.commit()

    await message.answer("✅ Профиль обновлён.", reply_markup=get_main_keyboard())
    await state.clear()
