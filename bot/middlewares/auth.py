"""
AuthMiddleware
──────────────
1. Yangi foydalanuvchini bazaga qo'shadi
2. Banlangan foydalanuvchini to'xtatadi
3. data["lang"] ni o'rnatadi (SubscriptionMiddleware uchun kerak)

TUZATILGAN:
  - InlineQuery ham qo'llab-quvvatlanadi (main.py da middleware ulanishi kerak)
  - from_user None bo'lsa (bot xabari, kanal post): xavfsiz o'tkazib yuboriladi
  - DB xatosi bo'lsa: handler blokllamaydi, faqat log yoziladi
"""

import logging
import secrets
from typing import Any, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineQuery

from bot.database.db import get_db

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery | InlineQuery,
        data: dict,
    ) -> Any:
        user = event.from_user
        if user is None:
            return await handler(event, data)

        lang = "uz"  # default

        try:
            async with get_db() as db:
                async with db.execute(
                    "SELECT is_banned, lang FROM users WHERE tg_id = ?",
                    (user.id,),
                ) as cursor:
                    row = await cursor.fetchone()

                if row is None:
                    ref_code = secrets.token_hex(4).upper()
                    await db.execute(
                        """INSERT OR IGNORE INTO users
                           (tg_id, username, full_name, referral_code)
                           VALUES (?, ?, ?, ?)""",
                        (user.id, user.username, user.full_name, ref_code),
                    )
                    await db.commit()
                else:
                    is_banned: int = row[0]
                    lang = row[1] or "uz"

                    if is_banned:
                        # InlineQuery uchun ban xabarini yuborib bo'lmaydi — o'tkazib yuboramiz
                        if isinstance(event, Message):
                            await event.answer("🚫 Siz bloklangansiz.")
                        elif isinstance(event, CallbackQuery):
                            await event.answer("🚫 Siz bloklangansiz.", show_alert=True)
                        return

        except Exception as exc:
            logger.error("AuthMiddleware DB xatosi (user_id=%s): %s", user.id, exc)

        data["lang"] = lang
        return await handler(event, data)
