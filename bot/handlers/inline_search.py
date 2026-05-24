"""
Inline qidiruv — @AfsonaTvBot Avengers
──────────────────────────────────────
Foydalanuvchi istalgan chatda @bot_username nom yozsa:
  → Natijalar chiqadi (poster + nom + reyting)
  → Bossa kino botdan keladi
  → Premium kino bo'lsa — obuna taklifi chiqadi
"""

from aiogram import Router, F
from aiogram.types import (
    InlineQuery,
    InlineQueryResultVideo,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from bot.database.db import get_db

router = Router()

MAX_RESULTS = 10


async def _is_premium_user(user_id: int) -> bool:
    from datetime import datetime
    async with get_db() as db:
        async with db.execute(
            "SELECT is_premium, premium_until FROM users WHERE tg_id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return False
    if not row[0]:
        return False
    if row[1]:
        try:
            until = datetime.fromisoformat(row[1])
            if datetime.now() > until:
                return False
        except Exception:
            pass
    return True


async def _get_lang(user_id: int) -> str:
    async with get_db() as db:
        async with db.execute(
            "SELECT lang FROM users WHERE tg_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else "uz"


@router.inline_query()
async def inline_search(query: InlineQuery):
    search_text = query.query.strip()
    user_id = query.from_user.id

    user_premium = await _is_premium_user(user_id)
    lang = await _get_lang(user_id)

    results = []

    # ── Bo'sh qidiruv — eng mashhur kinolar ─────────────────────────
    if not search_text:
        async with get_db() as db:
            async with db.execute("""
                SELECT id, code, title, year, genre, is_premium,
                       file_id, rating, views, poster_file_id, description
                FROM movies
                WHERE status = 'active' AND is_coming_soon = 0
                ORDER BY views DESC
                LIMIT ?
            """, (MAX_RESULTS,)) as cur:
                movies = await cur.fetchall()
    else:
        # ── Qidiruv — nom + janr + kod bo'yicha ─────────────────────
        async with get_db() as db:
            async with db.execute("""
                SELECT id, code, title, year, genre, is_premium,
                       file_id, rating, views, poster_file_id, description
                FROM movies
                WHERE status = 'active' AND is_coming_soon = 0
                  AND (
                      title LIKE ?
                      OR code LIKE ?
                      OR genre LIKE ?
                  )
                ORDER BY
                    CASE WHEN title LIKE ? THEN 0 ELSE 1 END,
                    views DESC
                LIMIT ?
            """, (
                f"%{search_text}%",
                f"%{search_text}%",
                f"%{search_text}%",
                f"{search_text}%",
                MAX_RESULTS
            )) as cur:
                movies = await cur.fetchall()

    if not movies:
        # Natija topilmadi
        not_found_text = (
            f"🔍 '{search_text}' bo'yicha hech narsa topilmadi"
            if lang == "uz" else
            f"🔍 По запросу '{search_text}' ничего не найдено"
        )
        results.append(
            InlineQueryResultArticle(
                id="not_found",
                title=not_found_text,
                description=(
                    "Boshqa nom bilan qidiring" if lang == "uz"
                    else "Попробуйте другое название"
                ),
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"🔍 <b>'{search_text}'</b> bo'yicha kino topilmadi.\n\n"
                        f"💡 Boshqa nom yoki kod bilan qidiring."
                        if lang == "uz" else
                        f"🔍 По запросу <b>'{search_text}'</b> фильм не найден.\n\n"
                        f"💡 Попробуйте другое название или код."
                    ),
                    parse_mode="HTML"
                ),
                thumbnail_url="https://i.imgur.com/JqMXTJv.png",
            )
        )
        await query.answer(results, cache_time=10, is_personal=True)
        return

    for movie in movies:
        (mid, code, title, year, genre, is_prem,
         file_id, rating, views, poster_fid, description) = movie

        # Premium kino + premium bo'lmagan foydalanuvchi
        locked = is_prem and not user_premium

        # Sarlavha
        premium_badge = "⭐ " if is_prem else ""
        lock_badge = "🔒 " if locked else ""
        year_str = f" ({year})" if year else ""
        genre_str = f" • {genre}" if genre else ""
        rating_str = f" • ⭐{rating:.1f}" if rating else ""

        result_title = f"{lock_badge}{premium_badge}{title}{year_str}"
        result_desc = f"{genre_str}{rating_str} • 👁{views:,}"

        if locked:
            # Premium kino — botga yo'naltiradi
            btn_label = (
                "⭐ Premium olish" if lang == "uz" else "⭐ Получить Premium"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=btn_label,
                    url=f"https://t.me/{query.bot.username}?start=premium"
                )
            ]])
            message_text = (
                f"🔒 <b>{title}</b>{year_str}\n\n"
                f"Bu kino faqat <b>Premium</b> foydalanuvchilar uchun!\n\n"
                f"⭐ Premium oling va barcha kinolarga kiring."
                if lang == "uz" else
                f"🔒 <b>{title}</b>{year_str}\n\n"
                f"Этот фильм только для <b>Premium</b> пользователей!\n\n"
                f"⭐ Оформите Premium для доступа ко всем фильмам."
            )

            results.append(
                InlineQueryResultArticle(
                    id=f"locked_{code}",
                    title=result_title,
                    description=result_desc.strip(" •"),
                    input_message_content=InputTextMessageContent(
                        message_text=message_text,
                        parse_mode="HTML"
                    ),
                    reply_markup=kb,
                    thumbnail_url="https://i.imgur.com/JqMXTJv.png",
                )
            )
        else:
            # Ochiq kino — botdan yuboriladi
            watch_label = (
                "▶️ Kinoni olish" if lang == "uz" else "▶️ Получить фильм"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=watch_label,
                    url=f"https://t.me/{query.bot.username}?start=movie_{code}"
                )
            ]])

            desc_text = description or ""
            caption = (
                f"🎬 <b>{title}</b>{year_str}\n"
                f"🎭 {genre or ''}{rating_str}\n"
                f"👁 Ko'rishlar: {views:,}\n\n"
                f"{desc_text[:200]}"
            ).strip()

            # Video result
            results.append(
                InlineQueryResultVideo(
                    id=f"movie_{code}",
                    video_url=f"https://t.me/{query.bot.username}?start=movie_{code}",
                    mime_type="video/mp4",
                    thumbnail_url="https://i.imgur.com/JqMXTJv.png",
                    title=result_title,
                    description=result_desc.strip(" •"),
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=kb,
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"🎬 <b>{title}</b>{year_str}\n"
                            f"📌 Kod: <code>{code}</code>\n\n"
                            f"Kinoni olish uchun quyidagi tugmani bosing:"
                            if lang == "uz" else
                            f"🎬 <b>{title}</b>{year_str}\n"
                            f"📌 Код: <code>{code}</code>\n\n"
                            f"Нажмите кнопку ниже, чтобы получить фильм:"
                        ),
                        parse_mode="HTML"
                    ),
                )
            )

    await query.answer(
        results,
        cache_time=30,
        is_personal=True,
    )


