from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from database.db import get_connection
from config import ADMINS, PAYMENT_LINK, REQUIRED_CHAT_ID, CARD
from datetime import datetime, timedelta
from logging_config import logger
from payments.service import create_payment
USE_YOOKASSA = True



router = Router()

# ==========================
# Конфиг групп и каналов
# ==========================

GROUPS = {
    "fast": {
        "label": "⚡ Быстрая",
        "channels": ["R1", "R2", "F2", "F4", "R8"],
    },
    "standard": {
        "label": "🚀 Средняя",
        "channels": ["R1", "R2", "F2", "F4", "R8"],
    },
    "third": {
        "label": "🏁 Стандартная",
        "channels": ["R1", "R2", "F2", "F4", "R8"],
    },
}

# Максимум слотов в каждой группе — по длине списка каналов
MAX_SLOTS_PER_GROUP = {
    name: len(cfg["channels"])
    for name, cfg in GROUPS.items()
}

# Общее количество слотов на тренировку
TOTAL_SLOTS = sum(MAX_SLOTS_PER_GROUP.values())


def get_group_label(group_name: str) -> str:
    """Красивое имя группы по её коду."""
    return GROUPS.get(group_name, {}).get("label", group_name)


@router.message(F.text.contains("Записаться"))
async def show_available_trainings(message: Message):
    user_id = message.from_user.id
    now = datetime.now()

    with get_connection() as conn:
        cursor = conn.cursor()

        cutoff_date = (now - timedelta(hours=1)).isoformat()

        cursor.execute("""
            SELECT t.id, t.date,
                (SELECT COUNT(*) FROM slots WHERE training_id = t.id AND status IN ('pending', 'confirmed')) AS booked_count,
                (SELECT COUNT(*) FROM slots WHERE training_id = t.id AND user_id = ? AND status IN ('pending', 'confirmed')) AS user_booked,
                (SELECT COUNT(*) FROM slots WHERE training_id = t.id AND user_id = ? AND status IN ('pending_cancel')) AS user_pending
            FROM trainings t
            WHERE t.status = 'open' AND t.date > ?
            ORDER BY t.date ASC
            LIMIT 6
        """, (user_id, user_id, cutoff_date))

        trainings = cursor.fetchall()

    if not trainings:
        await message.answer("❌ Пока нет открытых тренировок.")
        return

    total_slots = TOTAL_SLOTS

    keyboard = []
    for training_id, date_str, booked_count, user_booked, user_pending in trainings:
        date_obj = datetime.fromisoformat(date_str)

        weekday_label = ""
        if date_obj.weekday() == 1:
            weekday_label = "Вторник "
        elif date_obj.weekday() == 5:
            weekday_label = "Суббота "

        free_slots = total_slots - (booked_count or 0)
        label = f"{weekday_label}{date_obj.strftime('%d.%m %H:%M')} ({free_slots})"

        if (user_booked or 0) > 0:
            label += " ✅"
        elif (user_pending or 0) > 0:
            label += " ⏳"
        elif (booked_count or 0) >= total_slots:
            label += " ❌"

        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"select_training:{training_id}")])

    await message.answer("Выберите тренировку для записи:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))




@router.callback_query(F.data.startswith("select_training:"))
async def show_group_choice(callback: CallbackQuery, training_id_override: int = None):
    training_id = training_id_override or int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    with get_connection() as conn:
        cursor = conn.cursor()

        # Проверка: уже записан?
        cursor.execute("""
            SELECT COUNT(*) FROM slots
            WHERE training_id = ? AND user_id = ? AND status IN ('pending', 'confirmed', 'pending_cancel')
        """, (training_id, user_id))
        already = cursor.fetchone()[0]

        if already:
            await callback.answer("Вы уже записаны на эту тренировку.", show_alert=True)
            return

        # Получаем кол-во занятых мест в каждой группе
        cursor.execute("""
            SELECT group_name, COUNT(*)
            FROM slots
            WHERE training_id = ? AND status IN ('pending', 'confirmed')
            GROUP BY group_name
        """, (training_id,))
        counts = dict(cursor.fetchall())

        # Формируем список кнопок по всем группам из конфига
        buttons = []
        total_free = 0
        for group_name, cfg in GROUPS.items():
            used = counts.get(group_name, 0)
            free = MAX_SLOTS_PER_GROUP[group_name] - used
            free = max(free, 0)
            total_free += free
            buttons.append(
                InlineKeyboardButton(
                    text=f"{cfg['label']} ({free})",
                    callback_data=f"book:{training_id}:{group_name}"
                )
            )

        if total_free <= 0:
            await callback.answer("Мест не осталось ❌", show_alert=True)
            return

        # Получение даты тренировки
        cursor.execute("SELECT date FROM trainings WHERE id = ?", (training_id,))
        row = cursor.fetchone()

    if not row:
        await callback.message.edit_text("❌ Тренировка не найдена.")
        return

    date_str = datetime.fromisoformat(row[0]).strftime("%d.%m.%Y %H:%M")

    # Раскладываем кнопки по 2 в ряд
    rows = []
    row_buttons: list[InlineKeyboardButton] = []
    for btn in buttons:
        row_buttons.append(btn)
        if len(row_buttons) == 2:
            rows.append(row_buttons)
            row_buttons = []
    if row_buttons:
        rows.append(row_buttons)

    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_trainings")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    await callback.message.edit_text(f"📅 Тренировка {date_str}\n\nВыбери группу:", reply_markup=keyboard)


#Кнопки Назад
@router.callback_query(F.data == "back_to_trainings")
async def back_to_trainings(callback: CallbackQuery):
    user_id = callback.from_user.id
    now = datetime.now()

    with get_connection() as conn:
        cursor = conn.cursor()

        cutoff_date = (now - timedelta(hours=1)).isoformat()

        cursor.execute("""
            SELECT t.id, t.date,
                (SELECT COUNT(*) FROM slots WHERE training_id = t.id AND status IN ('pending', 'confirmed')) AS booked_count,
                (SELECT COUNT(*) FROM slots WHERE training_id = t.id AND user_id = ? AND status IN ('pending', 'confirmed')) AS user_booked
            FROM trainings t
            WHERE t.status = 'open' AND datetime(t.date) > ?
            ORDER BY t.date ASC
            LIMIT 6
        """, (user_id, cutoff_date))

        trainings = cursor.fetchall()

    if not trainings:
        await callback.message.edit_text("❌ Пока нет открытых тренировок.")
        return

    total_slots = 12
    keyboard = []
    for training_id, date_str, booked_count, user_booked in trainings:
        date_obj = datetime.fromisoformat(date_str)
        weekday_label = "Вторник " if date_obj.weekday() == 1 else "Суббота " if date_obj.weekday() == 5 else ""
        free_slots = total_slots - (booked_count or 0)
        label = f"{weekday_label}{date_obj.strftime('%d.%m %H:%M')} ({free_slots})"
        if (user_booked or 0) > 0:
            label += " ✅"
        elif (booked_count or 0) >= total_slots:
            label += " ❌"
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"select_training:{training_id}")])

    await callback.message.edit_text("Выберите тренировку для записи:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data.startswith("back_to_groups:"))
async def back_to_groups(callback: CallbackQuery):
    training_id = int(callback.data.split(":")[1])
    await show_group_choice(callback=callback, training_id_override=training_id)
# Бронирование
@router.callback_query(F.data.startswith("book:"))
async def choose_channel(callback: CallbackQuery):
    _, training_id, group = callback.data.split(":")
    training_id = int(training_id)

    all_channels = GROUPS.get(group, {}).get("channels")
    if not all_channels:
        await callback.message.edit_text("❌ Неизвестная группа.")
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        # Получение даты тренировки
        cursor.execute("SELECT date FROM trainings WHERE id = ?", (training_id,))
        row = cursor.fetchone()

        if not row:
            await callback.message.edit_text("❌ Тренировка не найдена.")
            return

        date_str = datetime.fromisoformat(row[0]).strftime("%d.%m.%Y %H:%M")
        cursor.execute("""
            SELECT channel FROM slots
            WHERE training_id = ? AND group_name = ? AND status IN ('pending', 'confirmed')
        """, (training_id, group))
        taken = [r[0] for r in cursor.fetchall()]

    available = [ch for ch in all_channels if ch not in taken]

    if not available:
        await callback.message.edit_text("❌ В этой группе нет свободных каналов.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ch, callback_data=f"reserve:{training_id}:{group}:{ch}")]
            for ch in available
        ] + [
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_groups:{training_id}")]
        ]
    )

    group_label = get_group_label(group)

    await callback.message.edit_text(
        f"📅 Тренировка {date_str} \n\n 🧩 Свободные каналы в группе <b>{group_label}</b>:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("reserve:"))
async def reserve_slot(callback: CallbackQuery):
    _, training_id, group, channel = callback.data.split(":")
    training_id = int(training_id)
    user_id = callback.from_user.id
    username = callback.from_user.username
    full_name = callback.from_user.full_name

    # Проверка: канал занят
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM slots
            WHERE training_id = ? AND group_name = ? AND channel = ? AND status IN ('pending', 'confirmed')
        """, (training_id, group, channel))
        taken = cursor.fetchone()[0]

        if taken:
            await callback.answer("Этот канал уже занят другим участником.", show_alert=True)
            return

        # Получаем дату тренировки
        cursor.execute("SELECT date FROM trainings WHERE id = ?", (training_id,))
        row = cursor.fetchone()
        if not row:
            await callback.message.edit_text("❌ Ошибка: тренировка не найдена.")
            return

        date_str = row[0]
        date_fmt = datetime.fromisoformat(date_str).strftime("%d.%m.%Y %H:%M")

        # Проверяем абонемент
        cursor.execute("SELECT subscription FROM users WHERE user_id = ?", (user_id,))
        sub_row = cursor.fetchone()
        sub_count = sub_row[0] if sub_row else 0

        if sub_count > 0:
            payment_type = "subscription"
            status = "confirmed"
        else:
            payment_type = "yookassa" if USE_YOOKASSA else "manual"
            status = "pending"

        # Регистрируем слот
        cursor.execute("""
            INSERT INTO slots (training_id, user_id, group_name, channel, status, created_at, payment_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            training_id,
            user_id,
            group,
            channel,
            status,
            datetime.now().isoformat(),
            payment_type
        ))
        slot_id = cursor.lastrowid

        # Списываем абонемент до commit
        if payment_type == "subscription":
            cursor.execute("UPDATE users SET subscription = subscription - 1 WHERE user_id = ?", (user_id,))

        conn.commit()

    group_label = get_group_label(group)

    if payment_type == "subscription":
        # Подсчёт оставшихся мест
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM slots
                WHERE training_id = ? AND status = 'confirmed'
            """, (training_id,))
            booked = cursor.fetchone()[0]
            free_slots = TOTAL_SLOTS - booked

            cursor.execute("SELECT subscription FROM users WHERE user_id = ?", (user_id,))
            sub_row = cursor.fetchone()
            sub_left = sub_row[0] if sub_row else 0

        await callback.message.edit_text(
            f"📅 <b>Тренировка {date_fmt}</b>\n"
            f"✅ Вы забронировали <b>{channel}</b> в группе <b>{group_label}</b>.\n"
            f"<i>Оплата через абонемент. Запись подтверждена автоматически.</i>\n"
            f"🎟 Осталось абонементов: <b>{sub_left}</b>"
        )

        await callback.bot.send_message(
            REQUIRED_CHAT_ID,
            f"🛸 {'@' + username if username else full_name} записался на тренировку <b>{date_fmt}</b>\n"
            f"Осталось мест: {free_slots}/{TOTAL_SLOTS}",
            parse_mode="HTML"
        )

        for admin in ADMINS:
            await callback.bot.send_message(
                admin,
                f"✅ {'@' + username if username else full_name} записался через абонемент:\n"
                f"📅 {date_fmt}\n"
                f"🏁 <b>{group_label}</b>\n"
                f"📡 Канал: <b>{channel}</b>\n"
                f"🎟 Осталось абонементов: <b>{sub_left}</b>",
                parse_mode="HTML"
            )

    elif payment_type == "yookassa":
        # 1️⃣ создаём payment СРАЗУ
        payer = f"@{username}" if username else full_name
        payment_url = create_payment(
            user_id=user_id,
            amount=1000,
            target_type="slot",
            target_id=slot_id,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,  # временно, обновим ниже
            payment_method="sbp",
            description = f"WhoopClub разовая тренировка| slot:{slot_id} | {payer}"
        )

        # 2️⃣ клавиатура С РЕАЛЬНЫМ URL
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Оплатить (СБП)",
                    url=payment_url
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить запись",
                    callback_data=f"user_cancel_pending:{slot_id}"
                )
            ]
        ])

        # 3️⃣ редактируем сообщение
        msg = await callback.message.edit_text(
            f"📅 <b>Тренировка {date_fmt}</b>\n"
            f"✅ Вы забронировали <b>{channel}</b> в группе <b>{group_label}</b>.\n\n"
            f"💳 Оплатите участие через СБП.\n"
            f"⏳ Запись будет подтверждена автоматически после оплаты.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        # 4️⃣ обновляем message_id в payments (ВАЖНО)
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE payments SET message_id = ? WHERE target_type='slot' AND target_id = ? AND status='pending'",
                (msg.message_id, slot_id)
            )
            conn.commit()


    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"confirm_payment:{slot_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"user_cancel_pending:{slot_id}")
            ]
        ])

        await callback.message.edit_text(
            f"📅 <b>Тренировка {date_fmt}</b>\n"
            f"✅ Вы забронировали <b>{channel}</b> в группе <b>{group_label}</b>.\n"
            f"💳 Пожалуйста, оплатите <b>1000₽</b> по ссылке: <a href='{PAYMENT_LINK}'>ОПЛАТИТЬ</a>\n"
            f"Либо по номеру карты <code>{CARD}</code>\n"
            f"После оплаты нажмите кнопку ниже.",
            reply_markup=keyboard
        )
@router.callback_query(F.data.startswith("user_cancel_pending:"))
async def user_cancel_pending(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    with get_connection() as conn:
        cursor = conn.cursor()
        # Проверка: слот существует, принадлежит пользователю и в статусе pending
        cursor.execute("""
            SELECT training_id FROM slots
            WHERE id = ? AND user_id = ? AND status = 'pending'
        """, (slot_id, user_id))
        row = cursor.fetchone()

        if not row:
            await callback.answer("Нельзя отменить: слот уже подтверждён или не найден.", show_alert=True)
            return

        # Удаляем слот
        cursor.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
        conn.commit()

    await callback.message.edit_text("❌ Ваша бронь отменена. Вы можете выбрать другую тренировку или группу.")


@router.callback_query(F.data.startswith("confirm_payment:"))
async def confirm_manual_payment(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    username = callback.from_user.username
    full_name = callback.from_user.full_name
    
    logger.info("[confirm_manual_payment] callback.from_user")
    logger.info(f"  slot_id: {slot_id}")
    logger.info(f"  user_id: {user_id}")
    logger.info(f"  username: {username}")
    logger.info(f"  full_name: {full_name}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.training_id, s.group_name, s.channel, t.date
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            WHERE s.id = ?
        """, (slot_id,))
        row = cursor.fetchone()

    if not row:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    training_id, group, channel, date_str = row
    logger.info("[confirm_manual_payment] данные из базы:")
    logger.info(f"  training_id: {training_id}")
    logger.info(f"  group: {group}")
    logger.info(f"  channel: {channel}")
    logger.info(f"  date_str: {date_str}")
    await notify_admins_about_booking(
        bot=callback.bot,
        training_id=training_id,
        user_id=user_id,
        group=group,
        channel=channel,
        slot_id=slot_id,
        username=username,
        payment_type="manual",
        full_name=callback.from_user.full_name,
        date_str=date_str
    )

    await callback.message.edit_text("🔔 Администратор уведомлён. Ожидайте подтверждения оплаты.")


