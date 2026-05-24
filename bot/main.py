"""
bot/main.py  —  E qism qo'shilgandan KEYINGI holat
"""
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.database.db import init_db
from bot.handlers import user, movie, admin, premium
from bot.handlers import gamification
from bot.middlewares.auth import AuthMiddleware
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

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

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
