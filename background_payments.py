import asyncio
from datetime import datetime
from database.db import get_connection
from config import ADMINS, REQUIRED_CHAT_ID
from logging_config import logger
from handlers.booking import get_group_label, TOTAL_SLOTS


async def payments_ui_watcher(bot):
    logger.info("[payments_ui_watcher] started")

    while True:
        await asyncio.sleep(5)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    p.id,
                    p.user_id,
                    p.chat_id,
                    p.message_id,
                    p.target_type,
                    p.target_id
                FROM payments p
                WHERE p.status = 'succeeded'
                  AND p.ui_status = 'shown'
                  AND p.target_type IN ('slot', 'subscription')
            """)
            payments = cursor.fetchall()

        for payment_id, user_id, chat_id, message_id, target_type, target_id in payments:
            try:
                if target_type == "slot":
                    await handle_slot_payment(
                        bot=bot,
                        payment_id=payment_id,
                        user_id=user_id,
                        chat_id=chat_id,
                        message_id=message_id,
                        slot_id=target_id
                    )

                elif target_type == "subscription":
                    await handle_subscription_payment(
                        bot=bot,
                        payment_id=payment_id,
                        user_id=user_id,
                        chat_id=chat_id,
                        message_id=message_id,
                        subscription_id=target_id
                    )

                else:
                    logger.warning(
                        f"[payments_ui_watcher] unknown target_type={target_type}"
                    )

            except Exception as e:
                logger.exception(
                    f"[payments_ui_watcher] error for payment {payment_id}: {e}"
                )

            else:
                # помечаем UI как обработанный
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE payments SET ui_status = 'paid' WHERE id = ?",
                        (payment_id,)
                    )
                    conn.commit()
async def handle_slot_payment(
    *,
    bot,
    payment_id: int,
    user_id: int,
    chat_id: int,
    message_id: int,
    slot_id: int
):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                s.group_name,
                s.channel,
                t.date,
                t.id
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            WHERE s.id = ?
        """, (slot_id,))
        row = cursor.fetchone()

    if not row:
        return

    group, channel, date_str, training_id = row
    date_fmt = datetime.fromisoformat(date_str).strftime("%d.%m.%Y %H:%M")
    group_label = get_group_label(group)

    # 1️⃣ обновляем сообщение оплаты (убираем кнопки)
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            f"📅 <b>Тренировка {date_fmt}</b>\n"
            f"✅ <b>Оплата получена!</b>\n"
            f"🏁 {group_label}, канал <b>{channel}</b>"
        ),
        parse_mode="HTML"
    )

#   # 2️⃣ уведомляем пользователя (дублируем на всякий случай)
#   await bot.send_message(
#       user_id,
#       f"✅ Ваша запись подтверждена!\n"
#       f"📅 {date_fmt}\n"
#       f"🏁 {group_label}, канал {channel}"
#   )

    # 3️⃣ считаем свободные места
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM slots
            WHERE training_id = ? AND status = 'confirmed'
        """, (training_id,))
        booked = cursor.fetchone()[0]

    free_slots = TOTAL_SLOTS - booked

    # 4️⃣ уведомление в клубный чат
    try:
        chat_member = await bot.get_chat_member(user_id, user_id)
        display_name = (
            f"@{chat_member.user.username}"
            if chat_member.user.username
            else chat_member.user.full_name
        )
    except:
        display_name = f"ID {user_id}"

    await bot.send_message(
        REQUIRED_CHAT_ID,
        f"🛸 {display_name} записался на тренировку <b>{date_fmt}</b>\n"
        f"Осталось мест: {free_slots}/{TOTAL_SLOTS}",
        parse_mode="HTML"
    )

    # 5️⃣ уведомление админам
    for admin in ADMINS:
        await bot.send_message(
            admin,
        (    
            f"✅ {display_name} записался на тренировку:\n"
            f"📅 {date_fmt}\n"
            f"🏁 <b>{group_label}</b>\n"
            f"📡 Канал: <b>{channel}</b>\n"
            f"💳 Оплата СБП\n"
        ),
            parse_mode="HTML"
        )
async def handle_subscription_payment(
    *,
    bot,
    payment_id: int,
    user_id: int,
    chat_id: int,
    message_id: int,
    subscription_id: int
):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.count, u.subscription
            FROM subscriptions s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.id = ?
        """, (subscription_id,))
        row = cursor.fetchone()

    if not row:
        return

    count, total = row

    # 1️⃣ обновляем сообщение оплаты
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            f"🎟 <b>Абонемент оплачен</b>\n"
            f"📦 Добавлено: <b>{count}</b>\n"
            f"📊 Всего доступно: <b>{total}</b>"
        ),
        parse_mode="HTML"
    )

    # 2️⃣ получаем display_name (КАК В СЛОТАХ)
    try:
        chat_member = await bot.get_chat_member(user_id, user_id)
        display_name = (
            f"@{chat_member.user.username}"
            if chat_member.user.username
            else chat_member.user.full_name
        )
    except:
        display_name = f"ID {user_id}"

    # 3️⃣ уведомление админам
    for admin in ADMINS:
        await bot.send_message(
            admin,
            (
                f"🎟 <b>Оплачен абонемент</b>\n"
                f"👤 {display_name}\n"
                f"📦 Куплено: <b>{count}</b>\n"
                f"📊 Всего: <b>{total}</b>\n"
                f"🧾 Payment ID: <code>{payment_id}</code>"
            ),
            parse_mode="HTML"
        )
