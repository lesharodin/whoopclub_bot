from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers import registration, profile, admin, booking, participants, subscription
from database.db import init_db
from middlewares.private_only import PrivateChatOnlyMiddleware  # импортируй middleware
from background_tasks import monitor_pending_slots, check_and_send_progrev, monitor_full_trainings
from background_payments import payments_ui_watcher, handle_slot_payment


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
    # Добавляем middleware
    dp.message.middleware(PrivateChatOnlyMiddleware(allowed_chat_commands={"/help", "/participants"}))
    dp.callback_query.middleware(PrivateChatOnlyMiddleware())
    dp.include_router(registration.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)
    dp.include_router(booking.router)
    dp.include_router(participants.router)
    dp.include_router(subscription.router)
    dp.startup.register(on_startup)
    dp.include_router(admin.admin_router)\

    print("🚀 Бот запущен...")
    await dp.start_polling(bot)
async def on_startup(bot: Bot):
    asyncio.create_task(monitor_pending_slots(bot))
    asyncio.create_task(check_and_send_progrev(bot))
    asyncio.create_task(monitor_full_trainings(bot))
    asyncio.create_task(payments_ui_watcher(bot))
    asyncio.create_task(handle_slot_payment(bot))

if __name__ == "__main__":
    asyncio.run(main())