async def notify_admins_about_booking(bot, training_id, user_id, group, channel, slot_id, username, payment_type, full_name, date_str):
    logger.info("[notify_admins_about_booking]")
    logger.info(f"  user_id: {user_id}")
    logger.info(f"  username: {username}")
    logger.info(f"  full_name: {full_name}")
    logger.info(f"  date_str: {date_str}")

    if username and "20" in username and ":" in username:
        logger.warning(f"⚠️ ПОДОЗРИТЕЛЬНЫЙ USERNAME: {username} — похоже, это дата!")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, system, subscription FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

    nickname = user[0] if user else "-"
    system = user[1] if user else "-"
    remaining = user[2] if user else 0

    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{full_name}</a>"

    payment_desc = "🎟 Абонемент" if payment_type == "subscription" else "💳 Реквизиты"
    if payment_type == "subscription":
        payment_desc += f" (осталось {remaining})"

    date_fmt = datetime.fromisoformat(date_str).strftime("%d.%m.%Y %H:%M")
    group_label = get_group_label(group)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{slot_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{slot_id}")
    ]])

    text = (
        f"📥 Новая запись на тренировку:\n"
        f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
        f"📅 Дата: <b>{date_fmt}</b>\n"
        f"🏁 Группа: <b>{group_label}</b>\n"
        f"📡 Канал: <b>{channel}</b>\n"
        f"🎮 OSD: <b>{nickname}</b>\n"
        f"🎥 Видео: <b>{system}</b>\n"
        f"{payment_desc}\n"
        f"⏳ Ожидает подтверждения оплаты"
    )

    for admin in ADMINS:
        msg = await bot.send_message(admin, text, reply_markup=kb, parse_mode="HTML")
        # сохраняем id отправленного сообщения
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO admin_notifications (slot_id, admin_id, message_id)
                VALUES (?, ?, ?)
            """, (slot_id, admin, msg.message_id))
            conn.commit()



@router.callback_query(F.data.startswith("confirm:"))
async def confirm_booking(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])

    with get_connection() as conn:
        cursor = conn.cursor()

        # Получаем все необходимые данные
        cursor.execute("""
            SELECT s.user_id, s.group_name, s.channel, s.payment_type, t.date, u.nickname, u.system
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            JOIN users u ON s.user_id = u.user_id
            WHERE s.id = ?
        """, (slot_id,))
        row = cursor.fetchone()

    if not row:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    user_id, group, channel, payment_type, training_date, nickname, system = row

    # ✅ Подтверждение и списание абонемента
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE slots SET status = 'confirmed' WHERE id = ?", (slot_id,))
        if payment_type == "subscription":
            cursor.execute("UPDATE users SET subscription = subscription - 1 WHERE user_id = ?", (user_id,))
        conn.commit()

    date_fmt = datetime.fromisoformat(training_date).strftime("%d.%m.%Y %H:%M")
    await callback.message.edit_text("✅ Оплата подтверждена")
    await callback.bot.send_message(user_id, f"✅ Ваша запись подтверждена! Ждём вас на тренировке {date_fmt}🛸")

    # ✅ Получаем username и имя участника (не админа)
    try:
        chat_member = await callback.bot.get_chat_member(chat_id=user_id, user_id=user_id)
        full_name = chat_member.user.full_name
        username = chat_member.user.username
    except:
        full_name = "Пользователь"
        username = None

    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{full_name}</a>"

    # 📨 Формируем сообщение админу
    group_label = get_group_label(group)
    payment_text = "🎟 Абонемент" if payment_type == "subscription" else "💳 Оплата по реквизитам"
    
    admin_name = callback.from_user.full_name

    admin_message = (
        f"✅ Запись подтверждена админом <b>{admin_name}</b>:\n"
        f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
        f"📅 Дата: <b>{date_fmt}</b>\n"
        f"🏁 Группа: <b>{group_label}</b>\n"
        f"📡 Канал: <b>{channel}</b>\n"
        f"🎮 OSD: <b>{nickname}</b>\n"
        f"🎥 Видео: <b>{system}</b>\n"
        f"{payment_text}"
    )
    # Удаляем сообщения с кнопками у всех админов
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT admin_id, message_id FROM admin_notifications WHERE slot_id = ?", (slot_id,))
        messages = cursor.fetchall()
        cursor.execute("DELETE FROM admin_notifications WHERE slot_id = ?", (slot_id,))
        conn.commit()

    for admin_id, message_id in messages:
        try:
            await callback.bot.delete_message(chat_id=admin_id, message_id=message_id)
        except:
            pass  # сообщение могло быть уже удалено или скрыто

    # Подсчёт оставшихся мест
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM slots
            WHERE training_id = (SELECT training_id FROM slots WHERE id = ?) AND status IN ('confirmed')
        """, (slot_id,))
        booked = cursor.fetchone()[0]
    free_slots = TOTAL_SLOTS - booked

    # Уведомление в клубный чат
    if username:
        display_name = f"@{username}"
    else:
        display_name = full_name

    await callback.bot.send_message(
        REQUIRED_CHAT_ID,
        f"🛸 {display_name} записался на тренировку <b>{date_fmt}</b>\n"
        f"Осталось мест: {free_slots}/{TOTAL_SLOTS}"
    )
        
    for admin in ADMINS:
        await callback.bot.send_message(admin, admin_message, parse_mode="HTML")


