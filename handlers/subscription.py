from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_connection
from config import ADMINS
from datetime import datetime

router = Router()

@router.message(F.text.contains("Купить абонемент"))
async def show_subscription_options(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="5 тренировок -5% 3800₽", callback_data="sub:5"),
            InlineKeyboardButton(text="10 тренировок -10% 7200₽", callback_data="sub:10")
        ]
    ])
    await message.answer("Выберите абонемент:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("sub:"))
async def process_subscription(callback: CallbackQuery):
    count = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    username = callback.from_user.username

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subscriptions (user_id, count, status, created_at)
            VALUES (?, ?, 'pending', ?)
        """, (user_id, count, datetime.now().isoformat()))
        subscription_id = cursor.lastrowid
        conn.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"sub_paid:{subscription_id}")]
    ])

    await callback.message.edit_text(
        f"Вы выбрали абонемент на {count} тренировок.\n"
        f"💳 Реквизиты для оплаты: +7 905 563 5566 Т-Банк\n\n"
        f"После оплаты нажмите кнопку ниже:",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("sub_paid:"))
async def notify_admins(callback: CallbackQuery):
    subscription_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    username = callback.from_user.username
    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>профиль</a>"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count FROM subscriptions WHERE id = ?", (subscription_id,))
        count = cursor.fetchone()[0]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"sub_ok:{subscription_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"sub_reject:{subscription_id}")
        ]
    ])

    text = (
        f"💰 Покупка абонемента\n"
        f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
        f"📦 {count} тренировок\n"
        f"⏳ Ожидает подтверждения"
    )

    for admin in ADMINS:
        await callback.bot.send_message(admin, text, reply_markup=kb)

    await callback.message.edit_text("🔔 Ожидайте подтверждения от администратора.")



@router.callback_query(F.data.startswith("sub_ok:"))
async def confirm_subscription(callback: CallbackQuery):
    subscription_id = int(callback.data.split(":")[1])
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, count FROM subscriptions WHERE id = ?", (subscription_id,))
        user_id, count = cursor.fetchone()
        cursor.execute("UPDATE subscriptions SET status = 'confirmed' WHERE id = ?", (subscription_id,))
        cursor.execute("UPDATE users SET subscription = COALESCE(subscription, 0) + ? WHERE user_id = ?", (count, user_id))
        conn.commit()

    await callback.message.edit_text("✅ Абонемент подтверждён")
    await callback.bot.send_message(user_id, f"✅ Оплата абонемента подтверждена. Вам доступно {count} тренировок.")

@router.callback_query(F.data.startswith("sub_reject:"))
async def reject_subscription(callback: CallbackQuery):
    subscription_id = int(callback.data.split(":")[1])
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM subscriptions WHERE id = ?", (subscription_id,))
        user_id = cursor.fetchone()[0]
        cursor.execute("DELETE FROM subscriptions WHERE id = ?", (subscription_id,))
        conn.commit()

    await callback.message.edit_text("❌ Запрос отклонён")
    await callback.bot.send_message(user_id, "❌ Оплата не подтверждена. Попробуйте снова или свяжитесь с админом.")
