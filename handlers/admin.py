from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from config import ADMINS
from database.db import get_connection
from aiogram.filters.command import Command
from aiogram.utils.markdown import hbold
from handlers.booking import notify_admins_about_booking
import calendar

router = Router()


def get_existing_training_dates() -> set[str]:
    """Получает даты только открытых тренировок (без времени) в формате 'YYYY-MM-DD'."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT date FROM trainings WHERE status = 'open'")
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

# Команда для проверки своего Telegram ID
@router.message(F.text == "/id")
async def get_id(message: Message):
    await message.answer(f"🪪 Твой Telegram ID: <code>{message.from_user.id}</code>")

#Список пользователей

@router.message(F.text == "/users")
async def list_users(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ У тебя нет прав администратора.")
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, nickname, system, subscription
            FROM users
            ORDER BY user_id
        """)
        users = cursor.fetchall()

    if not users:
        await message.answer("📭 В базе нет зарегистрированных пользователей.")
        return

    lines = ["📋 Список пользователей:\n"]
    for user_id, nickname, system, subscription in users:
        # Пытаемся получить username и полное имя
        chat_member = await message.bot.get_chat_member(chat_id=user_id, user_id=user_id)
        full_name = chat_member.user.full_name
        username = chat_member.user.username

        user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{full_name}</a>"

        lines.append(
            f"{user_link} | ID: <code>{user_id}</code>\n"
            f"🎮 OSD: {nickname}\n"
            f"🎥 Система: {system}\n"
            f"🎟 Абонементов: {subscription}\n"
            f"---"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")

# Создание тренировок
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
        # Создание тренировки
        cursor.execute("INSERT INTO trainings (date, status) VALUES (?, ?)", (dt.isoformat(), "open"))
        training_id = cursor.lastrowid
        # Автоматическая запись двух админов
        now = datetime.now().isoformat()
        admin_slots = [
            (training_id, 932407372, 'fast', 'R1'),
            (training_id, 132536948, 'fast', 'L1')
        ]
        for training_id, admin_id, group, channel in admin_slots:
            cursor.execute("""
                INSERT INTO slots (training_id, user_id, group_name, channel, status, created_at, payment_type)
                VALUES (?, ?, ?, ?, 'confirmed', ?, 'admin')
            """, (training_id, admin_id, group, channel, now))

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


#Начисление абонементов


@router.message(Command("add_subscription"))
async def add_subscription_command(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ У тебя нет прав администратора.")
        return

    parts = message.text.strip().split()
    if len(parts) != 3:
        await message.answer("❗ Используй формат: /add_subscription <user_id> <кол-во>")
        return

    try:
        target_user_id = int(parts[1])
        count = int(parts[2])
        if count <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❗ Введи корректные числовые значения.")
        return

    # Проверим, существует ли пользователь
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (target_user_id,))
        row = cursor.fetchone()

    if not row:
        await message.answer("❌ Пользователь не найден.")
        return

    nickname = row[0]

    # Кнопки подтверждения
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_add_sub:{target_user_id}:{count}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_add_sub")
        ]
    ])
    await message.answer(
        f"Вы действительно хотите начислить {count} абонементов пользователю <b>{nickname}</b> (ID: <code>{target_user_id}</code>)?",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("confirm_add_sub:"))
async def confirm_add_subscription(callback: CallbackQuery):
    _, user_id_str, count_str = callback.data.split(":")
    user_id = int(user_id_str)
    count = int(count_str)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET subscription = subscription + ? WHERE user_id = ?", (count, user_id))
        cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.commit()

    nickname = row[0] if row else "неизвестный"

    # Уведомление админу
    await callback.message.edit_text(
        f"✅ Начислено {count} абонементов пользователю <b>{nickname}</b> (ID: <code>{user_id}</code>)."
    )
    await callback.answer()

    # Уведомление пользователя
    try:
        await callback.bot.send_message(
            user_id,
            f"🎉 Вам начислено <b>{count}</b> абонементов! Теперь вы можете записаться на тренировку без оплаты."
        )
    except Exception as e:
        # Если пользователь не начал бота, ловим ошибку
        await callback.message.answer(f"⚠️ Не удалось отправить сообщение пользователю: {e}")


@router.callback_query(F.data == "cancel_add_sub")
async def cancel_add_subscription(callback: CallbackQuery):
    await callback.message.edit_text("❌ Начисление абонементов отменено.")
    await callback.answer()


