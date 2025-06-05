from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMINS
from database.db import get_connection
from datetime import datetime

router = Router()

# FSM состояние
class NewTraining(StatesGroup):
    waiting_for_date = State()

# Команда для проверки своего Telegram ID
@router.message(F.text == "/id")
async def get_id(message: Message):
    await message.answer(f"🪪 Твой Telegram ID: <code>{message.from_user.id}</code>")

# Админская команда
@router.message(F.text == "/new_training")
async def ask_for_date(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ У тебя нет прав администратора.")
        return

    await message.answer("📅 Введи дату тренировки в формате `YYYY-MM-DD HH:MM` (например, 2025-06-11 18:30):")
    await state.set_state(NewTraining.waiting_for_date)

@router.message(NewTraining.waiting_for_date)
async def save_training(message: Message, state: FSMContext):
    try:
        dt = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Попробуй ещё раз (пример: 2025-06-11 18:30)")
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO trainings (date, status) VALUES (?, ?)", (dt.isoformat(), "open"))
        conn.commit()

    await message.answer(f"✅ Тренировка создана на {dt.strftime('%d.%m.%Y %H:%M')}")
    await state.clear()
