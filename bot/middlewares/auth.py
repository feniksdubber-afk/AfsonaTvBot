from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from bot.database.db import get_db

class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery,
        data: dict
    ) -> Any:
        user = event.from_user
        db = await get_db()

        try:
            # User bazada bormi?
            async with db.execute(
                "SELECT is_banned FROM users WHERE tg_id = ?", (user.id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row is None:
                # Yangi user — bazaga qo'shish
                import secrets
                ref_code = secrets.token_hex(4).upper()
                await db.execute(
                    """INSERT OR IGNORE INTO users 
                       (tg_id, username, full_name, referral_code)
                       VALUES (?, ?, ?, ?)""",
                    (user.id, user.username, user.full_name, ref_code)
                )
                await db.commit()
            elif row[0] == 1:
                # Banned user
                if isinstance(event, Message):
                    await event.answer("🚫 Siz bloklangansiz.")
                return

        finally:
            await db.close()

        return await handler(event, data)
