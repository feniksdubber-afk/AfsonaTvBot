"""
db.py
─────
Ma'lumotlar bazasi bilan ishlash uchun asosiy modul.

  get_db()   — aiosqlite context manager (har bir so'rov uchun)
               WAL + foreign_keys har safar yoqiladi
  init_db()  — botni ishga tushirishda bir marta chaqiriladi

TUZATILGAN:
  - get_db() endi PRAGMA foreign_keys=ON va WAL ni yoqadi
    (oldin faqat init_db() da yoqilar edi — handlerlar tekshiruvsiz ishlardi)
  - context manager to'g'ri implement qilingan
"""

import logging
import os
from contextlib import asynccontextmanager

import aiosqlite

from bot.config import DB_PATH
from bot.database.models import _create_tables

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_db():
    """
    Har bir handler/funksiya uchun yangi DB ulanishi ochadi.
    WAL va foreign_keys har safar yoqiladi — xavfsiz va parallel.

    Ishlatish:
        async with get_db() as db:
            await db.execute(...)
    """
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        # Parallel o'qish/yozish uchun (performance ++)
        await db.execute("PRAGMA journal_mode = WAL")
        # Foreign key cheklovlari — har ulanishda yoqilishi shart
        await db.execute("PRAGMA foreign_keys = ON")
        # Cache 4MB
        await db.execute("PRAGMA cache_size = -4000")
        yield db


async def init_db() -> None:
    """
    Bot ishga tushganda bir marta chaqiriladi.
    Tartib:
      1. data/ papkasini yaratadi
      2. Asosiy jadvallarni yaratadi
      3. Migrationlarni ishga tushiradi
    """
    async with get_db() as db:
        await _create_tables(db)

    logger.info("✅ Asosiy jadvallar tayyor.")

    from bot.database.migrations import run_migrations
    await run_migrations()

    logger.info("✅ Ma'lumotlar bazasi to'liq tayyor!")
