"""
bot/database/models.py  —  E qism qo'shilgandan KEYINGI to'liq holat
Eski faylingizni SHU BILAN ALMASHTIRING.
"""
import aiosqlite
from bot.config import DB_PATH

CREATE_TABLES = """

-- Foydalanuvchilar
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    tg_id         INTEGER UNIQUE NOT NULL,
    username      TEXT,
    full_name     TEXT,
    lang          TEXT DEFAULT 'uz',
    is_premium    INTEGER DEFAULT 0,
    premium_until TEXT,
    is_banned     INTEGER DEFAULT 0,
    balance       INTEGER DEFAULT 0,
    referral_code TEXT UNIQUE,
    referred_by   INTEGER,
    night_mode    INTEGER DEFAULT 0,
    notify        INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now'))
);

-- Kinolar
CREATE TABLE IF NOT EXISTS movies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    title       TEXT NOT NULL,
    title_ru    TEXT,
    description TEXT,
    genre       TEXT,
    year        INTEGER,
    country     TEXT,
    rating      REAL DEFAULT 0,
    is_premium  INTEGER DEFAULT 0,
    is_series   INTEGER DEFAULT 0,
    season      INTEGER,
    episode     INTEGER,
    file_id     TEXT,
    poster_id   TEXT,
    views       INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'active',
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Sevimlilar
CREATE TABLE IF NOT EXISTS favorites (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER,
    movie_id INTEGER,
    added_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, movie_id)
);

-- Ko'rish tarixi
CREATE TABLE IF NOT EXISTS watch_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    movie_id   INTEGER,
    watched_at TEXT DEFAULT (datetime('now'))
);

-- Izohlar
CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    movie_id   INTEGER,
    text       TEXT,
    likes      INTEGER DEFAULT 0,
    dislikes   INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Kinolarga berilgan baholar
CREATE TABLE IF NOT EXISTS user_ratings (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER,
    movie_id INTEGER,
    stars    INTEGER,
    UNIQUE(user_id, movie_id)
);

-- Premium Tariflar
CREATE TABLE IF NOT EXISTS tariffs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    duration    INTEGER NOT NULL,
    price       INTEGER NOT NULL,
    description TEXT,
    is_active   INTEGER DEFAULT 1
);

-- Premium to'lovlar
CREATE TABLE IF NOT EXISTS payments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    tariff_id      INTEGER,
    amount         INTEGER NOT NULL,
    method         TEXT,
    status         TEXT DEFAULT 'pending',
    transaction_id TEXT,
    created_at     TEXT DEFAULT (datetime('now')),
    paid_at        TEXT
);

-- Promokodlar
CREATE TABLE IF NOT EXISTS promo_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT UNIQUE,
    type       TEXT,
    value      INTEGER,
    uses_left  INTEGER,
    expires_at TEXT
);

-- Vazifalar
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT,
    description TEXT,
    reward      INTEGER,
    type        TEXT,        -- watch / referral / rate / url / manual
    target_url  TEXT,
    is_active   INTEGER DEFAULT 1
);

-- Foydalanuvchi vazifalari
CREATE TABLE IF NOT EXISTS user_tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER,
    task_id      INTEGER,
    completed_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, task_id)
);

-- Kino so'rovlar
CREATE TABLE IF NOT EXISTS movie_requests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    text       TEXT,
    status     TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now'))
);

-- Xatoliklar logi
CREATE TABLE IF NOT EXISTS error_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    error      TEXT,
    user_id    INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

-- ═══════════════════════════════════════════════════════════════
--  E QISM — Gamification uchun yangi jadvallar
-- ═══════════════════════════════════════════════════════════════

-- Ball tarixi logi
CREATE TABLE IF NOT EXISTS point_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    amount     INTEGER NOT NULL,
    reason     TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Turnirlar
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
);

-- Turnir qatnashchilari
CREATE TABLE IF NOT EXISTS tournament_participants (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    points        INTEGER DEFAULT 0,
    UNIQUE(tournament_id, user_id)
);

"""

async def _create_tables(db: aiosqlite.Connection):
    await db.executescript(CREATE_TABLES)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await _create_tables(db)
        await db.commit()
        print("✅ Baza tayyor!")
