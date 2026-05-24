"""
admin_tools.py
──────────────
Admin uchun yordamchi funksiyalar.

generate_unique_code():
  - 6 xonali raqamli kod yaratadi (100_000 — 999_999)
  - movies VA series jadvallarini ham tekshiradi
  - maksimal 50 ta urinish — cheksiz loop yo'q
  - Barcha urinishlar tugasa ValueError ko'taradi
"""

import logging
import random

import aiosqlite

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 50


async def generate_unique_code(db: aiosqlite.Connection) -> str:
    """
    Filmlar va seriallar uchun takrorlanmas 6 xonali raqamli kod yaratadi.

    Args:
        db: ochiq aiosqlite ulanishi

    Returns:
        Unikal kod (str)

    Raises:
        ValueError: 50 ta urinishdan keyin ham unikal kod topilmasa
    """
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        code = str(random.randint(100_000, 999_999))

        async with db.execute(
            "SELECT 1 FROM movies WHERE code = ?", (code,)
        ) as cur:
            movie_exists = await cur.fetchone()

        async with db.execute(
            "SELECT 1 FROM series WHERE code = ?", (code,)
        ) as cur:
            series_exists = await cur.fetchone()

        if not movie_exists and not series_exists:
            logger.debug(
                "Unikal kod yaratildi: %s (%d-urinish)", code, attempt
            )
            return code

    # Bu holatga amalda deyarli tushib bo'lmaydi (900_000 ta variant)
    raise ValueError(
        f"generate_unique_code: {_MAX_ATTEMPTS} ta urinishdan keyin "
        "unikal kod topilmadi. Bazadagi yozuvlar sonini tekshiring."
    )
