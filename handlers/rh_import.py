from aiogram import Router, Bot, F
from aiogram.types import Message
from aiogram.filters.command import Command
from config import ADMINS
from database.db import get_connection
from .rh_extract import process_race_db

from pathlib import Path
import tempfile, aiofiles

router = Router()

@router.message(Command("rh_import"))
async def cmd_upload_results(message: Message):
    if message.from_user.id not in ADMINS:
        await message.reply("⛔ Только админы могут загружать результаты.")
        return

    await message.reply("📥 Отправь файл базы RotorHazard (.db) сообщением в ответ на это.")

@router.message(F.document)
async def handle_rh_database(message: Message, bot: Bot):
    if message.from_user.id not in ADMINS:
        return

    doc = message.document
    if not doc.file_name.endswith(".db"):
        await message.reply("⚠️ Это не .db файл.")
        return

    try:
        temp_path = Path(tempfile.gettempdir()) / doc.file_name

        # Получаем file_id → file_path
        file_info = await bot.get_file(doc.file_id)
        file_data = await bot.download_file(file_info.file_path)

        # Сохраняем файл во временную директорию
        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(file_data.read())

        await message.reply("🔄 Обработка базы…")

        conn = get_connection()
        await process_race_db(str(temp_path), conn)

        await message.reply("✅ Результаты успешно обработаны.")
    except Exception as e:
        await message.reply(f"❌ Ошибка при обработке:\n<pre>{e}</pre>", parse_mode="HTML")