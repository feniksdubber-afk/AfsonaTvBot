from aiogram import Router, F
from aiogram.types import (
    InlineQuery, InlineQueryResultArticle,
    InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
)
from bot.database.db import get_db

router = Router()


@router.inline_query()
async def advanced_inline_search(inline_query: InlineQuery):
    query = inline_query.query.strip()
    if not query:
        return

    results = []
    bot_user = await inline_query.bot.get_me()

    async with get_db() as db:
        # 1. Filmlardan qidirish (aktivlari) — eski title va yangi title_uz bilan
        async with db.execute("""
            SELECT code, title, title_uz, year, genres, poster_file_id FROM movies
            WHERE status = 'active'
              AND (title_uz LIKE ? OR title_ru LIKE ? OR title LIKE ?)
            LIMIT 5
        """, (f"%{query}%", f"%{query}%", f"%{query}%")) as cur:
            movies = await cur.fetchall()

        # 2. Seriallardan qidirish (aktivlari)
        async with db.execute("""
            SELECT code, title_uz, year, genres, poster_file_id FROM series
            WHERE status = 'active'
              AND (title_uz LIKE ? OR title_ru LIKE ?)
            LIMIT 5
        """, (f"%{query}%", f"%{query}%")) as cur:
            series = await cur.fetchall()

    # Filmlarni natijaga qo'shish
    for row in movies:
        code, title_old, title_uz, year, genres, poster = row
        # Backward compatibility: eski title ustunini ham qo'llab-quvvatlash
        title = title_uz or title_old or "Nomsiz kino"

        results.append(
            InlineQueryResultArticle(
                id=f"movie_{code}",
                title=f"🎬 FILM: {title} ({year or '?'})",
                description=f"🎭 {genres or ''}",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"🎬 <b>{title}</b> ({year or '?'}) filmini "
                        f"tomosha qilish uchun pastdagi tugmani bosing 👇"
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🍿 Tomosha qilish",
                        url=f"https://t.me/{bot_user.username}?start=movie_{code}"
                    )
                ]])
            )
        )

    # Seriallarni natijaga qo'shish
    for row in series:
        code, title, year, genres, poster = row
        results.append(
            InlineQueryResultArticle(
                id=f"series_{code}",
                title=f"📺 SERIAL: {title} ({year or '?'})",
                description=f"🎭 {genres or ''}",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"📺 <b>{title}</b> ({year or '?'}) serialining "
                        f"barcha qismlarini ko'rish uchun pastdagi tugmani bosing 👇"
                    ),
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🍿 Barcha qismlar",
                        url=f"https://t.me/{bot_user.username}?start=series_{code}"
                    )
                ]])
            )
        )

    await inline_query.answer(results=results, cache_time=5)