@router.callback_query(F.data.startswith("reject:"))
async def reject_booking(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])
    with get_connection() as conn:
        cursor = conn.cursor()

        # Получаем данные о слоте и пользователе
        cursor.execute("""
            SELECT s.user_id, s.status, s.group_name, s.channel, s.payment_type, t.date,
                   u.nickname, u.system
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            JOIN users u ON s.user_id = u.user_id
            WHERE s.id = ?
        """, (slot_id,))
        row = cursor.fetchone()

        if not row:
            await callback.answer("❌ Запись не найдена.", show_alert=True)
            return

        user_id, status, group, channel, payment_type, training_date, nickname, system = row

        if status == "confirmed":
            await callback.answer("❗ Эта запись уже подтверждена другим админом.", show_alert=True)
            return

        # Удаляем запись
        cursor.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
        conn.commit()

        # Уведомление пользователя
        await callback.message.edit_text("❌ Запись отклонена")
        await callback.bot.send_message(user_id, "❌ Ваша запись была отклонена. Попробуйте снова или свяжитесь с админом.")

        # Получаем имя и username пользователя
        try:
            chat_member = await callback.bot.get_chat_member(chat_id=user_id, user_id=user_id)
            full_name = chat_member.user.full_name
            username = chat_member.user.username
        except:
            full_name = "Пользователь"
            username = None

        user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{full_name}</a>"
        admin_name = callback.from_user.full_name

        # Формируем лог для админов
        group_label = get_group_label(group)
        date_fmt = datetime.fromisoformat(training_date).strftime("%d.%m.%Y %H:%М")
        payment_text = "🎟 Абонемент" if payment_type == "subscription" else "💳 Оплата по реквизитам"

        admin_message = (
            f"❌ Запись отклонена админом <b>{admin_name}</b>:\n"
            f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
            f"📅 Дата: <b>{date_fmt}</b>\n"
            f"🏁 Группа: <b>{group_label}</b>\n"
            f"📡 Канал: <b>{channel}</b>\n"
            f"🎮 OSD: <b>{nickname}</b>\n"
            f"🎥 Видео: <b>{system}</b>\n"
            f"{payment_text}"
        )
        # Удаляем сообщения с кнопками у всех админов
        with get_connection() as conn2:
            cursor2 = conn2.cursor()
            cursor2.execute("SELECT admin_id, message_id FROM admin_notifications WHERE slot_id = ?", (slot_id,))
            messages = cursor2.fetchall()
            cursor2.execute("DELETE FROM admin_notifications WHERE slot_id = ?", (slot_id,))
            conn2.commit()

        for admin_id, message_id in messages:
            try:
                await callback.bot.delete_message(chat_id=admin_id, message_id=message_id)
            except:
                pass  # сообщение могло быть уже удалено или скрыто
        # Рассылка всем админам
        for admin in ADMINS:
            await callback.bot.send_message(admin, admin_message, parse_mode="HTML")

