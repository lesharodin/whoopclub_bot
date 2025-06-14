import os
from dotenv import load_dotenv

load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден! Проверь .env файл.")
    exit(1)

ADMINS = list(map(int, os.getenv("ADMINS", "").split()))
PAYMENT_LINK = os.getenv("PAYMENT_LINK")