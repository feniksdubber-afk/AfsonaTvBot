"""
Majburiy kanal obunasi tizimi
"""

import json
import aiosqlite
from aiogram import Bot
from aiogram.types import ChatMember
from bot.config import DB_PATH


async def _ensure_settings_table():
    """settings jadvali yo'q bo'lsa yaratadi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.execute("""
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('required_channels', '[]')
        """)
        await db.commit()


async def get_required_channels() -> list[dict]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = 'required_channels'"
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return []
        return json.loads(row[0]) or []
    except Exception:
        # Jadval yo'q — yaratib qayta urinib ko'ramiz
        try:
            await _ensure_settings_table()
        except Exception:
            pass
        return []


async def set_required_channels(channels: list[dict]):
    await _ensure_settings_table()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("required_channels", json.dumps(channels, ensure_ascii=False))
        )
        await db.commit()


async def check_user_subscriptions(bot: Bot, user_id: int) -> list[dict]:
    """Obuna bo'lmagan kanallar ro'yxatini qaytaradi."""
    try:
        channels = await get_required_channels()
    except Exception:
        return []

    if not channels:
        return []

    not_subscribed = []
    for ch in channels:
        try:
            member: ChatMember = await bot.get_chat_member(ch["id"], user_id)
            if member.status in ("left", "kicked", "banned"):
                not_subscribed.append(ch)
        except Exception:
            pass

    return not_subscribed


async def fetch_channel_info(bot: Bot, channel_id_or_username: str) -> dict | None:
    try:
        chat = await bot.get_chat(channel_id_or_username)
        if chat.username:
            link = f"https://t.me/{chat.username}"
        else:
            link = f"https://t.me/c/{str(chat.id)[4:]}"
        return {
            "id": chat.id,
            "title": chat.title or "Kanal",
            "link": link
        }
    except Exception:
        return None
