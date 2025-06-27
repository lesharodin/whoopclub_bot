from aiogram import Router, Bot, F
from aiogram.types import Message, Document
from config import ADMINS
from database.db import get_connection
from handlers.rh_extract import process_race_db, extract_training_date

import tempfile
import os

router = Router()

@router.message(F.document)
async def handle_rh_db_file(message: Message, bot: Bot):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔️ Недостаточно прав для загрузки баз данных.")
        return

    doc = message.document

    if not doc.file_name.endswith(".db"):
        await message.answer("❌ Пожалуйста, отправь файл с расширением .db")
        return

    await message.answer(f"🔄 Обрабатываем базу: {doc.file_name}...")

    try:
        # Сохраняем файл во временное хранилище
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            await bot.download(doc, destination=tmp.name)
            file_path = tmp.name

        # Извлекаем дату
        training_date = extract_training_date(file_path)

        # Работаем с базой и закрываем соединение сразу после
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM training_scores WHERE training_date = ?", (training_date,))
            if cursor.fetchone():
                await message.answer(f"⚠️ База уже была загружена ранее ({training_date}), пропускаем.")
                return

            await process_race_db(file_path, conn)

        await message.answer(f"✅ База {doc.file_name} ({training_date}) успешно обработана.")

    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке:\n{e}")
    finally:
        import time
        time.sleep(0.1)  # Короткая задержка, чтобы ОС освободила файл
        try:
            os.remove(file_path)
        except PermissionError:
            await message.answer("⚠️ Не удалось удалить временный файл — возможно, он ещё используется.")
