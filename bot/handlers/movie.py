from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import get_db
from bot.keyboards.user_kb import (
    main_menu, movie_kb, rating_kb,
    comments_kb, series_nav_kb, back_kb
)

router = Router()

# ── FSM ────────────────────────────────────────────────
class CommentState(StatesGroup):
    waiting_text = State()
    movie_id = State()

class SearchState(StatesGroup):
    waiting_query = State()

# ── Helpers ────────────────────────────────────────────
async def get_user(tg_id: int) -> dict | None:
    async with await get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE tg_id = ?", (tg_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return dict(zip([d[0] for d in cur.description], row))
    return None

async def get_movie_by_code(code: str) -> dict | None:
    async with await get_db() as db:
        async with db.execute(
            "SELECT * FROM movies WHERE code = ? AND status = 'active'", (code,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return dict(zip([d[0] for d in cur.description], row))
    return None

async def is_favorite(user_id: int, movie_id: int) -> bool:
    async with await get_db() as db:
        async with db.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND movie_id = ?",
            (user_id, movie_id)
        ) as cur:
            return await cur.fetchone() is not None

async def add_watch_history(user_id: int, movie_id: int):
    async with await get_db() as db:
        await db.execute(
            "INSERT INTO watch_history (user_id, movie_id) VALUES (?, ?)",
            (user_id, movie_id)
        )
        await db.execute(
            "UPDATE movies SET views = views + 1 WHERE id = ?", (movie_id,)
        )
        await db.commit()

def txt(uz, ru, lang):
    return uz if lang == "uz" else ru

def movie_caption(m: dict, lang: str) -> str:
    title = m["title_ru"] if lang == "ru" and m.get("title_ru") else m["title"]
    genre = m.get("genre", "—")
    year = m.get("year", "—")
    country = m.get("country", "—")
    rating = m.get("rating", 0)
    views = m.get("views", 0)
    desc = m.get("description", "")
    premium_badge = "⭐ Premium\n" if m.get("is_premium") else ""
    series_info = ""
    if m.get("is_series"):
        series_info = txt(
            f"📺 Serial | Mavsum {m.get('season','?')} | {m.get('episode','?')}-qism\n",
            f"📺 Сериал | Сезон {m.get('season','?')} | Серия {m.get('episode','?')}\n",
            lang
        )

    return (
        f"{premium_badge}"
        f"🎬 <b>{title}</b>\n"
        f"{series_info}"
        f"🎭 {txt('Janr','Жанр',lang)}: {genre}\n"
        f"📅 {txt('Yil','Год',lang)}: {year} | 🌍 {country}\n"
        f"⭐ {txt('Reyting','Рейтинг',lang)}: {rating:.1f}/5\n"
        f"👁 {txt('Ko\'rishlar','Просмотры',lang)}: {views:,}\n\n"
        f"{desc}"
    )

# ── Kino kodi orqali izlash ────────────────────────────
@router.message(F.text.regexp(r'^[A-Za-z0-9]{3,10}$'))
async def find_movie_by_code(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return
    lang = user["lang"]
    code = message.text.strip().upper()

    movie = await get_movie_by_code(code)
    if not movie:
        return  # Kod topilmasa — javob bermaymiz (raqam yoki boshqa narsa bo'lishi mumkin)

    # Premium kino tekshirish
    if movie["is_premium"] and not user["is_premium"]:
        text = txt(
            "⭐ Bu kino <b>Premium</b> foydalanuvchilar uchun.\n"
            "Premium olish uchun /premium buyrug'ini yuboring.",
            "⭐ Этот фильм доступен только для <b>Premium</b> пользователей.\n"
            "Для получения Premium отправьте /premium.",
            lang
        )
        await message.answer(text, parse_mode="HTML")
        return

    fav = await is_favorite(message.from_user.id, movie["id"])
    caption = movie_caption(movie, lang)
    await add_watch_history(message.from_user.id, movie["id"])

    if movie.get("poster_id"):
        await message.answer_photo(
            photo=movie["poster_id"],
            caption=caption,
            reply_markup=movie_kb(movie["id"], fav, lang),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            caption,
            reply_markup=movie_kb(movie["id"], fav, lang),
            parse_mode="HTML"
        )

    # Videoni alohida yuborish
    if movie.get("file_id"):
        await message.answer_video(
            video=movie["file_id"],
            caption=f"🎬 {movie['title']}",
            protect_content=True
        )

    # Serial bo'lsa navigatsiya
    if movie.get("is_series"):
        season = movie["season"]
        episode = movie["episode"]
        code_base = code[:-len(str(episode))] if str(episode) in code else code

        async with await get_db() as db:
            async with db.execute(
                "SELECT 1 FROM movies WHERE code = ? AND status = 'active'",
                (f"{code_base}{episode+1}",)
            ) as cur:
                has_next = await cur.fetchone() is not None
            async with db.execute(
                "SELECT 1 FROM movies WHERE code = ? AND status = 'active'",
                (f"{code_base}{episode-1}",)
            ) as cur:
                has_prev = episode > 1 and await cur.fetchone() is not None

        if has_next or has_prev:
            nav_text = txt("📺 Navigatsiya:", "📺 Навигация:", lang)
            await message.answer(
                nav_text,
                reply_markup=series_nav_kb(code_base, season, episode, has_next, has_prev)
            )


# ── Serial navigatsiya callback ────────────────────────
@router.callback_query(F.data.startswith("ep_"))
async def episode_nav(call: CallbackQuery):
    _, code_base, season, episode = call.data.split("_")
    code = f"{code_base}{episode}"
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    movie = await get_movie_by_code(code)
    if not movie:
        await call.answer(txt("Qism topilmadi!", "Серия не найдена!", lang), show_alert=True)
        return

    await call.answer()
    fav = await is_favorite(call.from_user.id, movie["id"])
    caption = movie_caption(movie, lang)
    await add_watch_history(call.from_user.id, movie["id"])

    if movie.get("file_id"):
        await call.message.answer_video(
            video=movie["file_id"],
            caption=caption,
            reply_markup=movie_kb(movie["id"], fav, lang),
            protect_content=True,
            parse_mode="HTML"
        )


# ── Qidirish ───────────────────────────────────────────
@router.message(F.text.in_(["🔍 Qidirish", "🔍 Поиск"]))
async def search_start(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"]
    text = txt(
        "🔍 Kino nomini yozing:",
        "🔍 Введите название фильма:",
        lang
    )
    await message.answer(text)
    await state.set_state(SearchState.waiting_query)

@router.message(SearchState.waiting_query)
async def search_movies(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"]
    query = f"%{message.text.strip()}%"

    async with await get_db() as db:
        async with db.execute(
            """SELECT code, title, year, is_premium FROM movies
               WHERE (title LIKE ? OR title_ru LIKE ?) AND status = 'active'
               LIMIT 10""",
            (query, query)
        ) as cur:
            rows = await cur.fetchall()

    await state.clear()

    if not rows:
        text = txt("🔍 Hech narsa topilmadi.", "🔍 Ничего не найдено.", lang)
        await message.answer(text, reply_markup=main_menu(lang))
        return

    lines = []
    for r in rows:
        premium = "⭐" if r[3] else "🎬"
        lines.append(f"{premium} <code>{r[0]}</code> — {r[1]} ({r[2] or '?'})")

    text = txt(
        f"🔍 <b>Natijalar:</b>\n\n" + "\n".join(lines) + "\n\n📌 Kodni yuboring — bot ko'rsatadi.",
        f"🔍 <b>Результаты:</b>\n\n" + "\n".join(lines) + "\n\n📌 Отправьте код — бот покажет.",
        lang
    )
    await message.answer(text, reply_markup=main_menu(lang), parse_mode="HTML")


# ── Sevimlilarga qo'shish/olib tashlash ───────────────
@router.callback_query(F.data.startswith("fav_"))
async def toggle_favorite(call: CallbackQuery):
    movie_id = int(call.data.split("_")[1])
    user = await get_user(call.from_user.id)
    lang = user["lang"]
    fav = await is_favorite(call.from_user.id, movie_id)

    async with await get_db() as db:
        if fav:
            await db.execute(
                "DELETE FROM favorites WHERE user_id = ? AND movie_id = ?",
                (call.from_user.id, movie_id)
            )
            msg = txt("💔 Sevimlilardan olib tashlandi!", "💔 Убрано из избранного!", lang)
        else:
            await db.execute(
                "INSERT OR IGNORE INTO favorites (user_id, movie_id) VALUES (?, ?)",
                (call.from_user.id, movie_id)
            )
            msg = txt("❤️ Sevimlilarga qo'shildi!", "❤️ Добавлено в избранное!", lang)
        await db.commit()

    await call.answer(msg)
    await call.message.edit_reply_markup(
        reply_markup=movie_kb(movie_id, not fav, lang)
    )


# ── Reyting ────────────────────────────────────────────
@router.callback_query(F.data.startswith("rate_"))
async def show_rating(call: CallbackQuery):
    movie_id = int(call.data.split("_")[1])
    user = await get_user(call.from_user.id)
    lang = user["lang"]
    text = txt("⭐ Reytingni tanlang:", "⭐ Выберите рейтинг:", lang)
    await call.message.answer(text, reply_markup=rating_kb(movie_id))
    await call.answer()

@router.callback_query(F.data.startswith("setrate_"))
async def set_rating(call: CallbackQuery):
    _, movie_id, stars = call.data.split("_")
    movie_id, stars = int(movie_id), int(stars)
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with await get_db() as db:
        # Foydalanuvchi reytingini saqlash (yangi jadval kerak bo'lsa ham avg hisoblaymiz)
        await db.execute(
            """INSERT OR REPLACE INTO user_ratings (user_id, movie_id, stars)
               VALUES (?, ?, ?)""",
            (call.from_user.id, movie_id, stars)
        )
        # O'rtacha reyting yangilash
        async with db.execute(
            "SELECT AVG(stars) FROM user_ratings WHERE movie_id = ?", (movie_id,)
        ) as cur:
            avg = (await cur.fetchone())[0] or 0
        await db.execute(
            "UPDATE movies SET rating = ? WHERE id = ?", (round(avg, 1), movie_id)
        )
        await db.commit()

    msg = txt(
        f"✅ {'⭐' * stars} Reytingiz saqlandi!",
        f"✅ {'⭐' * stars} Ваш рейтинг сохранён!",
        lang
    )
    await call.answer(msg, show_alert=True)
    await call.message.delete()


# ── Izohlar ────────────────────────────────────────────
@router.callback_query(F.data.startswith("comments_"))
async def show_comments(call: CallbackQuery):
    movie_id = int(call.data.split("_")[1])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with await get_db() as db:
        async with db.execute(
            """SELECT c.id, c.text, c.likes, c.dislikes, u.full_name
               FROM comments c JOIN users u ON c.user_id = u.tg_id
               WHERE c.movie_id = ?
               ORDER BY c.created_at DESC LIMIT 5""",
            (movie_id,)
        ) as cur:
            rows = await cur.fetchall()

    comments = [
        {"id": r[0], "text": r[1], "likes": r[2], "dislikes": r[3], "name": r[4]}
        for r in rows
    ]

    if not comments:
        text = txt(
            "💬 Hali izoh yo'q. Birinchi bo'ling!",
            "💬 Пока нет комментариев. Будьте первым!",
            lang
        )
    else:
        lines = "\n\n".join([
            f"👤 <b>{c['name']}</b>\n{c['text']}\n👍{c['likes']} 👎{c['dislikes']}"
            for c in comments
        ])
        text = txt(f"💬 <b>Izohlar:</b>\n\n{lines}", f"💬 <b>Комментарии:</b>\n\n{lines}", lang)

    await call.message.answer(
        text,
        reply_markup=comments_kb(movie_id, comments, lang),
        parse_mode="HTML"
    )
    await call.answer()

@router.callback_query(F.data.startswith("addcomment_"))
async def add_comment_start(call: CallbackQuery, state: FSMContext):
    movie_id = int(call.data.split("_")[1])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    # Premium tekshirish (izoh faqat premium uchun bo'lsa)
    # if not user["is_premium"]:
    #     await call.answer("⭐ Izoh qoldirish premium uchun!", show_alert=True)
    #     return

    await state.update_data(movie_id=movie_id)
    await state.set_state(CommentState.waiting_text)
    text = txt(
        "✏️ Izohingizni yozing (max 500 belgi):",
        "✏️ Напишите ваш комментарий (макс. 500 символов):",
        lang
    )
    await call.message.answer(text)
    await call.answer()

@router.message(CommentState.waiting_text)
async def save_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    movie_id = data["movie_id"]
    user = await get_user(message.from_user.id)
    lang = user["lang"]

    if len(message.text) > 500:
        text = txt("❌ Izoh 500 belgidan oshmasin!", "❌ Комментарий не должен превышать 500 символов!", lang)
        await message.answer(text)
        return

    async with await get_db() as db:
        await db.execute(
            "INSERT INTO comments (user_id, movie_id, text) VALUES (?, ?, ?)",
            (message.from_user.id, movie_id, message.text)
        )
        await db.commit()

    await state.clear()
    text = txt("✅ Izohingiz qo'shildi!", "✅ Ваш комментарий добавлен!", lang)
    await message.answer(text, reply_markup=main_menu(lang))


# ── Like/Dislike ───────────────────────────────────────
@router.callback_query(F.data.startswith("like_"))
async def like_comment(call: CallbackQuery):
    comment_id = int(call.data.split("_")[1])
    async with await get_db() as db:
        await db.execute(
            "UPDATE comments SET likes = likes + 1 WHERE id = ?", (comment_id,)
        )
        await db.commit()
    await call.answer("👍")

@router.callback_query(F.data.startswith("dislike_"))
async def dislike_comment(call: CallbackQuery):
    comment_id = int(call.data.split("_")[1])
    async with await get_db() as db:
        await db.execute(
            "UPDATE comments SET dislikes = dislikes + 1 WHERE id = ?", (comment_id,)
        )
        await db.commit()
    await call.answer("👎")


# ── Ulashish ───────────────────────────────────────────
@router.callback_query(F.data.startswith("share_"))
async def share_movie(call: CallbackQuery):
    movie_id = int(call.data.split("_")[1])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with await get_db() as db:
        async with db.execute(
            "SELECT code, title FROM movies WHERE id = ?", (movie_id,)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await call.answer()
        return

    bot_info = await call.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={row[0]}"
    text = txt(
        f"📤 <b>{row[1]}</b> kinoni do'stlaringiz bilan ulashing:\n{link}",
        f"📤 Поделитесь фильмом <b>{row[1]}</b> с друзьями:\n{link}",
        lang
    )
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()


# ── O'xshash kinolar ───────────────────────────────────
@router.callback_query(F.data.startswith("similar_"))
async def similar_movies(call: CallbackQuery):
    movie_id = int(call.data.split("_")[1])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with await get_db() as db:
        async with db.execute(
            "SELECT genre FROM movies WHERE id = ?", (movie_id,)
        ) as cur:
            row = await cur.fetchone()

    if not row or not row[0]:
        await call.answer(txt("Ma'lumot yo'q", "Нет данных", lang), show_alert=True)
        return

    genre = row[0]
    async with await get_db() as db:
        async with db.execute(
            """SELECT code, title, rating FROM movies
               WHERE genre = ? AND id != ? AND status = 'active'
               ORDER BY rating DESC LIMIT 5""",
            (genre, movie_id)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await call.answer(txt("O'xshash topilmadi", "Похожих нет", lang), show_alert=True)
        return

    lines = "\n".join([f"🎬 <code>{r[0]}</code> — {r[1]} ⭐{r[2]}" for r in rows])
    text = txt(
        f"🎬 <b>O'xshash kinolar ({genre}):</b>\n\n{lines}",
        f"🎬 <b>Похожие фильмы ({genre}):</b>\n\n{lines}",
        lang
    )
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()


# ── Back to movie ──────────────────────────────────────
@router.callback_query(F.data.startswith("back_movie_"))
async def back_movie(call: CallbackQuery):
    await call.message.delete()
    await call.answer()
