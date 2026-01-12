import requests
import uuid
from datetime import datetime
from config import YOOKASSA_RETURN_URL, YOOKASSA_SECRET_KEY, YOOKASSA_SHOP_ID


YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"


def create_test_payment(slot_id: int, amount_rub: int):
    """
    amount_rub — в рублях (например 800)
    """

    payload = {
        "amount": {
            "value": f"{amount_rub}.00",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL
        },
        "capture": True,
        "description": "Оплата тренировки WhoopClub",
        "metadata": {
            "slot_id": str(slot_id),
            "source": "bot_test"
        },
        "payment_method_data": {
            "type": "bank_card"
        }
    }

    headers = {
        "Idempotence-Key": str(uuid.uuid4())
    }

    response = requests.post(
        YOOKASSA_API_URL,
        json=payload,
        headers=headers,
        auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        timeout=20
    )

    response.raise_for_status()
    return response.json()