@router.message(F.text.contains("Мои записи"))
async def show_my_bookings(message: Message):
    user_id = message.from_user.id

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.date, s.group_name, s.channel, s.status
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            WHERE s.user_id = ? AND t.status != 'cancelled'
            ORDER BY t.date ASC
        """, (user_id,))
        rows = cursor.fetchall()

    if not rows:
        await message.answer("📭 У вас пока нет записей на тренировки.")
        return

    lines = ["📅 Ваши записи на тренировки:\n\n"]
    for date_str, group, channel, status in rows:
        date_fmt = datetime.fromisoformat(date_str).strftime("%d.%m.%Y %H:%M")
        group_label = get_group_label(group)
        if status == "pending":
            status_label = "⏳ Ожидает"
        elif status == "pending_cancel":
            status_label = "⏳ Запрос отмены"
        else:
            status_label = "✅ Подтверждена"
        lines.append(f"— {date_fmt} | {group_label} | {channel} | {status_label}\n\n")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить запись", callback_data="cancel_booking_menu")]
    ])

    await message.answer("".join(lines), reply_markup=keyboard)

#отмена тренировки

@router.callback_query(F.data == "cancel_booking_menu")
async def show_user_bookings_to_cancel(callback: CallbackQuery):
    user_id = callback.from_user.id
    now = datetime.now()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, t.date
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            WHERE s.user_id = ? AND s.status = 'confirmed' AND t.date > ? AND t.status != 'cancelled'
            ORDER BY t.date ASC
        """, (user_id, now.isoformat()))
        bookings = cursor.fetchall()

    if not bookings:
        await callback.message.edit_text("❌ У вас нет активных записей для отмены.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=datetime.fromisoformat(date).strftime("%d.%m %H:%M"),
                callback_data=f"ask_cancel:{slot_id}"
            )]
            for slot_id, date in bookings
        ]
    )

    await callback.message.edit_text("Выберите запись, которую хотите отменить:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("ask_cancel:"))
async def ask_to_cancel(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.date FROM slots s
            JOIN trainings t ON s.training_id = t.id
            WHERE s.id = ?
        """, (slot_id,))
        row = cursor.fetchone()

    if not row:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    training_date = datetime.fromisoformat(row[0])
    now = datetime.now()
    hours_before = (training_date - now).total_seconds() / 3600

    text = (
        f"📅 Тренировка {training_date.strftime('%d.%m %H:%M')}\n\n"
        f"❓ Вы уверены, что хотите отменить запись?\n\n"
        f"{'💸 Абонемент будет возвращён.' if hours_before > 24 else '⚠️ Меньше 24 часов до тренировки — абонемент не вернётся, средства уйдут в донат.'}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отменить", callback_data=f"confirm_cancel:{slot_id}"),
            InlineKeyboardButton(text="❌ Назад", callback_data="cancel")
        ]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(F.data.startswith("confirm_cancel:"))
async def confirm_cancel_request(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.payment_type, t.date, s.group_name, s.channel,
                   u.nickname, u.system, t.id
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            JOIN users u ON s.user_id = u.user_id
            WHERE s.id = ? AND s.user_id = ? AND s.status = 'confirmed'
        """, (slot_id, user_id))
        row = cursor.fetchone()

        if not row:
            await callback.answer("Запись не найдена", show_alert=True)
            return

        payment_type, training_date, group, channel, nickname, system, training_id = row

        now = datetime.now()
        training_dt = datetime.fromisoformat(training_date)
        hours_before = (training_dt - now).total_seconds() / 3600

        cursor.execute("DELETE FROM slots WHERE id = ?", (slot_id,))

        if hours_before > 24:
            cursor.execute("UPDATE users SET subscription = subscription + 1 WHERE user_id = ?", (user_id,))
            refund_text = "🎟 Абонемент возвращён."
        else:
            refund_text = "💸 Меньше 24 часов — абонемент не возвращается, средства ушли в донат клуба."

        conn.commit()

    date_fmt = datetime.fromisoformat(training_date).strftime("%d.%m.%Y %H:%M")
    group_label = get_group_label(group)
    payment_text = "🎟 Абонемент" if payment_type == "subscription" else "💳 Оплата по реквизитам"
    username = callback.from_user.username
    full_name = callback.from_user.full_name
    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{full_name}</a>"

    admin_log = (
        f"❎ Запись отменена пользователем (без подтверждения админом)\n"
        f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
        f"📅 Дата: <b>{date_fmt}</b>\n"
        f"🏁 Группа: <b>{group_label}</b>\n"
        f"📡 Канал: <b>{channel}</b>\n"
        f"🎮 OSD: <b>{nickname}</b>\n"
        f"🎥 Видео: <b>{system}</b>\n"
        f"{payment_text}\n"
        f"{refund_text}"
    )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM slots
            WHERE training_id = ? AND status = 'confirmed'
        """, (training_id,))
        booked = cursor.fetchone()[0]

    free_slots = TOTAL_SLOTS - booked

    await callback.message.edit_text(f"✅ Запись отменена.\n{refund_text}")

    await callback.bot.send_message(
        REQUIRED_CHAT_ID,
        f"🚪 Освободилось место на тренировке <b>{date_fmt}</b>!\n"
        f"Осталось мест: {free_slots}/{TOTAL_SLOTS}",
        parse_mode="HTML"
    )

    for admin in ADMINS:
        await callback.bot.send_message(admin, admin_log, parse_mode="HTML")

@router.callback_query(F.data.startswith("admin_cancel:"))
async def admin_confirm_cancel(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])
    admin_name = callback.from_user.full_name

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.user_id, s.payment_type, t.date, s.group_name, s.channel,
                   u.nickname, u.system, t.id
            FROM slots s
            JOIN trainings t ON s.training_id = t.id
            JOIN users u ON s.user_id = u.user_id
            WHERE s.id = ? AND s.status = 'pending_cancel'
        """, (slot_id,))
        row = cursor.fetchone()

        if not row:
            await callback.answer("Запись не найдена или уже обработана.", show_alert=True)
            return

        user_id, payment_type, training_date, group, channel, nickname, system, training_id = row

        # Считаем, сколько часов до тренировки
        now = datetime.now()
        training_dt = datetime.fromisoformat(training_date)
        hours_before = (training_dt - now).total_seconds() / 3600

        # Удаляем слот
        cursor.execute("DELETE FROM slots WHERE id = ?", (slot_id,))

        # Возвращаем абонемент только если больше 24 часов
        refund_text = ""
        if hours_before > 24:
            cursor.execute("UPDATE users SET subscription = subscription + 1 WHERE user_id = ?", (user_id,))
            refund_text = "🎟 Абонемент возвращён."
        else:
            refund_text = "💸 Меньше 24 часов — абонемент не возвращается, средства ушли в донат клуба."

        conn.commit()

        # Удаляем сообщения с кнопками отмены у всех админов
        cursor.execute("SELECT admin_id, message_id FROM admin_notifications WHERE slot_id = ?", (slot_id,))
        messages = cursor.fetchall()
        cursor.execute("DELETE FROM admin_notifications WHERE slot_id = ?", (slot_id,))
        conn.commit()

    for admin_id, message_id in messages:
        try:
            await callback.bot.delete_message(chat_id=admin_id, message_id=message_id)
        except:
            pass

    if callback.message:
        try:
            await callback.message.edit_text("✅ Запись отменена. Пользователь уведомлён.")
        except:
            pass
    await callback.bot.send_message(user_id, f"❌ Ваша запись отменена.\n{refund_text}")
    # Формируем лог админу
    date_fmt = datetime.fromisoformat(training_date).strftime("%d.%m.%Y %H:%M")
    group_label = get_group_label(group)
    payment_text = "🎟 Абонемент" if payment_type == "subscription" else "💳 Оплата по реквизитам"
    
    try:
        chat_member = await callback.bot.get_chat_member(chat_id=user_id, user_id=user_id)
        full_name = chat_member.user.full_name
        username = chat_member.user.username
    except:
        full_name = "Пользователь"
        username = None

    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{full_name}</a>"

    admin_log = (
        f"❎ Отмена подтверждена админом <b>{admin_name}</b>\n"
        f"👤 {user_link} (ID: <code>{user_id}</code>)\n"
        f"📅 Дата: <b>{date_fmt}</b>\n"
        f"🏁 Группа: <b>{group_label}</b>\n"
        f"📡 Канал: <b>{channel}</b>\n"
        f"🎮 OSD: <b>{nickname}</b>\n"
        f"🎥 Видео: <b>{system}</b>\n"
        f"{payment_text}\n"
        f"{refund_text}"
    )
    # Подсчёт оставшихся мест
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM slots
            WHERE training_id = ? AND status = 'confirmed'
        """, (training_id,))
        booked = cursor.fetchone()[0]
    free_slots = TOTAL_SLOTS - booked

    # Уведомление в клубный чат
    await callback.bot.send_message(
        REQUIRED_CHAT_ID,
        f"🚪 Освободилось место на тренировке <b>{date_fmt}</b>!\n"
        f"Осталось мест: {free_slots}/{TOTAL_SLOTS}",
        parse_mode="HTML"
    )

    for admin in ADMINS:
        await callback.bot.send_message(admin, admin_log, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_reject_cancel:"))
async def admin_reject_cancel(callback: CallbackQuery):
    slot_id = int(callback.data.split(":")[1])

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE slots SET status = 'confirmed' WHERE id = ? AND status = 'pending_cancel'", (slot_id,))
        if cursor.rowcount == 0:
            await callback.answer("Запись не найдена или уже обработана.", show_alert=True)
            return
        conn.commit()

    await callback.message.edit_text("❌ Отмена записи отклонена.")
