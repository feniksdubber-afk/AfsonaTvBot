"""
Majburiy kanal obunasi tizimi
─────────────────────────────
- Kanallar bazada saqlanadi (settings jadvali)
- Admin paneldan qo'shish / o'chirish mumkin
- Har bir xabarda tekshiriladi (middleware orqali)
"""

import json
from aiogram import Bot
from aiogram.types import ChatMember
from bot.database.db import get_db


# ─── Bazadan kanallar ro'yxatini olish ──────────────────────────────
async def get_required_channels() -> list[dict]:
    """
    Qaytaradi: [{"id": -100xxx, "title": "Kanal nomi", "link": "@username"}, ...]
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key = 'required_channels'"
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return []
    try:
        return json.loads(row[0]) or []
    except Exception:
        return []


async def set_required_channels(channels: list[dict]):
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("required_channels", json.dumps(channels, ensure_ascii=False))
        )
        await db.commit()


# ─── Foydalanuvchi obuna bo'lganini tekshirish ──────────────────────
async def check_user_subscriptions(bot: Bot, user_id: int) -> list[dict]:
    """
    Obuna bo'lmagan kanallar ro'yxatini qaytaradi.
    Bo'sh list = hammaga obuna.
    """
    channels = await get_required_channels()
    not_subscribed = []

    for ch in channels:
        try:
            member: ChatMember = await bot.get_chat_member(ch["id"], user_id)
            if member.status in ("left", "kicked", "banned"):
                not_subscribed.append(ch)
        except Exception:
            # Kanal mavjud emas yoki bot admin emas — o'tkazib yuboramiz
            pass

    return not_subscribed


# ─── Kanal ma'lumotlarini Telegramdan olish ─────────────────────────
async def fetch_channel_info(bot: Bot, channel_id_or_username: str) -> dict | None:
    """
    Kanal ID yoki @username bo'yicha kanal ma'lumotlarini oladi.
    """
    try:
        chat = await bot.get_chat(channel_id_or_username)
        link = f"@{chat.username}" if chat.username else f"https://t.me/c/{str(chat.id)[4:]}"
        return {
            "id": chat.id,
            "title": chat.title or "Kanal",
            "link": link
        }
    except Exception:
        return None
