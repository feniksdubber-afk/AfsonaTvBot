import aiosqlite
from bot.config import DB_PATH

async def get_db():
    return await aiosqlite.connect(DB_PATH)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await _create_tables(db)
        await db.commit()
        print("✅ Baza tayyor!")
