from database.db import get_connection
from config import ADMINS, REQUIRED_CHAT_ID
from datetime import datetime
from handlers.booking import get_group_label, TOTAL_SLOTS

async def notify_confirmed_booking(bot, slot_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                s.user_id,
                s.payment_message_id,
                s.training_id,
                s.group_name,
                s.channel,
                s.payment_type, 
                t.date,
                u.subscription,
                u.nickname,
                u.system,
                s.tg_username,
                s.tg_full_name
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            JOIN users u ON s.user_id = u.user_id
            WHERE s.id = ?
              AND s.status = 'confirmed'
              AND s.notified = 0
        """, (slot_id,))
        row = cursor.fetchone()
        if not row:
            return

        (
            user_id,
            payment_message_id,
            training_id,
            group,
            channel,
            payment_type,
            date_str,
            subscription_left,
            nickname,
            system,
            tg_username,
            tg_full_name
        ) = row

        # считаем занятые места
        cursor.execute("""
            SELECT COUNT(*) FROM slots
            WHERE training_id = ? AND status = 'confirmed'
        """, (training_id,))
        booked = cursor.fetchone()[0]
        free_slots = TOTAL_SLOTS - booked

        # помечаем notified ДО отправки
        cursor.execute(
            "UPDATE slots SET notified = 1 WHERE id = ?",
            (slot_id,)
        )
        cursor.execute(
            "UPDATE slots SET payment_message_id = NULL WHERE id = ?",
            (slot_id,)
        )
        conn.commit()

    # формируем user_link
    if tg_username:
        user_link = f"@{tg_username}"
    else:
        user_link = f"<a href='tg://user?id={user_id}'>{tg_full_name}</a>"

    date_fmt = datetime.fromisoformat(date_str).strftime("%d.%m.%Y %H:%M")
    group_label = get_group_label(group)

    # 1️⃣ пользователю
    if payment_message_id:
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=payment_message_id,
                text=(
                    f"📅 <b>Тренировка {date_fmt}</b>\n"
                    f"✅ Оплата получена!\n"
                    f"Запись подтверждена 🛸"
                ),
                reply_markup=None,
                parse_mode="HTML"
                
            )
        except:
            pass

    # 2️⃣ клубный чат
    await bot.send_message(
        REQUIRED_CHAT_ID,
        f"🛸 {user_link} записался на тренировку <b>{date_fmt}</b>\n"
        f"Осталось мест: {free_slots}/{TOTAL_SLOTS}",
        parse_mode="HTML"
    )

    # 3️⃣ админам
    payment_text = (
        f"🎟 Абонемент (осталось {subscription_left})"
        if payment_type == "subscription"
        else "💳 YooKassa"
    )

    admin_text = (
        f"✅ {user_link} записался через Юкассу:\n"
        f"📅 {date_fmt}\n"
        f"🏁 <b>{group_label}</b>\n"
        f"📡 Канал: <b>{channel}</b>\n"
        f"🎮 OSD: <b>{nickname}</b>\n"
        f"{payment_text}"
    )

    for admin in ADMINS:
        await bot.send_message(admin, admin_text, parse_mode="HTML")

        
async def notify_confirmed_subscription(bot, subscription_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                s.user_id,
                s.count,
                s.payment_message_id,
                u.subscription,
                s.tg_username,
                s.tg_full_name
            FROM subscriptions s
            JOIN users u ON s.user_id = u.user_id
            WHERE s.id = ?
              AND s.status = 'confirmed'
              AND s.notified = 0
        """, (subscription_id,))
        row = cursor.fetchone()

        if not row:
            return

        (
            user_id,
            bought_count,
            payment_message_id,
            total_subscription,
            tg_username,
            tg_full_name
        ) = row

        # помечаем notified СРАЗУ
        cursor.execute(
            "UPDATE subscriptions SET notified = 1 WHERE id = ?",
            (subscription_id,)
        )
        conn.commit()

    # 🔗 user_link
    if tg_username:
        user_link = f"@{tg_username}"
    else:
        user_link = f"<a href='tg://user?id={user_id}'>{tg_full_name}</a>"

    # 1️⃣ пользователю — редактируем сообщение с оплатой
    if payment_message_id:
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=payment_message_id,
                text=(
                    f"🎟 <b>Абонемент успешно оплачен</b>\n\n"
                    f"➕ Добавлено тренировок: <b>{bought_count}</b>\n"
                    f"📊 Всего доступно: <b>{total_subscription}</b>\n\n"
                    f"Ждём вас на тренировках 🛸"
                ),
                parse_mode="HTML",
                reply_markup=None
            )
        except:
            pass
    else:
        await bot.send_message(
            user_id,
            (
                f"🎟 <b>Абонемент успешно оплачен</b>\n\n"
                f"➕ Добавлено тренировок: <b>{bought_count}</b>\n"
                f"📊 Всего доступно: <b>{total_subscription}</b>"
            ),
            parse_mode="HTML"
        )

    # 2️⃣ админам (информационно)
    admin_text = (
        f"🎟 <b>Оплачен абонемент</b>\n"
        f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
        f"➕ Добавлено: <b>{bought_count}</b>\n"
        f"📊 Всего у пользователя: <b>{total_subscription}</b>"
    )

    for admin in ADMINS:
        await bot.send_message(admin, admin_text, parse_mode="HTML")