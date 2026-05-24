"""
main.py
───────
Bot ishga tushirish va sozlash markazi.

Router ulash tartibi (muhim!):
  1. subscription_handler — kanal obuna tekshirish
  2. inline_search        — inline query
  3. admin_channels       — admin kanal boshqaruvi
  4. user                 — foydalanuvchi handlerlari (/start, profil...)
  5. movie                — kino fasl/qism callbacklari
  6. admin                — admin panel (FSM bilan kino/serial qo'shish)
  7. premium              — premium va to'lov handlerlari
  8. gamification         — ball tizimi, vazifalar, turnir

Middleware tartibi:
  1. AuthMiddleware         — foydalanuvchi yaratish, ban tekshirish, lang
  2. SubscriptionMiddleware — majburiy kanal obunasi

O'ZGARISH:
  - MemoryStorage → aiogram_sqlite_storage.SQLiteStorage
    Bot to'xtab qayta ishga tushsa FSM holatlari saqlanib qoladi.
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram_sqlite_storage import SQLiteStorage

from bot.config import BOT_TOKEN, DB_PATH
from bot.database.db import init_db
from bot.handlers import (
    user,
    movie,
    admin,
    premium,
    gamification,
)
from bot.handlers import subscription as subscription_handler
from bot.handlers import inline_search
from bot.handlers import admin_channels
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.utils.scheduler import setup_scheduler

# ── Papkalarni yaratish ──────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH) or "data", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/errors.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# FSM holatlari saqlanadigan fayl (kino DB dan alohida — aralashmasin)
FSM_DB_PATH = DB_PATH.replace("kinobot.db", "fsm.db")


async def main() -> None:
    # 1. Ma'lumotlar bazasini ishga tushirish
    await init_db()

    # 2. Bot va Dispatcher — SQLiteStorage bilan
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=SQLiteStorage(FSM_DB_PATH))

    # ── Middleware (tartib muhim!) ────────────────────────────────────
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.inline_query.middleware(AuthMiddleware())

    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    # ── Routerlar (tartib muhim!) ─────────────────────────────────────
    dp.include_router(subscription_handler.router)  # 1
    dp.include_router(inline_search.router)          # 2
    dp.include_router(admin_channels.router)         # 3
    dp.include_router(user.router)                   # 4
    dp.include_router(movie.router)                  # 5
    dp.include_router(admin.router)                  # 6
    dp.include_router(premium.router)                # 7
    dp.include_router(gamification.router)           # 8

    # ── Scheduler ────────────────────────────────────────────────────
    scheduler = setup_scheduler(bot)

    logger.info("🚀 Bot muvaffaqiyatli ishga tushdi! (FSM: SQLiteStorage → %s)", FSM_DB_PATH)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("⏹ Scheduler to'xtatildi.")
        await bot.session.close()
        logger.info("👋 Bot to'xtatildi.")


if __name__ == "__main__":
    asyncio.run(main())
