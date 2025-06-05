from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers import registration, profile, admin, booking, participants, subscription
from database.db import init_db

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())

import asyncio
from database.db import init_db

async def main():
    init_db()  # ⬅️ Этот вызов должен быть до всего остального!
    print("✅ Инициализация БД завершена")

    dp.include_router(registration.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)
    dp.include_router(booking.router)
    dp.include_router(participants.router)
    dp.include_router(subscription.router)

    print("🚀 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())