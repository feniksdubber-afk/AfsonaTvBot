"""
models.py
─────────
Barcha jadval sxemalari (CREATE TABLE IF NOT EXISTS).
Bu fayl faqat jadval tuzilmasini ta'riflaydi.
init_db() bu yerda YO'Q — u db.py da joylashgan.

TUZATILGAN:
  - error_logs jadvaliga `handler` ustuni qo'shildi
    (error_logger.py uni INSERT da ishlatadi, lekin jadvalda yo'q edi)
  - favorites jadvalidagi UNIQUE constraint izohi aniqlantirildi
    (NULL muammosi migrations.py da partial index bilan hal qilinadi)
"""

import aiosqlite


CREATE_TABLES = """

-- ════════════════════════════════════════════
--  FOYDALANUVCHILAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    tg_id         INTEGER UNIQUE NOT NULL,
    username      TEXT,
    full_name     TEXT,
    lang          TEXT    DEFAULT 'uz',
    is_premium    INTEGER DEFAULT 0,
    premium_until TEXT,
    is_banned     INTEGER DEFAULT 0,
    balance       INTEGER DEFAULT 0,
    referral_code TEXT    UNIQUE,
    referred_by   INTEGER,
    night_mode    INTEGER DEFAULT 0,
    notify        INTEGER DEFAULT 1,
    created_at    TEXT    DEFAULT (datetime('now'))
);

-- ════════════════════════════════════════════
--  KINOLAR (Filmlar)
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS movies (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT    UNIQUE NOT NULL,
    title          TEXT    NOT NULL,
    title_uz       TEXT,
    title_ru       TEXT,
    description    TEXT,
    genre          TEXT,
    genres         TEXT,
    year           INTEGER,
    country        TEXT,
    rating         REAL    DEFAULT 0,
    is_premium     INTEGER DEFAULT 0,
    is_series      INTEGER DEFAULT 0,
    season         INTEGER,
    episode        INTEGER,
    file_id        TEXT,
    poster_id      TEXT,
    poster_file_id TEXT,
    views          INTEGER DEFAULT 0,
    status         TEXT    DEFAULT 'active',
    created_at     TEXT    DEFAULT (datetime('now'))
);

-- ════════════════════════════════════════════
--  SERIALLAR
-- ════════════════════════════════════════════
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
);

-- ════════════════════════════════════════════
--  FASLLAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS seasons (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id     INTEGER NOT NULL,
    season_number INTEGER NOT NULL,
    UNIQUE(series_id, season_number),
    FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE CASCADE
);

-- ════════════════════════════════════════════
--  QISMLAR (Epizodlar)
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS episodes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id      INTEGER NOT NULL,
    season_number  INTEGER NOT NULL,
    episode_number INTEGER NOT NULL,
    file_id        TEXT    NOT NULL,
    created_at     TEXT    DEFAULT (datetime('now')),
    UNIQUE(series_id, season_number, episode_number),
    FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE CASCADE
);

-- ════════════════════════════════════════════
--  SEVIMLILAR
--  ESLATMA: series_id uchun UNIQUE partial index
--           migrations.py da yaratiladi (NULL != NULL muammosi).
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS favorites (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    movie_id  INTEGER,
    series_id INTEGER,
    added_at  TEXT    DEFAULT (datetime('now')),
    UNIQUE(user_id, movie_id),
    FOREIGN KEY (user_id)   REFERENCES users(tg_id)   ON DELETE CASCADE,
    FOREIGN KEY (movie_id)  REFERENCES movies(id)     ON DELETE CASCADE,
    FOREIGN KEY (series_id) REFERENCES series(id)     ON DELETE CASCADE
);

-- ════════════════════════════════════════════
--  KO'RISH TARIXI
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS watch_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    movie_id       INTEGER,
    series_id      INTEGER,
    season_number  INTEGER,
    episode_number INTEGER,
    watched_at     TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_id)   REFERENCES users(tg_id)  ON DELETE CASCADE,
    FOREIGN KEY (movie_id)  REFERENCES movies(id)    ON DELETE SET NULL,
    FOREIGN KEY (series_id) REFERENCES series(id)    ON DELETE SET NULL
);

-- ════════════════════════════════════════════
--  IZOHLAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    movie_id   INTEGER NOT NULL,
    text       TEXT    NOT NULL,
    likes      INTEGER DEFAULT 0,
    dislikes   INTEGER DEFAULT 0,
    created_at TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_id)  REFERENCES users(tg_id) ON DELETE CASCADE,
    FOREIGN KEY (movie_id) REFERENCES movies(id)   ON DELETE CASCADE
);

-- ════════════════════════════════════════════
--  LIKE / DISLIKE REAKSIYALAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS movie_reactions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    movie_id INTEGER NOT NULL,
    reaction TEXT    NOT NULL CHECK(reaction IN ('like','dislike')),
    UNIQUE(user_id, movie_id),
    FOREIGN KEY (user_id)  REFERENCES users(tg_id) ON DELETE CASCADE,
    FOREIGN KEY (movie_id) REFERENCES movies(id)   ON DELETE CASCADE
);

-- ════════════════════════════════════════════
--  REYTINGLAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_ratings (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    movie_id INTEGER NOT NULL,
    stars    INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 5),
    UNIQUE(user_id, movie_id),
    FOREIGN KEY (user_id)  REFERENCES users(tg_id) ON DELETE CASCADE,
    FOREIGN KEY (movie_id) REFERENCES movies(id)   ON DELETE CASCADE
);

-- ════════════════════════════════════════════
--  PREMIUM TARIFLAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS tariffs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    duration    INTEGER NOT NULL,
    price       INTEGER NOT NULL,
    description TEXT,
    is_active   INTEGER DEFAULT 1
);

-- ════════════════════════════════════════════
--  TO'LOVLAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS payments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    tariff_id      INTEGER,
    amount         INTEGER NOT NULL,
    method         TEXT,
    status         TEXT    DEFAULT 'pending',
    transaction_id TEXT,
    created_at     TEXT    DEFAULT (datetime('now')),
    paid_at        TEXT,
    FOREIGN KEY (user_id)   REFERENCES users(tg_id) ON DELETE CASCADE,
    FOREIGN KEY (tariff_id) REFERENCES tariffs(id)  ON DELETE SET NULL
);

-- ════════════════════════════════════════════
--  PROMOKODLAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS promo_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT    UNIQUE NOT NULL,
    type       TEXT    NOT NULL,
    value      INTEGER NOT NULL,
    uses_left  INTEGER DEFAULT 1,
    expires_at TEXT
);

-- ════════════════════════════════════════════
--  PROMOKOD ISHLATILGANLIK
--  Har bir foydalanuvchi har bir promokodni
--  faqat 1 marta ishlatishi mumkin.
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS promo_uses (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    promo_id INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    used_at  TEXT    DEFAULT (datetime('now')),
    UNIQUE(promo_id, user_id),
    FOREIGN KEY (promo_id) REFERENCES promo_codes(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)  REFERENCES users(tg_id)    ON DELETE CASCADE
);

-- ════════════════════════════════════════════
--  VAZIFALAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT,
    reward      INTEGER NOT NULL DEFAULT 0,
    type        TEXT    NOT NULL,
    target_url  TEXT,
    is_active   INTEGER DEFAULT 1
);

-- ════════════════════════════════════════════
--  FOYDALANUVCHI VAZIFALARI
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    task_id      INTEGER NOT NULL,
    completed_at TEXT    DEFAULT (datetime('now')),
    UNIQUE(user_id, task_id),
    FOREIGN KEY (user_id) REFERENCES users(tg_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(id)    ON DELETE CASCADE
);

-- ════════════════════════════════════════════
--  KINO SO'ROVLAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS movie_requests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    text       TEXT    NOT NULL,
    status     TEXT    DEFAULT 'pending',
    created_at TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(tg_id) ON DELETE CASCADE
);

-- ════════════════════════════════════════════
--  SOZLAMALAR
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ════════════════════════════════════════════
--  XATOLIKLAR LOGI
--  TUZATILGAN: handler ustuni qo'shildi
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS error_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    error      TEXT,
    handler    TEXT,
    user_id    INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

-- ════════════════════════════════════════════
--  BALL TARIXI LOGI
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS point_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    amount     INTEGER NOT NULL,
    reason     TEXT,
    created_at TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(tg_id) ON DELETE CASCADE
);

-- ════════════════════════════════════════════
--  TURNIRLAR
-- ════════════════════════════════════════════
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
);

-- ════════════════════════════════════════════
--  TURNIR QATNASHCHILARI
-- ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS tournament_participants (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    points        INTEGER DEFAULT 0,
    UNIQUE(tournament_id, user_id),
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id)  ON DELETE CASCADE,
    FOREIGN KEY (user_id)       REFERENCES users(tg_id)     ON DELETE CASCADE
);

"""


async def _create_tables(db: aiosqlite.Connection) -> None:
    """
    Barcha jadvallarni bir yo'la yaratadi.
    IF NOT EXISTS — xavfsiz, mavjud ma'lumotlar saqlanib qoladi.
    """
    await db.executescript(CREATE_TABLES)

    await db.executemany(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        [
            ("required_channels", "[]"),
            ("card_number",  "0000 0000 0000 0000"),
            ("card_owner",   "Bot Admin"),
            ("protect_content", "1"),
        ]
    )
    await db.commit()
