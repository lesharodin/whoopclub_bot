# logging_config.py
import logging
import os

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "debug_booking.log")

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()  # если хочешь также видеть в stdout
    ]
)

logger = logging.getLogger("booking_logger")
