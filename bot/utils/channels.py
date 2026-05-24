"""
Majburiy kanal obunasi tizimi
"""

import json
from aiogram import Bot
from aiogram.types import ChatMember
from bot.database.db import get_db


async def get_required_channels() -> list[dict]:
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = 'required_channels'"
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return []
        return json.loads(row[0]) or []
    except Exception:
        # settings jadvali hali yaratilmagan yoki boshqa xato
        return []


async def set_required_channels(channels: list[dict]):
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("required_channels", json.dumps(channels, ensure_ascii=False))
        )
        await db.commit()


async def check_user_subscriptions(bot: Bot, user_id: int) -> list[dict]:
    """Obuna bo'lmagan kanallar ro'yxatini qaytaradi."""
    channels = await get_required_channels()
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
            # Private kanal uchun invite link
            link = f"https://t.me/c/{str(chat.id)[4:]}"
        return {
            "id": chat.id,
            "title": chat.title or "Kanal",
            "link": link
        }
    except Exception:
        return None
