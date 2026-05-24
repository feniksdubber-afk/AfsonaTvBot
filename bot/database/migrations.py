"""
migrations.py
─────────────
Eski bazaga yangi jadvallar va ustunlar qo'shadi.
Ma'lumotlar SAQLANIB QOLADI.

Har safar bot ishga tushganda chaqiriladi — xavfsiz (IF NOT EXISTS / try-except).

QOIDA:
  - Yangi jadval kerak bo'lsa  → CREATE TABLE IF NOT EXISTS bloki qo'shing
  - Yangi ustun kerak bo'lsa   → _add_column() yordamida qo'shing
  - Hech qachon DROP yoki DELETE ishlatmang!

TUZATILGAN:
  - error_logs.handler ustuni qo'shildi (error_logger.py talab qiladi)
  - favorites.series_id uchun partial unique index (NULL muammosi hal qilindi)
"""

import logging

import aiosqlite

from bot.config import DB_PATH

logger = logging.getLogger(__name__)


async def _add_column(
    db: aiosqlite.Connection, table: str, column: str, definition: str
) -> None:
    """Jadvalga ustun qo'shadi. Ustun allaqachon mavjud bo'lsa — e'tiborsiz qoldiradi."""
    try:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        logger.info("Migration: %s.%s ustuni qo'shildi.", table, column)
    except Exception:
        pass  # "duplicate column name" — ustun bor, OK


async def _create_index(
    db: aiosqlite.Connection, index_name: str, ddl: str
) -> None:
    """Index yaratadi. Mavjud bo'lsa — e'tiborsiz qoldiradi."""
    try:
        await db.execute(ddl)
        logger.info("Migration: %s indeksi yaratildi.", index_name)
    except Exception:
        pass


async def run_migrations() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")

        # ── 1. users jadvaliga ustunlar ───────────────────────────────
        await _add_column(db, "users", "night_mode", "INTEGER DEFAULT 0")
        await _add_column(db, "users", "notify",     "INTEGER DEFAULT 1")
        await _add_column(db, "users", "balance",    "INTEGER DEFAULT 0")

        # ── 2. movies jadvaliga ustunlar ──────────────────────────────
        await _add_column(db, "movies", "title_uz",       "TEXT")
        await _add_column(db, "movies", "title_ru",       "TEXT")
        await _add_column(db, "movies", "country",        "TEXT")
        await _add_column(db, "movies", "genres",         "TEXT")
        await _add_column(db, "movies", "poster_file_id", "TEXT")
        await _add_column(db, "movies", "status",         "TEXT DEFAULT 'active'")

        # ── 3. favorites.series_id ────────────────────────────────────
        await _add_column(db, "favorites", "series_id", "INTEGER")

        # Partial unique index: NULL != NULL muammosini hal qiladi
        await _create_index(
            db,
            "idx_favorites_user_series",
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_favorites_user_series
               ON favorites(user_id, series_id)
               WHERE series_id IS NOT NULL"""
        )

        # ── 4. error_logs.handler ─────────────────────────────────────
        # TUZATILGAN: error_logger.py bu ustunni ishlatadi
        await _add_column(db, "error_logs", "handler", "TEXT")

        # ── 5. settings — default qiymatlar ──────────────────────────
        await db.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            [
                ("required_channels", "[]"),
                ("card_number",  "0000 0000 0000 0000"),
                ("card_owner",   "Bot Admin"),
            ]
        )

        await db.commit()

    logger.info("✅ Migrationlar muvaffaqiyatli bajarildi.")
