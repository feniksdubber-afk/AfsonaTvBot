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

Tuzatilgan:
  - favorites.series_id uchun UNIQUE INDEX qo'shildi
    (NULL muammosi: SQL da NULL != NULL, shuning uchun oddiy UNIQUE constraint
     bir userga bir serialga cheksiz yozish imkonini berardi)
"""

import logging

import aiosqlite

from bot.config import DB_PATH

logger = logging.getLogger(__name__)


async def _add_column(
    db: aiosqlite.Connection, table: str, column: str, definition: str
) -> None:
    """
    Jadvalga ustun qo'shadi. Ustun allaqachon mavjud bo'lsa — e'tiborsiz qoldiradi.
    """
    try:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        logger.info("Migration: %s.%s ustuni qo'shildi.", table, column)
    except Exception:
        # "duplicate column name" xatosi — ustun allaqachon bor, OK
        pass


async def _create_index(
    db: aiosqlite.Connection, index_name: str, ddl: str
) -> None:
    """
    Partial index yaratadi. Mavjud bo'lsa — e'tiborsiz qoldiradi.
    """
    try:
        await db.execute(ddl)
        logger.info("Migration: %s indeksi yaratildi.", index_name)
    except Exception:
        pass


async def run_migrations() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")

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

        # ── 3. favorites jadvaliga series_id ustuni ───────────────────
        await _add_column(db, "favorites", "series_id", "INTEGER")

        # ── 3a. favorites.series_id uchun partial unique index ────────
        # Muammo: SQL da NULL != NULL, shuning uchun UNIQUE(user_id, series_id)
        # constraint NULL qiymatlar uchun ishlamaydi — bir userga bir serialga
        # cheksiz yozish mumkin bo'lgan edi.
        # Yechim: WHERE series_id IS NOT NULL filtri bilan partial index.
        await _create_index(
            db,
            "idx_favorites_user_series",
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_favorites_user_series
               ON favorites (user_id, series_id)
               WHERE series_id IS NOT NULL""",
        )
        # movie_id uchun ham xuddi shunday
        await _create_index(
            db,
            "idx_favorites_user_movie",
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_favorites_user_movie
               ON favorites (user_id, movie_id)
               WHERE movie_id IS NOT NULL""",
        )

        # ── 4. watch_history jadvaliga serial ustunlari ───────────────
        await _add_column(db, "watch_history", "series_id",      "INTEGER")
        await _add_column(db, "watch_history", "season_number",  "INTEGER")
        await _add_column(db, "watch_history", "episode_number", "INTEGER")

        # ── 5. Yangi jadvallar ────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS series (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                code           TEXT    UNIQUE NOT NULL,
                title_uz       TEXT    NOT NULL,
                title_ru       TEXT,
                country        TEXT,
                year           INTEGER,
                genres         TEXT,
                poster_file_id TEXT,
                description    TEXT,
                is_premium     INTEGER DEFAULT 0,
                status         TEXT    DEFAULT 'active',
                created_at     TEXT    DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS seasons (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id     INTEGER NOT NULL,
                season_number INTEGER NOT NULL,
                UNIQUE(series_id, season_number),
                FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id      INTEGER NOT NULL,
                season_number  INTEGER NOT NULL,
                episode_number INTEGER NOT NULL,
                file_id        TEXT    NOT NULL,
                created_at     TEXT    DEFAULT (datetime('now')),
                UNIQUE(series_id, season_number, episode_number),
                FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("required_channels", "[]"),
        )

        await db.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                error      TEXT,
                handler    TEXT,
                user_id    INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS point_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                amount     INTEGER NOT NULL,
                reason     TEXT,
                created_at TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(tg_id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                description TEXT,
                prizes      TEXT,
                top_n       INTEGER DEFAULT 3,
                status      TEXT    DEFAULT 'active',
                start_at    TEXT,
                end_at      TEXT,
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tournament_participants (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                points        INTEGER DEFAULT 0,
                UNIQUE(tournament_id, user_id),
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id)  ON DELETE CASCADE,
                FOREIGN KEY (user_id)       REFERENCES users(tg_id)     ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                description TEXT,
                reward      INTEGER NOT NULL DEFAULT 0,
                type        TEXT    NOT NULL,
                target_url  TEXT,
                is_active   INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_tasks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                task_id      INTEGER NOT NULL,
                completed_at TEXT    DEFAULT (datetime('now')),
                UNIQUE(user_id, task_id),
                FOREIGN KEY (user_id) REFERENCES users(tg_id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id)    ON DELETE CASCADE
            )
        """)

        await db.commit()

        # ── Settings default qiymatlari (migration sifatida) ──────────
        await db.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            [
                ("card_number", "0000 0000 0000 0000"),
                ("card_owner",  "Bot Admin"),
            ]
        )
        await db.commit()

    logger.info("✅ Migrationlar muvaffaqiyatli bajarildi.")