#отмена тренировки    
@router.message(Command("cancel_training"))
async def cancel_training(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ У тебя нет прав администратора.")
        return

    now = datetime.now().isoformat()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date FROM trainings
            WHERE status = 'open' AND datetime(date) > ?
            ORDER BY date ASC
        """, (now,))
        rows = cursor.fetchall()

    if not rows:
        await message.answer("❌ Нет будущих открытых тренировок.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=datetime.fromisoformat(date).strftime("%d.%m %H:%M"),
            callback_data=f"cancel_train:{training_id}"
        )]
        for training_id, date in rows
    ])

    await message.answer("Выбери тренировку для отмены:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("cancel_train:"))
async def confirm_training_cancel(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[1])

    with get_connection() as conn:
        cursor = conn.cursor()

        # Получаем дату тренировки
        cursor.execute("SELECT date FROM trainings WHERE id = ?", (training_id,))
        row = cursor.fetchone()
        if not row:
            await callback.answer("❌ Тренировка не найдена", show_alert=True)
            return
        date_str = datetime.fromisoformat(row[0]).strftime("%d.%m.%Y %H:%M")

        # Получаем всех участников
        cursor.execute("""
            SELECT s.user_id, s.status
            FROM slots s
            WHERE s.training_id = ?
        """, (training_id,))
        participants = cursor.fetchall()

        # Обновляем статус тренировки
        cursor.execute("UPDATE trainings SET status = 'cancelled' WHERE id = ?", (training_id,))
        conn.commit()

    # Рассылаем уведомления
    for user_id, status in participants:
        try:
            if status == "confirmed":
                # Возврат абонемента
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE users SET subscription = subscription + 1 WHERE user_id = ?", (user_id,)
                    )
                await callback.bot.send_message(
                    user_id,
                    f"❌ Тренировка {date_str} была отменена.\n🎟 Вам возвращён 1 абонемент."
                )
            else:
                await callback.bot.send_message(
                    user_id,
                    f"❌ Тренировка {date_str} была отменена."
                )
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

    await callback.message.edit_text(f"✅ Тренировка {date_str} отменена, пользователи уведомлены.")
    await callback.answer()


#подсказки

@router.message(F.text == "/admin")
async def admin_help(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ У тебя нет прав администратора.")
        return

    help_text = (
        "🛠 <b>Админ-команды:</b>\n\n"
        "📋 <b>/users</b> — список всех зарегистрированных пользователей\n"
        "📅 <b>/new_training</b> — создать новую тренировку через календарь\n"
        "Создание тренировки доступно только на вторник или субботу.\n"
        "➕ <b>/add_subscription &lt;user_id&gt; &lt;кол-во&gt;</b> — начислить абонементы пользователю\n"
        "💡 После команды <code>/add_subscription</code> бот спросит подтверждение перед начислением.\n"
        "\n"
        "<b>/cancel_training</b> — отменить существующую тренировку\n"
        "  ⛔ Отменяются только будущие тренировки\n"
        "  🔁 Подтверждённым участникам возвращается 1 абонемент и приходит уведомление\n\n"
        "🪪 <b>/id</b> — узнать свой Telegram ID\n"
        "\n"
    )

    await message.answer(help_text, parse_mode="HTML")

admin_router = Router()

@admin_router.message(Command("resend_pending"))
async def resend_pending_handler(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ У тебя нет прав.")
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.training_id, s.user_id, s.group_name, s.channel, s.payment_type, s.created_at,
                   t.date, u.nickname, u.system
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            JOIN users u ON s.user_id = u.user_id
            WHERE s.status = 'pending'
              AND NOT EXISTS (
                SELECT 1 FROM admin_notifications n WHERE n.slot_id = s.id
              )
        """)
        slots = cursor.fetchall()

    if not slots:
        await message.answer("✅ Все уведомления отправлены. Ничего не найдено.")
        return

    sent_count = 0

    for row in slots:
        slot_id, training_id, user_id, group, channel, payment_type, _, training_date, _, _, = row

        try:
            chat_member = await bot.get_chat_member(chat_id=user_id, user_id=user_id)
            username = chat_member.user.username
            full_name = chat_member.user.full_name
        except:
            full_name = "Пользователь"
            username = None

        await notify_admins_about_booking(
            training_id=training_id,
            user_id=user_id,
            group=group,
            channel=channel,
            slot_id=slot_id,
            username=username,
            payment_type=payment_type,
            full_name=full_name,
            date_str=training_date
        )
        sent_count += 1

    await message.answer(f"✅ Уведомления повторно отправлены по {sent_count} слоту(ам).")