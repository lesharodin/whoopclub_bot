from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from database.db import get_connection
from keyboards.menu import get_main_keyboard

router = Router()

class Registration(StatesGroup):
    enter_nickname = State()
    select_system = State()

@router.message(F.text == "/start")
async def start_registration(message: Message, state: FSMContext):
    user_id = message.from_user.id

    # Проверка регистрации
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, system FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

    if row:
        nickname, system = row
        await message.answer(
            f"👋 Ты уже зарегистрирован!\n\n"
            f"👤 Никнейм: {nickname}\n"
            f"🛠️ Система: {system}",
            reply_markup=get_main_keyboard()
        )
        return

    # Если не зарегистрирован — начинаем регистрацию
    await message.answer("👋 Привет! Назови свой никнейм / OSD:")
    await state.set_state(Registration.enter_nickname)

@router.message(Registration.enter_nickname)
async def process_nickname(message: Message, state: FSMContext):
    await state.update_data(nickname=message.text)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="HDZero"), KeyboardButton(text="Аналог")],
            [KeyboardButton(text="DJI"), KeyboardButton(text="WS")]
        ],
        resize_keyboard=True
    )
    await message.answer("🚁 Выбери систему, на которой ты летаешь:", reply_markup=keyboard)
    await state.set_state(Registration.select_system)

@router.message(Registration.select_system)
async def finish_registration(message: Message, state: FSMContext):
    data = await state.update_data(system=message.text)
    await state.clear()

    user_id = message.from_user.id
    nickname = data["nickname"]
    system = data["system"]

    # Сохраняем в БД
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, nickname, system) VALUES (?, ?, ?)",
            (user_id, nickname, system)
        )
        conn.commit()

    await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"👤 Никнейм: {nickname}\n"
        f"🛠️ Система: {system}",
        reply_markup=get_main_keyboard()
    )