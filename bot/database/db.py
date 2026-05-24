"""
db.py
─────
Ma'lumotlar bazasi bilan ishlash uchun asosiy modul.

  get_db()   — aiosqlite context manager qaytaradi (har bir so'rov uchun)
  init_db()  — botni ishga tushirishda bir marta chaqiriladi:
                1. Barcha jadvallarni yaratadi  (models._create_tables)
                2. Migrationlarni ishga tushiradi (migrations.run_migrations)

DIQQAT: init_db() faqat shu faylda — models.py da duplikat YO'Q.
"""

import logging
import os

import aiosqlite

from bot.config import DB_PATH
from bot.database.models import _create_tables

logger = logging.getLogger(__name__)


def get_db() -> aiosqlite.Connection:
    """
    Har bir handler/funksiya uchun yangi DB ulanishi ochadi.
    Ishlatish:
        async with get_db() as db:
            ...
    """
    return aiosqlite.connect(DB_PATH)


async def init_db() -> None:
    """
    Bot ishga tushganda bir marta chaqiriladi.
    Tartib:
      1. data/ papkasini yaratadi (yo'q bo'lsa)
      2. Barcha jadvallarni yaratadi
      3. Migrationlarni ishga tushiradi (ALTER TABLE va hokazo)
    """
    # 1. DB joylashgan papkani yaratish
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    # 2. Asosiy jadvallarni yaratish
    async with aiosqlite.connect(DB_PATH) as db:
        # WAL rejimi — parallel o'qish/yozish uchun
        await db.execute("PRAGMA journal_mode = WAL")
        # Foreign key cheklovlarini yoqish
        await db.execute("PRAGMA foreign_keys = ON")
        await _create_tables(db)

    logger.info("✅ Asosiy jadvallar tayyor.")

    # 3. Migrationlar (ALTER TABLE, yangi jadvallar va h.k.)
    from bot.database.migrations import run_migrations
    await run_migrations()

    logger.info("✅ Ma'lumotlar bazasi to'liq tayyor!")
