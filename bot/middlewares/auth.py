"""
AuthMiddleware
──────────────
1. Yangi foydalanuvchini bazaga qo'shadi
2. Banlangan foydalanuvchini to'xtatadi
3. `data["lang"]` ni o'rnatadi (SubscriptionMiddleware uchun kerak)
"""

import secrets
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

        async with get_db() as db:
            async with db.execute(
                "SELECT is_banned, lang FROM users WHERE tg_id = ?", (user.id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row is None:
                # Yangi foydalanuvchi — bazaga qo'shish
                ref_code = secrets.token_hex(4).upper()
                await db.execute(
                    """INSERT OR IGNORE INTO users
                       (tg_id, username, full_name, referral_code)
                       VALUES (?, ?, ?, ?)""",
                    (user.id, user.username, user.full_name, ref_code)
                )
                await db.commit()
                lang = "uz"
            else:
                is_banned, lang = row[0], row[1]

                if is_banned:
                    if isinstance(event, Message):
                        await event.answer("🚫 Siz bloklangansiz.")
                    elif isinstance(event, CallbackQuery):
                        await event.answer("🚫 Siz bloklangansiz.", show_alert=True)
                    return

        # lang ni keyingi middleware va handlerlarga uzatamiz
        data["lang"] = lang or "uz"

        return await handler(event, data)
