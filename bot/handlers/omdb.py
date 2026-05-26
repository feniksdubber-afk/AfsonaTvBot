"""
omdb.py  (#7)
────────────
OMDb API integratsiyasi.

Foydalanuvchi kino nomi yozganda:
  1. OMDb dan ma'lumot tortiladi
  2. Poster, reyting, yil, janr ko'rsatiladi
  3. Admin "✅ Qabul" bosib botga kino qo'sha oladi

API key: admin panel → Sozlamalar → OMDb API Key
Bepul: https://www.omdbapi.com/apikey.aspx (1000 req/kun)

Keshlash: omdb_cache jadvali (1 kun)
"""

import json
import logging
from datetime import datetime, timedelta

import aiohttp
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS
from bot.database.db import get_db

logger = logging.getLogger(__name__)
router = Router()

OMDB_BASE = "https://www.omdbapi.com/"
CACHE_TTL_HOURS = 24


# ══════════════════════════════════════════════════════════════════
#  FSM
# ══════════════════════════════════════════════════════════════════
class OmdbSearchState(StatesGroup):
    waiting_query = State()


# ══════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════════════════════════════
async def _get_omdb_key() -> str:
    async with get_db() as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key = 'omdb_api_key'"
        ) as cur:
            row = await cur.fetchone()
    return (row[0] or "").strip() if row else ""


async def _get_user_lang(tg_id: int) -> str:
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT lang FROM users WHERE tg_id = ?", (tg_id,)
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else "uz"
    except Exception:
        return "uz"


def _txt(uz: str, ru: str, lang: str) -> str:
    return uz if lang == "uz" else ru


async def _cached_search(query: str) -> dict | None:
    """Cache dan oladi. Muddati o'tgan bo'lsa None."""
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT data, created_at FROM omdb_cache WHERE query = ?",
                (query.lower(),)
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        created = datetime.fromisoformat(row[1])
        if datetime.now() - created > timedelta(hours=CACHE_TTL_HOURS):
            return None
        return json.loads(row[0])
    except Exception:
        return None


async def _cache_save(query: str, data: dict) -> None:
    try:
        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO omdb_cache (query, data, created_at)
                   VALUES (?, ?, datetime('now'))""",
                (query.lower(), json.dumps(data, ensure_ascii=False))
            )
            await db.commit()
    except Exception:
        pass


async def _omdb_search(query: str, api_key: str) -> dict | None:
    """OMDb API dan qidiradi. Cache dan bo'lsa u yerdan oladi."""
    cached = await _cached_search(query)
    if cached:
        return cached

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                OMDB_BASE,
                params={"t": query, "apikey": api_key, "plot": "short"},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                data = await resp.json()
    except Exception as e:
        logger.warning("OMDb so'rovida xato: %s", e)
        return None

    if data.get("Response") != "True":
        return None

    await _cache_save(query, data)
    return data


def _format_omdb_result(d: dict, lang: str) -> str:
    """OMDb natijasini chiroyli matn sifatida formatlaydi."""
    title    = d.get("Title", "—")
    year     = d.get("Year", "—")
    genre    = d.get("Genre", "—")
    country  = d.get("Country", "—")
    plot     = d.get("Plot", "—")
    rating   = d.get("imdbRating", "—")
    runtime  = d.get("Runtime", "—")
    director = d.get("Director", "—")
    mtype    = d.get("Type", "movie")

    type_icon = "📺" if mtype == "series" else "🎬"

    if lang == "uz":
        return (
            f"{type_icon} <b>{title}</b> ({year})\n"
            f"⭐ IMDb: {rating}/10\n"
            f"⏱ Davomiyligi: {runtime}\n"
            f"🎭 Janr: {genre}\n"
            f"🌍 Davlat: {country}\n"
            f"🎬 Rejissor: {director}\n\n"
            f"📖 <i>{plot}</i>"
        )
    else:
        return (
            f"{type_icon} <b>{title}</b> ({year})\n"
            f"⭐ IMDb: {rating}/10\n"
            f"⏱ Длительность: {runtime}\n"
            f"🎭 Жанр: {genre}\n"
            f"🌍 Страна: {country}\n"
            f"🎬 Режиссёр: {director}\n\n"
            f"📖 <i>{plot}</i>"
        )