# ── /start movie_CODE — inline dan kelgan foydalanuvchiga kino yuborish ──
async def handle_movie_deeplink(message, code: str):
    """
    /start movie_AVT1 kabi deep link dan kino yuborish.
    Bu funksiya user.py dagi /start handlerdan chaqiriladi.
    """
    from datetime import datetime
    from aiogram.types import Message

    user_id = message.from_user.id

    async with get_db() as db:
        # Foydalanuvchi ma'lumoti
        async with db.execute(
            "SELECT is_premium, premium_until, lang FROM users WHERE tg_id = ?",
            (user_id,)
        ) as cur:
            user = await cur.fetchone()

        # Kino
        async with db.execute(
            "SELECT * FROM movies WHERE code = ? AND status = 'active'",
            (code.upper(),)
        ) as cur:
            movie = await cur.fetchone()

    if not movie:
        await message.answer(
            "❌ Kino topilmadi!" if (user and user[2] == "uz") else "❌ Фильм не найден!"
        )
        return

    lang = user[2] if user else "uz"

    # Columns: id, code, title, year, genre, is_premium, file_id, ...
    movie_dict = dict(zip([
        "id", "code", "title", "year", "genre", "is_premium",
        "file_id", "file_type", "rating", "views", "poster_file_id",
        "description", "status", "is_series", "season", "episode",
        "created_at"
    ], movie + (None,) * 20))

    is_prem = movie_dict.get("is_premium", 0)

    # Premium tekshirish
    if is_prem:
        user_premium = False
        if user and user[0]:
            if user[1]:
                try:
                    until = datetime.fromisoformat(user[1])
                    user_premium = datetime.now() <= until
                except Exception:
                    pass
            else:
                user_premium = True

        if not user_premium:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="⭐ Premium olish" if lang == "uz" else "⭐ Получить Premium",
                    callback_data="show_premium"
                )
            ]])
            await message.answer(
                f"🔒 <b>{movie_dict['title']}</b>\n\n"
                f"Bu kino faqat Premium foydalanuvchilar uchun!"
                if lang == "uz" else
                f"🔒 <b>{movie_dict['title']}</b>\n\n"
                f"Этот фильм только для Premium пользователей!",
                reply_markup=kb,
                parse_mode="HTML"
            )
            return

    # Ko'rishlar sonini oshirish
    async with get_db() as db:
        await db.execute(
            "UPDATE movies SET views = views + 1 WHERE code = ?",
            (code.upper(),)
        )
        await db.commit()

    # Kinoni yuborish
    file_id = movie_dict.get("file_id")
    file_type = movie_dict.get("file_type", "video")
    caption = (
        f"🎬 <b>{movie_dict['title']}</b>\n"
        f"{'📅 ' + str(movie_dict['year']) if movie_dict.get('year') else ''}"
        f"{'  🎭 ' + movie_dict['genre'] if movie_dict.get('genre') else ''}"
    ).strip()

    try:
        if file_type == "video":
            await message.answer_video(
                file_id,
                caption=caption,
                parse_mode="HTML",
                protect_content=True
            )
        else:
            await message.answer_document(
                file_id,
                caption=caption,
                parse_mode="HTML",
                protect_content=True
            )
    except Exception as e:
        await message.answer(f"❌ Kinoni yuborishda xatolik: {e}")
