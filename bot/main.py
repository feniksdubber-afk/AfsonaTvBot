"""
main.py
───────
Bot ishga tushirish va sozlash markazi.

Router ulash tartibi (muhim!):
  1. subscription_handler — kanal obuna tekshirish
  2. inline_search        — inline query
  3. admin_channels       — admin kanal boshqaruvi
  4. add_movie            — admin: caption-based kino qo'shish
                            (admin.router DAN OLDIN — FSM conflict bo'lmasin)
  5. user                 — foydalanuvchi handlerlari (/start, profil...)
  6. movie                — kino fasl/qism callbacklari
  7. admin                — admin panel (FSM bilan kino/serial qo'shish)
  8. premium              — premium va to'lov handlerlari
  9. gamification         — ball tizimi, vazifalar, turnir

Middleware tartibi:
  1. AuthMiddleware       — foydalanuvchi yaratish, ban tekshirish, lang
  2. SubscriptionMiddleware — majburiy kanal obunasi
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.database.db import init_db
from bot.handlers import (
    user,
    movie,
    admin,
    premium,
    gamification,
    add_movie,
)
from bot.handlers import subscription as subscription_handler
from bot.handlers import inline_search
from bot.handlers import admin_channels
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.utils.scheduler import setup_scheduler

# ── Logs papkasini yaratish ──────────────────────────────────────────
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/errors.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


async def main() -> None:
    # 1. Ma'lumotlar bazasini ishga tushirish
    await init_db()

    # 2. Bot va Dispatcher
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())

    # ── Middleware (tartib muhim!) ────────────────────────────────────
    # 1. Auth — foydalanuvchini yaratadi, ban tekshiradi, lang o'rnatadi
    # 2. Subscription — kanal obunasini tekshiradi
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    # ── Routerlar (tartib muhim!) ─────────────────────────────────────
    dp.include_router(subscription_handler.router)  # 1
    dp.include_router(inline_search.router)          # 2
    dp.include_router(admin_channels.router)         # 3
    dp.include_router(add_movie.router)              # 4 — admin.router DAN OLDIN!
    dp.include_router(user.router)                   # 5
    dp.include_router(movie.router)                  # 6
    dp.include_router(admin.router)                  # 7
    dp.include_router(premium.router)                # 8
    dp.include_router(gamification.router)           # 9

    # ── Scheduler ────────────────────────────────────────────────────
    setup_scheduler(bot)

    logger.info("🚀 Bot muvaffaqiyatli ishga tushdi!")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("👋 Bot to'xtatildi.")
