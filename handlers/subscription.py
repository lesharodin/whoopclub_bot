from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_connection
from config import ADMINS, PAYMENT_LINK, CARD
from datetime import datetime

router = Router()

PRICES = {
    5: 3800,
    10: 7200
}

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
    price = PRICES.get(count, "?")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subscriptions (user_id, count, status, created_at)
            VALUES (?, ?, 'pending', ?)
        """, (user_id, count, datetime.now().isoformat()))
        subscription_id = cursor.lastrowid
        conn.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"sub_paid:{subscription_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"user_cancel_sub:{subscription_id}")
        ]
    ])

    await callback.message.edit_text(
        f"Вы выбрали абонемент на <b>{count}</b> тренировок за <b>{price}₽</b>.\n"
        f"💳 Оплатите по ссылке: <a href='{PAYMENT_LINK}'>ОПЛАТИТЬ</a>\n"
        f"Либо по номеру карты <code>{CARD}</code>\n"
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
        msg = await callback.bot.send_message(admin, text, reply_markup=kb, parse_mode="HTML")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO subscription_notifications (subscription_id, admin_id, message_id)
                VALUES (?, ?, ?)
            """, (subscription_id, admin, msg.message_id))
            conn.commit()

    await callback.message.edit_text("🔔 Ожидайте подтверждения от администратора.")

@router.callback_query(F.data.startswith("user_cancel_sub:"))
async def user_cancel_subscription(callback: CallbackQuery):
    subscription_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    with get_connection() as conn:
        cursor = conn.cursor()
        # Проверяем, что запись принадлежит пользователю и ещё не подтверждена
        cursor.execute("""
            SELECT status FROM subscriptions
            WHERE id = ? AND user_id = ?
        """, (subscription_id, user_id))
        row = cursor.fetchone()

        if not row:
            await callback.answer("❌ Подписка не найдена.", show_alert=True)
            return

        status = row[0]
        if status != "pending":
            await callback.answer("⚠️ Подписка уже подтверждена и не может быть отменена.", show_alert=True)
            return

        # Удаляем запись
        cursor.execute("DELETE FROM subscriptions WHERE id = ?", (subscription_id,))
        conn.commit()

    await callback.message.edit_text("❌ Покупка абонемента отменена.")

@router.callback_query(F.data.startswith("sub_ok:"))
async def confirm_subscription(callback: CallbackQuery):
    subscription_id = int(callback.data.split(":")[1])
    admin_name = callback.from_user.full_name

    with get_connection() as conn:
        cursor = conn.cursor()

        # Проверяем текущий статус
        cursor.execute("SELECT user_id, count, status FROM subscriptions WHERE id = ?", (subscription_id,))
        result = cursor.fetchone()

        if not result:
            await callback.answer("❌ Подписка не найдена.", show_alert=True)
            return

        user_id, count, status = result

        if status != "pending":
            await callback.answer("⚠️ Эта подписка уже обработана.", show_alert=True)
            return
        
        # Обновляем статус и абонементы
        cursor.execute("UPDATE subscriptions SET status = 'confirmed' WHERE id = ?", (subscription_id,))
        cursor.execute("UPDATE users SET subscription = COALESCE(subscription, 0) + ? WHERE user_id = ?", (count, user_id))
        cursor.execute("SELECT subscription, nickname FROM users WHERE user_id = ?", (user_id,))
        sub_count, nickname = cursor.fetchone()

        conn.commit()

    await callback.message.edit_text("✅ Абонемент подтверждён")
    await callback.bot.send_message(user_id, f"✅ Оплата абонемента подтверждена. Вам доступно {sub_count} тренировок.")
    
    # ✅ Получаем username и имя участника (не админа)
    try:
        chat_member = await callback.bot.get_chat_member(chat_id=user_id, user_id=user_id)
        full_name = chat_member.user.full_name
        username = chat_member.user.username
    except:
        full_name = "Пользователь"
        username = None
    
    
    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{full_name}</a>"

    text = (
        f"🎟 Абонемент подтверждён админом <b>{admin_name}</b>\n"
        f"👤 Пользователь: {user_link} (ID: <code>{user_id}</code>)\n"
        f"📦 Добавлено: <b>{count}</b> тренировок\n"
        f"📊 Всего доступно: <b>{sub_count}</b>"
    )
    # Удаление сообщений у всех админов
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT admin_id, message_id FROM subscription_notifications WHERE subscription_id = ?", (subscription_id,))
        messages = cursor.fetchall()
        cursor.execute("DELETE FROM subscription_notifications WHERE subscription_id = ?", (subscription_id,))
        conn.commit()

    for admin_id, message_id in messages:
        try:
            await callback.bot.delete_message(chat_id=admin_id, message_id=message_id)
        except:
            pass        
    for admin in ADMINS:
        await callback.bot.send_message(admin, text, parse_mode="HTML")




@router.callback_query(F.data.startswith("sub_reject:"))
async def reject_subscription(callback: CallbackQuery):
    subscription_id = int(callback.data.split(":")[1])
    admin_name = callback.from_user.full_name

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, count, status FROM subscriptions WHERE id = ?", (subscription_id,))
        result = cursor.fetchone()

        if not result:
            await callback.answer("❌ Подписка не найдена.", show_alert=True)
            return

        user_id, count, status = result

        if status != "pending":
            await callback.answer("⚠️ Эта подписка уже обработана.", show_alert=True)
            return

        cursor.execute("DELETE FROM subscriptions WHERE id = ?", (subscription_id,))
        cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
        nickname_row = cursor.fetchone()
        nickname = nickname_row[0] if nickname_row else "профиль"
        conn.commit()

    await callback.message.edit_text("❌ Запрос отклонён")
    await callback.bot.send_message(user_id, "❌ Оплата не подтверждена. Попробуйте снова или свяжитесь с админом.")

    # ✅ Получаем username и имя участника (не админа)
    try:
        chat_member = await callback.bot.get_chat_member(chat_id=user_id, user_id=user_id)
        full_name = chat_member.user.full_name
        username = chat_member.user.username
    except:
        full_name = "Пользователь"
        username = None
    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{full_name}</a>"

    text = (
        f"🚫 Абонемент <b>отклонён</b> админом <b>{admin_name}</b>\n"
        f"👤 Пользователь: {user_link} (ID: <code>{user_id}</code>)\n"
        f"📦 Запрошено: <b>{count}</b> тренировок"
    )
    # Удаление сообщений у всех админов
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT admin_id, message_id FROM subscription_notifications WHERE subscription_id = ?", (subscription_id,))
        messages = cursor.fetchall()
        cursor.execute("DELETE FROM subscription_notifications WHERE subscription_id = ?", (subscription_id,))
        conn.commit()

    for admin_id, message_id in messages:
        try:
            await callback.bot.delete_message(chat_id=admin_id, message_id=message_id)
        except:
            pass        
    for admin in ADMINS:
        await callback.bot.send_message(admin, text, parse_mode="HTML")