"""
inline_search.py
────────────────
@AfsonaTvBot Avatar — istalgan chatda kino qidirish.

Natija bosilganda foydalanuvchi botga o'tib kino oladi
(deep link: /start movie_KOD yoki /start series_KOD).
"""

import logging
from aiogram import Router, F
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from bot.database.db import get_db

router  = Router()
logger  = logging.getLogger(__name__)
MAX_RES = 10


async def _is_premium_user(user_id: int) -> bool:
    from datetime import datetime
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT is_premium, premium_until FROM users WHERE tg_id = ?",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
        if not row or not row[0]:
            return False
        if row[1]:
            try:
                until = datetime.strptime(row[1], "%Y-%m-%d")
                return datetime.now() <= until
            except Exception:
                pass
        return True
    except Exception:
        return False


async def _get_lang(user_id: int) -> str:
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT lang FROM users WHERE tg_id = ?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else "uz"
    except Exception:
        return "uz"


@router.inline_query()
async def inline_search(query: InlineQuery):
    search = query.query.strip()
    user_id = query.from_user.id
    user_premium = await _is_premium_user(user_id)
    lang = await _get_lang(user_id)

    like = f"%{search}%"

    async with get_db() as db:
        if not search:
            # Bo'sh — eng mashhurlar
            async with db.execute("""
                SELECT 'movie' as t, code,
                       COALESCE(title_uz, title, 'Nomsiz') as title,
                       year, genres, is_premium, rating, views
                FROM movies WHERE status='active' AND is_premium=0
                ORDER BY views DESC LIMIT ?
            """, (MAX_RES,)) as cur:
                rows = await cur.fetchall()
        else:
            # Qidiruv — movies
            async with db.execute("""
                SELECT 'movie' as t, code,
                       COALESCE(title_uz, title, 'Nomsiz') as title,
                       year, genres, is_premium, rating, views
                FROM movies
                WHERE status='active'
                  AND (title_uz LIKE ? OR title LIKE ? OR title_ru LIKE ? OR code LIKE ?)
                ORDER BY CASE WHEN title_uz LIKE ? THEN 0 ELSE 1 END, views DESC
                LIMIT ?
            """, (like, like, like, like, f"{search}%", MAX_RES)) as cur:
                movie_rows = await cur.fetchall()

            # Qidiruv — series
            async with db.execute("""
                SELECT 'series' as t, code,
                       COALESCE(title_uz, 'Nomsiz serial') as title,
                       year, genres, is_premium, 0 as rating, 0 as views
                FROM series
                WHERE status='active'
                  AND (title_uz LIKE ? OR title_ru LIKE ? OR code LIKE ?)
                ORDER BY id DESC LIMIT 5
            """, (like, like, like)) as cur:
                series_rows = await cur.fetchall()

            rows = list(movie_rows) + list(series_rows)

    if not rows:
        empty_text = (
            f"🔍 '{search}' — hech narsa topilmadi"
            if lang == "uz" else
            f"🔍 '{search}' — ничего не найдено"
        )
        results = [
            InlineQueryResultArticle(
                id="not_found",
                title=empty_text,
                description="Boshqa nom bilan qidiring" if lang == "uz" else "Попробуйте другое название",
                input_message_content=InputTextMessageContent(
                    message_text=f"🔍 <b>{search}</b> bo'yicha kino topilmadi." if lang == "uz"
                                 else f"🔍 По запросу <b>{search}</b> ничего не найдено.",
                    parse_mode="HTML"
                ),
            )
        ]
        await query.answer(results, cache_time=10, is_personal=True)
        return

    bot_info = await query.bot.get_me()
    bot_username = bot_info.username
    results = []

    for row in rows:
        ctype, code, title, year, genres, is_prem, rating, views = row

        locked = is_prem and not user_premium
        lock   = "🔒 " if locked else ""
        star   = "⭐ " if is_prem else ""
        icon   = "📺 " if ctype == "series" else "🎬 "
        y      = f" ({year})" if year else ""
        g      = genres or "—"
        r      = f"⭐{rating:.1f}" if rating else ""

        result_title = f"{lock}{star}{icon}{title}{y}"
        result_desc  = f"{g}  {r}  👁{views:,}".strip(" ")

        if locked:
            # Premium kino — botga premium sahifasiga yo'naltiradi
            url = f"https://t.me/{bot_username}?start=premium"
            btn_text = "⭐ Premium olish" if lang == "uz" else "⭐ Получить Premium"
            msg_text = (
                f"🔒 <b>{title}</b>{y}\n\n"
                f"Bu kino faqat <b>Premium</b> foydalanuvchilar uchun!\n"
                f"/premium"
                if lang == "uz" else
                f"🔒 <b>{title}</b>{y}\n\n"
                f"Этот фильм только для <b>Premium</b> пользователей!\n"
                f"/premium"
            )
        else:
            prefix = "movie" if ctype == "movie" else "series"
            url = f"https://t.me/{bot_username}?start={prefix}_{code}"
            btn_text = "▶️ Kinoni olish" if lang == "uz" else "▶️ Получить фильм"
            msg_text = (
                f"{icon}<b>{title}</b>{y}\n"
                f"📌 Kod: <code>{code}</code>\n\n"
                f"Kinoni olish uchun quyidagi tugmani bosing:"
                if lang == "uz" else
                f"{icon}<b>{title}</b>{y}\n"
                f"📌 Код: <code>{code}</code>\n\n"
                f"Нажмите кнопку ниже, чтобы получить фильм:"
            )

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=btn_text, url=url)
        ]])

        results.append(
            InlineQueryResultArticle(
                id=f"{ctype}_{code}",
                title=result_title,
                description=result_desc,
                input_message_content=InputTextMessageContent(
                    message_text=msg_text,
                    parse_mode="HTML"
                ),
                reply_markup=kb,
                thumbnail_url=None,
            )
        )

    await query.answer(results, cache_time=30, is_personal=True)
