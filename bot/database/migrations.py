"""
migrations.py
─────────────
Eski bazaga yangi jadvallar va ustunlarni qo'shadi.
Ma'lumotlar saqlanib qoladi.
Har safar bot ishga tushganda chaqiriladi — xavfsiz (IF NOT EXISTS).
"""

import json
import aiosqlite
from bot.config import DB_PATH


async def run_migrations():
    async with aiosqlite.connect(DB_PATH) as db:

        # ── 1. settings jadvali ──────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Default required_channels (bo'sh ro'yxat)
        await db.execute("""
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('required_channels', '[]')
        """)

        # ── 2. error_logs jadvali ─────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                error      TEXT,
                user_id    INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # ── 3. point_log jadvali ──────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS point_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                amount     INTEGER NOT NULL,
                reason     TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(tg_id)
            )
        """)

        # ── 4. tournaments jadvali ────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                prizes      TEXT,
                top_n       INTEGER DEFAULT 3,
                status      TEXT DEFAULT 'active',
                start_at    TEXT,
                end_at      TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)

        # ── 5. tournament_participants jadvali ────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tournament_participants (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                points        INTEGER DEFAULT 0,
                UNIQUE(tournament_id, user_id),
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id),
                FOREIGN KEY (user_id)       REFERENCES users(tg_id)
            )
        """)

        # ── 6. tasks jadvali ──────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT,
                description TEXT,
                reward      INTEGER,
                type        TEXT,
                target_url  TEXT,
                is_active   INTEGER DEFAULT 1
            )
        """)

        # ── 7. user_tasks jadvali ─────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_tasks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER,
                task_id      INTEGER,
                completed_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, task_id)
            )
        """)

        # ── 8. YANGI: series jadvali (Seriallar uchun) ────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS series (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                code            TEXT UNIQUE NOT NULL,
                title_uz        TEXT NOT NULL,
                title_ru        TEXT,
                country         TEXT,
                year            INTEGER,
                genres          TEXT,
                poster_file_id  TEXT,
                description     TEXT,
                is_premium      INTEGER DEFAULT 0,
                status          TEXT DEFAULT 'active', -- active, archived, deleted
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)

        # ── 9. YANGI: seasons jadvali (Fasllar) ───────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seasons (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id     INTEGER NOT NULL,
                season_number INTEGER NOT NULL,
                UNIQUE(series_id, season_number),
                FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE CASCADE
            )
        """)

        # ── 10. YANGI: episodes jadvali (Qismlar) ─────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id      INTEGER NOT NULL,
                season_number  INTEGER NOT NULL,
                episode_number INTEGER NOT NULL,
                file_id        TEXT NOT NULL,
                created_at     TEXT DEFAULT (datetime('now')),
                UNIQUE(series_id, season_number, episode_number),
                FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE CASCADE
            )
        """)

        # ── 11. users jadvaliga yangi ustunlar qo'shish ───────────────
        user_columns = [
            ("night_mode", "INTEGER DEFAULT 0"),
            ("notify",     "INTEGER DEFAULT 1"),
            ("balance",    "INTEGER DEFAULT 0"),
        ]
        for col_name, col_def in user_columns:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
            except Exception:
                pass

        # ── 12. movies jadvaliga barcha yangi ustunlarni qo'shish ──────
        movie_columns = [
            ("title_ru",       "TEXT"),
            ("country",        "TEXT"),
            ("status",         "TEXT DEFAULT 'active'"),
            ("title_uz",       "TEXT"),
            ("genres",         "TEXT"),
            ("poster_file_id", "TEXT"),
        ]
        for col_name, col_def in movie_columns:
            try:
                await db.execute(f"ALTER TABLE movies ADD COLUMN {col_name} {col_def}")
            except Exception:
                pass

        await db.commit()
        print("✅ Migration muvaffaqiyatli bajarildi! Barcha eski va yangi jadvallar integratsiya qilindi.")
