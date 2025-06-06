from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from config import ADMINS
from database.db import get_connection
import calendar

router = Router()


def get_existing_training_dates() -> set[str]:
    """Получает даты созданных тренировок (без времени) в формате 'YYYY-MM-DD'."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT date FROM trainings")
        results = cursor.fetchall()
    return {datetime.fromisoformat(row[0]).date().isoformat() for row in results}


def build_calendar(year: int, month: int) -> InlineKeyboardMarkup:
    now = datetime.now()
    today = now.date()
    existing_dates = get_existing_training_dates()

    calendar.setfirstweekday(calendar.MONDAY)
    month_calendar = calendar.monthcalendar(year, month)

    markup = []

    # Название месяца
    markup.append([InlineKeyboardButton(text=f"{calendar.month_name[month]} {year}", callback_data="ignore")])

    # Дни недели
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    markup.append([InlineKeyboardButton(text=day, callback_data="ignore") for day in days])

    for week in month_calendar:
        row = []
        for i, day in enumerate(week):
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
                continue

            date_obj = datetime(year, month, day).date()
            if i in (1, 5) and date_obj >= today:
                date_str = date_obj.isoformat()
                label = f"{day}"
                if date_str in existing_dates:
                    label += "✅"
                callback_data = f"date:{date_str}"
                row.append(InlineKeyboardButton(text=label, callback_data=callback_data))
            else:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
        markup.append(row)

    # Навигация
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    nav_buttons = []
    base_month = datetime(datetime.now().year, datetime.now().month, 1)
    this_month = datetime(year, month, 1)

    if this_month > base_month:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"cal:{prev_year}:{prev_month}"))
    nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"cal:{next_year}:{next_month}"))
    markup.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=markup)


@router.message(F.text == "/new_training")
async def show_calendar(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ У тебя нет прав администратора.")
        return

    now = datetime.now()
    await send_calendar(message, now.year, now.month)


@router.callback_query(F.data.startswith("cal:"))
async def navigate_calendar(callback: CallbackQuery):
    _, year, month = callback.data.split(":")
    year = int(year)
    month = int(month)

    keyboard = build_calendar(year, month)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("date:"))
async def create_training(callback: CallbackQuery):
    _, date_str = callback.data.split(":", 1)
    selected_date = datetime.strptime(date_str, "%Y-%m-%d")

    # Устанавливаем время для вторника или субботы
    if selected_date.weekday() == 1:  # вторник
        dt = selected_date.replace(hour=19, minute=0)
    elif selected_date.weekday() == 5:  # суббота
        dt = selected_date.replace(hour=16, minute=0)
    else:
        await callback.answer("Можно выбрать только вторник или субботу", show_alert=True)
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO trainings (date, status) VALUES (?, ?)", (dt.isoformat(), "open"))
        conn.commit()

    await callback.message.edit_text(f"✅ Тренировка создана на {dt.strftime('%d.%m.%Y %H:%M')}")
    await callback.answer()


async def send_calendar(target, year: int, month: int):
    text = f"📅 Выбери дату тренировки ({calendar.month_name[month]} {year})"
    kb = build_calendar(year, month)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.edit_text(text, reply_markup=kb)
