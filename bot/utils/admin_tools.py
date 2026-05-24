"""
admin_tools.py
──────────────
generate_unique_code() — 3 dan 5 xonagacha random raqamli kod.
movies VA series jadvallarida takrorlanmasligini tekshiradi.
"""

import logging
import random
import aiosqlite

logger = logging.getLogger(__name__)
_MAX_ATTEMPTS = 100


async def generate_unique_code(db: aiosqlite.Connection) -> str:
    """
    3-5 xonali unikal raqamli kod yaratadi.
    Masalan: 847, 3291, 58043

    Raises:
        ValueError: 100 ta urinishdan keyin ham unikal topilmasa
    """
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        digits = random.randint(3, 5)          # 3, 4 yoki 5 xona
        low  = 10 ** (digits - 1)              # 100 / 1000 / 10000
        high = 10 ** digits - 1                # 999 / 9999 / 99999
        code = str(random.randint(low, high))

        async with db.execute(
            "SELECT 1 FROM movies WHERE code = ?", (code,)
        ) as cur:
            if await cur.fetchone():
                continue

        async with db.execute(
            "SELECT 1 FROM series WHERE code = ?", (code,)
        ) as cur:
            if await cur.fetchone():
                continue

        logger.debug("Kod yaratildi: %s (%d-urinish)", code, attempt)
        return code

    raise ValueError("generate_unique_code: unikal kod topilmadi!")
