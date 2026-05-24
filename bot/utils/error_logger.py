"""
error_logger.py
───────────────
Xatolarni error_logs jadvaliga yozish uchun yordamchi modul.

Ishlatish:
    from bot.utils.error_logger import log_error

    try:
        ...
    except Exception as exc:
        await log_error(exc, handler="my_handler", user_id=123)
"""

import logging
import traceback

from bot.database.db import get_db

logger = logging.getLogger(__name__)


async def log_error(
    exc: Exception,
    handler: str = "",
    user_id: int | None = None,
) -> None:
    """
    Xatoni error_logs jadvaliga yozadi va logging ga ham uzatadi.

    Args:
        exc:     Yuz bergan exception
        handler: Handler nomi (qaysi faylda yuz berdi)
        user_id: Foydalanuvchi Telegram ID si (ixtiyoriy)
    """
    error_text = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    logger.error("❌ [%s] user_id=%s | %s", handler, user_id, error_text)

    try:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO error_logs (error, handler, user_id)
                   VALUES (?, ?, ?)""",
                (error_text[:2000], handler or None, user_id),
            )
            await db.commit()
    except Exception as db_exc:
        # DB ga yozishda xato bo'lsa — faqat log yozamiz, cheksiz loop yo'q
        logger.error("error_logs ga yozishda xato: %s", db_exc)
