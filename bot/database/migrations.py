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

YANGILANDI (v2):
  - movie_parts jadvali qo'shildi (film franshizasi)
  - tariffs.points_price ustuni qo'shildi (ballga premium)
  - omdb_cache jadvali qo'shildi (OMDb natijalarini keshlash)
  - admin full-edit uchun yangi FSM state lar shart emas (migration emas)
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

        # Avval eski duplicate qatorlarni tozalaymiz (movie_id bo'yicha)
        await db.execute("""
            DELETE FROM favorites
            WHERE movie_id IS NOT NULL
              AND id NOT IN (
                  SELECT MIN(id) FROM favorites
                  WHERE movie_id IS NOT NULL
                  GROUP BY user_id, movie_id
              )
        """)
        # Eski duplicate qatorlarni tozalaymiz (series_id bo'yicha)
        await db.execute("""
            DELETE FROM favorites
            WHERE series_id IS NOT NULL
              AND id NOT IN (
                  SELECT MIN(id) FROM favorites
                  WHERE series_id IS NOT NULL
                  GROUP BY user_id, series_id
              )
        """)
        await db.commit()

        # Partial unique index (movie_id): NULL != NULL muammosini hal qiladi
        await _create_index(
            db,
            "idx_favorites_user_movie",
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_favorites_user_movie
               ON favorites(user_id, movie_id)
               WHERE movie_id IS NOT NULL"""
        )

        # Partial unique index (series_id): NULL != NULL muammosini hal qiladi
        await _create_index(
            db,
            "idx_favorites_user_series",
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_favorites_user_series
               ON favorites(user_id, series_id)
               WHERE series_id IS NOT NULL"""
        )

        # ── 4. error_logs.handler ─────────────────────────────────────
        await _add_column(db, "error_logs", "handler", "TEXT")

        # ── 5. YANGI: tariffs.points_price — ballga premium (#8) ─────
        await _add_column(db, "tariffs", "points_price", "INTEGER DEFAULT 0")

        # ── 6. YANGI: movie_parts jadvali — film franshizasi (#3) ─────
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS movie_parts (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    movie_id   INTEGER NOT NULL,
                    part_num   INTEGER NOT NULL,
                    title_uz   TEXT,
                    title_ru   TEXT,
                    file_id    TEXT    NOT NULL,
                    created_at TEXT    DEFAULT (datetime('now')),
                    UNIQUE(movie_id, part_num),
                    FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
                )
            """)
            logger.info("Migration: movie_parts jadvali tayyor.")
        except Exception:
            pass

        # ── 7. YANGI: promo_uses jadvali — promokod ishlatilganini kuzatish ──
        #    user_tasks ni noto'g'ri hack qilish o'rniga alohida jadval
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS promo_uses (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    promo_id   INTEGER NOT NULL,
                    user_id    INTEGER NOT NULL,
                    used_at    TEXT    DEFAULT (datetime('now')),
                    UNIQUE(promo_id, user_id),
                    FOREIGN KEY (promo_id) REFERENCES promo_codes(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id)  REFERENCES users(tg_id)    ON DELETE CASCADE
                )
            """)
            logger.info("Migration: promo_uses jadvali tayyor.")
        except Exception:
            pass

        # ── 8. YANGI: omdb_cache jadvali — OMDb keshlash (#7) ────────
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS omdb_cache (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    query      TEXT    UNIQUE NOT NULL,
                    data       TEXT    NOT NULL,
                    created_at TEXT    DEFAULT (datetime('now'))
                )
            """)
            logger.info("Migration: omdb_cache jadvali tayyor.")
        except Exception:
            pass

        # ── 9. settings — default qiymatlar ──────────────────────────
        await db.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            [
                ("required_channels", "[]"),
                ("card_number",  "0000 0000 0000 0000"),
                ("card_owner",   "Bot Admin"),
                ("omdb_api_key", ""),          # OMDb API key
                ("protect_content", "1"),      # Nusxa olish himoyasi (default: yoqiq)
            ]
        )

        await db.commit()

    logger.info("✅ Migrationlar muvaffaqiyatli bajarildi.")
