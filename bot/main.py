"""
bot/main.py — Majburiy kanal qo'shilgandan keyingi holat
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.database.db import init_db
from bot.handlers import user, movie, admin, premium, gamification
from bot.handlers import subscription as subscription_handler
from bot.handlers.admin import add_movie_fsm, add_series_fsm, edit_content
from bot.handlers import inline_search
from bot.handlers import admin_channels
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.utils.scheduler import setup_scheduler

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/errors.log"),
        logging.StreamHandler()
    ]
)


async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())

    # ── Middleware tartib muhim! ──────────────────────────────────────
    # 1. Auth — foydalanuvchini yaratadi, ban tekshiradi, lang o'rnatadi
    # 2. Subscription — kanal obunasini tekshiradi
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    # ── Routerlar ────────────────────────────────────────────────────
    # subscription_handler BIRINCHI — check_subscription callback uchun
    dp.include_router(subscription_handler.router)
    dp.include_router(add_movie_fsm.router)
    dp.include_router(add_series_fsm.router)
    dp.include_router(edit_content.router)
    dp.include_router(inline_search.router)
    dp.include_router(admin_channels.router)
    dp.include_router(user.router)
    dp.include_router(movie.router)
    dp.include_router(admin.router)
    dp.include_router(premium.router)
    dp.include_router(gamification.router)

    setup_scheduler(bot)

    print("🤖 Bot ishga tushdi!")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
