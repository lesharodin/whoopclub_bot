import asyncio

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.client.session.aiohttp import AiohttpSession

from config import BOT_TOKEN, PROXY
from handlers import registration, profile, admin, booking, participants, subscription
from database.db import init_db
from middlewares.private_only import PrivateChatOnlyMiddleware
from background_tasks import monitor_pending_slots, check_and_send_progrev, monitor_full_trainings
from background_payments import payments_ui_watcher


# --- SESSION ---
if PROXY:
    print(f"🌐 Используем прокси: {PROXY}")
    session = AiohttpSession(
        proxy=f"socks5://{PROXY}:1081"
    )
else:
    print("🔌 Работаем без прокси")
    session = AiohttpSession()


# --- BOT (как раньше — глобально) ---
bot = Bot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())


async def on_startup(bot: Bot):
    asyncio.create_task(monitor_pending_slots(bot))
    asyncio.create_task(check_and_send_progrev(bot))
    asyncio.create_task(monitor_full_trainings(bot))
    asyncio.create_task(payments_ui_watcher(bot))


async def on_shutdown(bot: Bot):
    await bot.session.close()


async def main():
    init_db()
    print("✅ Инициализация БД завершена")

    # Middleware
    dp.message.middleware(PrivateChatOnlyMiddleware(allowed_chat_commands={"/help", "/participants"}))
    dp.callback_query.middleware(PrivateChatOnlyMiddleware())

    # Routers
    dp.include_router(registration.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)
    dp.include_router(booking.router)
    dp.include_router(participants.router)
    dp.include_router(subscription.router)
    dp.include_router(admin.admin_router)

    # Lifecycle
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    print("🚀 Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())