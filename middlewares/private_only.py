from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher.middlewares.base import BaseMiddleware

class PrivateChatOnlyMiddleware(BaseMiddleware):
    def __init__(self, allowed_chat_commands: set[str] = None):
        super().__init__()
        self.allowed_chat_commands = allowed_chat_commands or set()

    async def __call__(self, handler, event, data):
        chat_type = event.chat.type if isinstance(event, Message) else event.message.chat.type

        if chat_type != "private":
            if isinstance(event, Message):
                if event.text and any(event.text.startswith(cmd) for cmd in self.allowed_chat_commands):
                    return await handler(event, data)
            return  # игнорируем всё остальное

        return await handler(event, data)
