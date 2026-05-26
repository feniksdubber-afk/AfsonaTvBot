"""
Majburiy kanal obunasi tizimi

TUZATILGAN:
  - [FIX #4] check_user_subscriptions: har bir kanal tekshiruvida
    xato bo'lsa logger.warning() yoziladi — yashirin xatolar ko'rinadi
  - [FIX #4] fetch_channel_info: xato bo'lsa logger.warning() yoziladi
"""

import json
import logging

import aiosqlite
from aiogram import Bot
from aiogram.types import ChatMember

from bot.config import DB_PATH

logger = logging.getLogger(__name__)


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
    except Exception as exc:
        logger.warning("get_required_channels xatosi: %s", exc)
        try:
            await _ensure_settings_table()
        except Exception as e2:
            logger.warning("_ensure_settings_table xatosi: %s", e2)
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
    except Exception as exc:
        logger.warning("check_user_subscriptions: kanallar olinmadi: %s", exc)
        return []

    if not channels:
        return []

    not_subscribed = []
    for ch in channels:
        try:
            member: ChatMember = await bot.get_chat_member(ch["id"], user_id)
            if member.status in ("left", "kicked", "banned"):
                not_subscribed.append(ch)
        except Exception as exc:
            # [FIX #4] Kanal tekshirishda xato — log yozamiz, o'tkazib yuboramiz
            logger.warning(
                "check_user_subscriptions: kanal=%s user=%s xato: %s",
                ch.get("id"), user_id, exc
            )

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
    except Exception as exc:
        # [FIX #4] Kanal ma'lumotlari olinmadi — log yozamiz
        logger.warning("fetch_channel_info: %s xatosi: %s", channel_id_or_username, exc)
        return None
