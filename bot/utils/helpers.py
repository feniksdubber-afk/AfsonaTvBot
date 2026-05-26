"""
helpers.py
──────────
Barcha handlerlarda takrorlanadigan yordamchi funksiyalar.

Ishlatish:
    from bot.utils.helpers import get_user, txt, is_admin
"""

from bot.config import ADMINS
from bot.database.db import get_db


# ── Til ──────────────────────────────────────────────────────────────
def txt(uz: str, ru: str, lang: str) -> str:
    """Tilga qarab matn qaytaradi."""
    return uz if lang == "uz" else ru


# ── Admin tekshiruv ───────────────────────────────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


# ── Foydalanuvchi ─────────────────────────────────────────────────────
async def get_user(tg_id: int) -> dict | None:
    """users jadvalidan foydalanuvchini dict sifatida qaytaradi."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE tg_id = ?", (tg_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
    return None


async def get_user_lang(tg_id: int) -> str:
    """Foydalanuvchi tilini qaytaradi, topilmasa 'uz'."""
    u = await get_user(tg_id)
    return u["lang"] if u else "uz"


async def get_protect_setting() -> bool:
    """
    settings jadvalidan 'protect_content' qiymatini o'qiydi.
    True  → protect_content=True  (nusxa/yuborish bloklangan)
    False → protect_content=False (nusxa/yuborish ruxsat etilgan)
    Default: True (himoyalangan)
    """
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = 'protect_content'"
            ) as cur:
                row = await cur.fetchone()
        return (row[0] if row else "1") == "1"
    except Exception:
        return True
