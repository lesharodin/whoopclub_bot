import os
from dotenv import load_dotenv

print("=== До загрузки .env ===")
print("BOT_TOKEN =", os.getenv("BOT_TOKEN"))

# Загружаем .env
load_dotenv()

print("=== После загрузки .env ===")
print("BOT_TOKEN =", os.getenv("BOT_TOKEN"))

# Альтернативный способ через os.environ.get
print("=== os.environ.get ===")
print("BOT_TOKEN =", os.environ.get("BOT_TOKEN"))