def _omdb_result_kb(query: str, is_admin: bool, lang: str) -> InlineKeyboardMarkup:
    """Natija ostidagi tugmalar."""
    buttons = []
    if is_admin:
        add_text = "➕ Botga qo'shish" if lang == "uz" else "➕ Добавить в бот"
        buttons.append([InlineKeyboardButton(
            text=add_text,
            callback_data=f"omdb_add_{query[:40]}"
        )])
    imdb_id_text = "🔗 IMDb sahifasi" if lang == "uz" else "🔗 Страница IMDb"
    buttons.append([InlineKeyboardButton(
        text=imdb_id_text,
        url=f"https://www.imdb.com/find/?q={query.replace(' ', '+')}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ══════════════════════════════════════════════════════════════════
#  HANDLERLAR
# ══════════════════════════════════════════════════════════════════

@router.message(Command("imdb"))
@router.message(F.text.in_(["🔎 IMDb qidiruv", "🔎 Поиск IMDb"]))
async def omdb_search_start(message: Message, state: FSMContext):
    lang = await _get_user_lang(message.from_user.id)
    api_key = await _get_omdb_key()

    if not api_key:
        await message.answer(
            _txt(
                "⚠️ IMDb qidiruvi hozircha faol emas.\n"
                "Admin OMDb API kalitini sozlamalarga kiritishi kerak.",
                "⚠️ Поиск IMDb пока недоступен.\n"
                "Администратор должен ввести OMDb API ключ в настройках.",
                lang
            )
        )
        return

    await state.set_state(OmdbSearchState.waiting_query)
    from bot.keyboards.user_kb import cancel_kb
    await message.answer(
        _txt(
            "🔎 Kino yoki serial nomini yozing (inglizcha):\n\nMisol: <code>Inception</code>",
            "🔎 Введите название фильма или сериала (на английском):\n\nПример: <code>Inception</code>",
            lang
        ),
        reply_markup=cancel_kb(lang),
        parse_mode="HTML"
    )


@router.message(OmdbSearchState.waiting_query, F.text)
async def omdb_search_process(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    lang  = await _get_user_lang(message.from_user.id)

    if not query or len(query) < 2:
        await message.answer(_txt("❌ Kamida 2 harf kiriting!", "❌ Введите хотя бы 2 символа!", lang))
        return

    await state.clear()
    api_key = await _get_omdb_key()
    if not api_key:
        await message.answer(_txt("⚠️ OMDb API kalit kiritilmagan!", "⚠️ OMDb API ключ не задан!", lang))
        return

    wait_msg = await message.answer(_txt("🔎 Qidirilmoqda...", "🔎 Поиск...", lang))

    result = await _omdb_search(query, api_key)

    try:
        await wait_msg.delete()
    except Exception:
        pass

    if not result:
        await message.answer(
            _txt(
                f"❌ <b>{query}</b> — topilmadi.\n\n"
                "💡 Inglizcha nomini to'liq yozing.",
                f"❌ <b>{query}</b> — не найдено.\n\n"
                "💡 Введите полное название на английском.",
                lang
            ),
            parse_mode="HTML"
        )
        return

    text = _format_omdb_result(result, lang)
    is_admin = message.from_user.id in ADMINS
    kb = _omdb_result_kb(query, is_admin, lang)

    poster = result.get("Poster", "")
    if poster and poster != "N/A":
        try:
            await message.answer_photo(
                photo=poster,
                caption=text,
                reply_markup=kb,
                parse_mode="HTML"
            )
            return
        except Exception:
            pass

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("omdb_add_"), F.from_user.id.in_(ADMINS))
async def omdb_add_to_bot(call: CallbackQuery):
    """Admin OMDb natijasini ko'rib, kino qo'shish jarayonini boshlaydi."""
    lang = await _get_user_lang(call.from_user.id)
    query = call.data[len("omdb_add_"):]

    api_key = await _get_omdb_key()
    result = await _omdb_search(query, api_key)

    if not result:
        await call.answer(_txt("❌ Ma'lumot topilmadi!", "❌ Данные не найдены!", lang), show_alert=True)
        return

    title   = result.get("Title", "")
    year    = result.get("Year", "")[:4] if result.get("Year") else ""
    genre   = result.get("Genre", "").replace(", ", "\n")
    country = result.get("Country", "").split(",")[0].strip()

    await call.answer()
    await call.message.answer(
        _txt(
            f"➕ <b>Kino qo'shish uchun admin panelga o'ting:</b>\n\n"
            f"📝 Tayyor ma'lumotlar:\n"
            f"• Nomi (EN): <code>{title}</code>\n"
            f"• Yil: <code>{year}</code>\n"
            f"• Janrlar: <code>{genre}</code>\n"
            f"• Mamlakat: <code>{country}</code>\n\n"
            f"👉 Admin panel → 🎬 Kino qo'shish\n"
            f"Video yuborib, bu ma'lumotlarni kiriting.",
            f"➕ <b>Перейдите в админ-панель для добавления:</b>\n\n"
            f"📝 Готовые данные:\n"
            f"• Название (EN): <code>{title}</code>\n"
            f"• Год: <code>{year}</code>\n"
            f"• Жанры: <code>{genre}</code>\n"
            f"• Страна: <code>{country}</code>\n\n"
            f"👉 Админ панель → 🎬 Добавить кино\n"
            f"Отправьте видео и введите эти данные.",
            lang
        ),
        parse_mode="HTML"
    )
