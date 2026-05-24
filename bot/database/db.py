import os
import aiosqlite
from bot.config import DB_PATH
from bot.database.models import _create_tables


def get_db():
    return aiosqlite.connect(DB_PATH)


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # 1. Asosiy jadvallarni yaratish
    async with aiosqlite.connect(DB_PATH) as db:
        await _create_tables(db)
        await db.commit()

    # 2. Migration — yangi jadvallar va ustunlar
    from bot.database.migrations import run_migrations
    await run_migrations()

    print("✅ Baza tayyor!")
