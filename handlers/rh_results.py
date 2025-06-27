from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_connection

router = Router()

@router.message(F.text.contains("Результаты"))
async def show_results_menu(message: Message):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT training_date FROM training_scores
        ORDER BY training_date DESC
    """)
    dates = [row[0] for row in cursor.fetchall()]
    
    if not dates:
        await message.answer("❌ Пока нет доступных результатов.")
        return

    buttons = [
        [InlineKeyboardButton(text=date, callback_data=f"results:{date}")]
        for date in dates
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer("📊 Выбери тренировку для просмотра результатов:", reply_markup=markup)


@router.callback_query(F.data.startswith("results:"))
async def show_selected_results(callback: CallbackQuery):
    selected_date = callback.data.split(":")[1]
    conn = get_connection()
    cursor = conn.cursor()

    await callback.message.delete()
    await callback.message.answer("🔄 Загружаем результаты...")

    cursor.execute("""
        SELECT pilot_name, group_name, best_lap, best_3_laps, total_laps, score_total
        FROM training_scores
        WHERE training_date = ?
        ORDER BY group_name, score_total DESC
    """, (selected_date,))
    rows = cursor.fetchall()

    if not rows:
        await callback.message.answer("⚠️ Нет данных о результатах.")
        return

    # Блок: Твои результаты
    tg_user_id = callback.from_user.id
    cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (tg_user_id,))
    res = cursor.fetchone()
    your_osd = res[0] if res else None

    personal_block = ""
    if your_osd:
        cursor.execute("""
            SELECT best_lap, best_lap_race_id, best_lap_order,
                   best_3_laps, best_3_race_id, best_3_start_order,
                   total_laps
            FROM training_scores
            WHERE training_date = ? AND pilot_name = ?
        """, (selected_date, your_osd))
        data = cursor.fetchone()
        if data:
            best_lap, lap_race, lap_order, best3, best3_race, best3_start = data[:6]
            total_laps = data[6]
            personal_block = (
                "<b>Твои результаты:</b>\n"
                f"• лучший круг в раунде #{lap_race}, круг {lap_order} — {best_lap:.3f}s\n"
                f"• 3 круга подряд в раунде #{best3_race}, с круга {best3_start} — {best3:.3f}s\n"
                f"• всего кругов: {total_laps}\n\n"
            )

    text = f"🏁 <b>Результаты тренировки {selected_date}</b>\n\n"
    text += personal_block

    # Группировка и отображение
    def render_group(group_rows, group_name):
        if not group_rows:
            return ""

        min_best_lap = min(r[2] for r in group_rows)
        min_best_3 = min(r[3] for r in group_rows)
        max_total_laps = max(r[4] for r in group_rows)

        if group_name == "Группа 1":
            group_title = "⚡️ Быстрая группа"
        elif group_name == "Группа 2":
            group_title = "🏁 Стандартная группа"
        else:
            group_title = f"Группа: {group_name}"

        out = f"\n<b>{group_title}</b>\n\n"
        for i, (pilot_name, _, best_lap, best_3, total_laps, score_total) in enumerate(group_rows, start=1):
            lap = f"🔥{best_lap:.3f}s" if best_lap == min_best_lap else f"{best_lap:.3f}s"
            laps3 = f"🔥{best_3:.3f}s" if best_3 == min_best_3 else f"{best_3:.3f}s"
            total = f"🔥{total_laps}" if total_laps == max_total_laps else f"{total_laps}"
            crown = " 👑" if (best_lap == min_best_lap and best_3 == min_best_3 and total_laps == max_total_laps) else ""

            out += f"{i}. <b>{pilot_name}</b>{crown}\n"
            out += f"{lap} | {laps3} | {total} | +{score_total}\n"

        return out

    current_group = None
    group_rows = []

    for row in rows:
        group = row[1]
        if group != current_group:
            if group_rows:
                text += render_group(group_rows, current_group)
                group_rows = []
            current_group = group
        group_rows.append(row)

    text += render_group(group_rows, current_group)
    await callback.message.answer(text.strip(), parse_mode="HTML")
