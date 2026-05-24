import os
import aiosqlite
from bot.config import DB_PATH
from bot.database.models import _create_tables

async def get_db():
    return await aiosqlite.connect(DB_PATH)

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await _create_tables(db)
        await db.commit()
        print("✅ Baza tayyor!")
