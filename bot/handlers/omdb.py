"""
omdb.py
───────
OMDb API integratsiyasi.

Foydalanuvchi:
  /imdb → nom yozadi → natija + poster ko'rsatiladi

Admin:
  "➕ Botga qo'shish" → FSM ishga tushadi:
    1. OMDb dan nom, yil, janr, mamlakat, tavsif, poster avtomatik olinadi
    2. Admin faqat VIDEO yuboradi
    3. Admin premium/tekin tanlaydi → bazaga saqlanadi

TUZATILGAN:
  - [FIX #1] omdb_add endi to'liq avtomatlashtirilgan — admin faqat video yuboradi
  - [FIX #2] _cache_save xatosi endi logger.warning bilan loglanadi
  - [FIX #3] OMDb search ham s= (bir nechta natija) ko'rsatadi, keyin t= bilan to'liq ma'lumot oladi

API key: admin panel → Sozlamalar → OMDb API Key
Bepul:   https://www.omdbapi.com/apikey.aspx (1000 req/kun)
Keshlash: omdb_cache jadvali (24 soat)
"""

import json
import logging
from datetime import datetime, timedelta

import aiohttp
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS, CHANNEL_PRIVATE, CHANNEL_PUBLIC
from bot.database.db import get_db
from bot.utils.admin_tools import generate_unique_code
from bot.keyboards import admin_kb as custom_admin_kb

logger = logging.getLogger(__name__)
router = Router()

OMDB_BASE = "https://www.omdbapi.com/"
CACHE_TTL_HOURS = 24


# ══════════════════════════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════════════════════════
class OmdbSearchState(StatesGroup):
    waiting_query = State()

class OmdbAddState(StatesGroup):
    """Admin OMDb orqali kino qo'shganda faqat video kerak — qolganini OMDb beradi."""
    waiting_video   = State()
    waiting_premium = State()


# ══════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════════════════════════════
async def _get_omdb_key() -> str:
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = 'omdb_api_key'"
            ) as cur:
                row = await cur.fetchone()
        return (row[0] or "").strip() if row else ""
    except Exception as exc:
        logger.warning("_get_omdb_key xatosi: %s", exc)
        return ""


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
    """Cache dan oladi. Muddati o'tgan bo'lsa None qaytaradi."""
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
    except Exception as exc:
        # [FIX #2] Ilgari "pass" edi — endi log yoziladi
        logger.warning("_cache_save xatosi (query=%s): %s", query, exc)


async def _omdb_fetch_by_title(query: str, api_key: str) -> dict | None:
    """Aniq nom bo'yicha to'liq ma'lumot oladi (t= parametri)."""
    cached = await _cached_search(query)
    if cached:
        return cached

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                OMDB_BASE,
                params={"t": query, "apikey": api_key, "plot": "short"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                data = await resp.json()
    except Exception as exc:
        logger.warning("OMDb t= so'rovida xato: %s", exc)
        return None

    if data.get("Response") != "True":
        return None

    await _cache_save(query, data)
    return data


async def _omdb_search_list(query: str, api_key: str) -> list[dict]:
    """[FIX #3] Qidiruv ro'yxatini qaytaradi (s= parametri) — bir nechta variant."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                OMDB_BASE,
                params={"s": query, "apikey": api_key},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                data = await resp.json()
    except Exception as exc:
        logger.warning("OMDb s= so'rovida xato: %s", exc)
        return []

    if data.get("Response") != "True":
        return []

    return data.get("Search", [])[:5]  # Eng ko'pi 5 ta


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


def _omdb_result_kb(query: str, is_admin_user: bool, lang: str) -> InlineKeyboardMarkup:
    """Natija ostidagi tugmalar."""
    buttons = []
    if is_admin_user:
        add_text = "➕ Botga qo'shish" if lang == "uz" else "➕ Добавить в бот"
        buttons.append([InlineKeyboardButton(
            text=add_text,
            callback_data=f"omdb_add_{query[:40]}"
        )])
    imdb_text = "🔗 IMDb sahifasi" if lang == "uz" else "🔗 Страница IMDb"
    buttons.append([InlineKeyboardButton(
        text=imdb_text,
        url=f"https://www.imdb.com/find/?q={query.replace(' ', '+')}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _search_results_kb(results: list[dict], lang: str) -> InlineKeyboardMarkup:
    """[FIX #3] Bir nechta natija bo'lsa tanlash klaviaturasi."""
    buttons = []
    for item in results:
        title = item.get("Title", "?")
        year  = item.get("Year", "")
        itype = "📺" if item.get("Type") == "series" else "🎬"
        label = f"{itype} {title} ({year})"
        # imdbID orqali aniq filmni keyingi qidiruv uchun title+year ishlatamiz
        cb = f"omdb_pick_{title[:35]}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=cb)])

    cancel_text = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    buttons.append([InlineKeyboardButton(text=cancel_text, callback_data="cancel_input")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ══════════════════════════════════════════════════════════════════
#  QIDIRUV HANDLERLARI (foydalanuvchi + admin)
# ══════════════════════════════════════════════════════════════════

@router.message(Command("imdb"))
@router.message(F.text.in_(["🔎 IMDb qidiruv", "🔎 Поиск IMDb"]))
async def omdb_search_start(message: Message, state: FSMContext):
    lang    = await _get_user_lang(message.from_user.id)
    api_key = await _get_omdb_key()

    if not api_key:
        await message.answer(
            _txt(
                "⚠️ IMDb qidiruvi hozircha faol emas.\n"
                "Admin OMDb API kalitini sozlamalarga kiritishi kerak.",
                "⚠️ Поиск IMDb пока недоступен.\n"
                "Администратор должен ввести OMDb API ключ в настройках.",
                lang,
            )
        )
        return

    await state.set_state(OmdbSearchState.waiting_query)
    from bot.keyboards.user_kb import cancel_kb
    await message.answer(
        _txt(
            "🔎 Kino yoki serial nomini yozing (inglizcha):\n\nMisol: <code>Inception</code>",
            "🔎 Введите название фильма или сериала (на английском):\n\nПример: <code>Inception</code>",
            lang,
        ),
        reply_markup=cancel_kb(lang),
        parse_mode="HTML",
    )


@router.message(OmdbSearchState.waiting_query, F.text)
async def omdb_search_process(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    lang  = await _get_user_lang(message.from_user.id)

    if len(query) < 2:
        await message.answer(_txt("❌ Kamida 2 harf kiriting!", "❌ Введите хотя бы 2 символа!", lang))
        return

    await state.clear()
    api_key = await _get_omdb_key()
    if not api_key:
        await message.answer(_txt("⚠️ OMDb API kalit kiritilmagan!", "⚠️ OMDb API ключ не задан!", lang))
        return

    wait_msg = await message.answer(_txt("🔎 Qidirilmoqda...", "🔎 Поиск...", lang))

    # [FIX #3] Avval ro'yxat qidiradi (s=), agar bir nechta bo'lsa tanlash beradi
    results = await _omdb_search_list(query, api_key)

    try:
        await wait_msg.delete()
    except Exception:
        pass

    if not results:
        await message.answer(
            _txt(
                f"❌ <b>{query}</b> — topilmadi.\n\n💡 Inglizcha nomini to'liq yozing.",
                f"❌ <b>{query}</b> — не найдено.\n\n💡 Введите полное название на английском.",
                lang,
            ),
            parse_mode="HTML",
        )
        return

    # Agar bitta aniq natija — to'g'ridan ko'rsatamiz
    if len(results) == 1:
        await _show_omdb_result(message, results[0]["Title"], api_key, lang)
        return

    # Bir nechta natija — tanlash klaviaturasi ko'rsatamiz
    choose_text = _txt(
        "🔎 Bir nechta natija topildi. Keraklisini tanlang:",
        "🔎 Найдено несколько результатов. Выберите нужный:",
        lang,
    )
    await message.answer(
        choose_text,
        reply_markup=_search_results_kb(results, lang),
    )


@router.callback_query(F.data.startswith("omdb_pick_"))
async def omdb_pick_result(call: CallbackQuery):
    """Foydalanuvchi bir nechta natijadan birini tanladi."""
    lang    = await _get_user_lang(call.from_user.id)
    title   = call.data[len("omdb_pick_"):]
    api_key = await _get_omdb_key()

    await call.answer()
    wait_msg = await call.message.answer(_txt("🔎 Yuklanmoqda...", "🔎 Загрузка...", lang))
    await _show_omdb_result(call.message, title, api_key, lang,
                             is_admin_user=(call.from_user.id in ADMINS))
    try:
        await wait_msg.delete()
    except Exception:
        pass


async def _show_omdb_result(
    message: Message,
    title: str,
    api_key: str,
    lang: str,
    is_admin_user: bool | None = None,
) -> None:
    """To'liq OMDb natijasini poster bilan ko'rsatadi."""
    result = await _omdb_fetch_by_title(title, api_key)
    if not result:
        await message.answer(
            _txt(
                f"❌ <b>{title}</b> uchun batafsil ma'lumot topilmadi.",
                f"❌ Подробная информация по <b>{title}</b> не найдена.",
                lang,
            ),
            parse_mode="HTML",
        )
        return

    if is_admin_user is None:
        is_admin_user = message.from_user.id in ADMINS if message.from_user else False

    text   = _format_omdb_result(result, lang)
    kb     = _omdb_result_kb(title, is_admin_user, lang)
    poster = result.get("Poster", "")

    if poster and poster != "N/A":
        try:
            await message.answer_photo(photo=poster, caption=text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════
#  ADMIN: BOTGA QO'SHISH — TO'LIQ AVTOMATLASHTIRILGAN FSM
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("omdb_add_"), F.from_user.id.in_(ADMINS))
async def omdb_add_start(call: CallbackQuery, state: FSMContext):
    """
    [FIX #1] Eski versiyada faqat matn ko'rsatilgan edi.
    Endi: OMDb ma'lumotlari FSM ga saqlanadi, admin faqat video yuboradi.
    """
    lang    = await _get_user_lang(call.from_user.id)
    query   = call.data[len("omdb_add_"):]
    api_key = await _get_omdb_key()

    result = await _omdb_fetch_by_title(query, api_key)
    if not result:
        await call.answer(
            _txt("❌ Ma'lumot topilmadi!", "❌ Данные не найдены!", lang),
            show_alert=True,
        )
        return

    # OMDb dan olingan ma'lumotlarni FSM ga saqlaymiz
    title_en = result.get("Title", "")
    year_raw = result.get("Year", "")
    year     = int(year_raw[:4]) if year_raw[:4].isdigit() else 0
    genres   = result.get("Genre", "").replace(", ", "\n")
    country  = result.get("Country", "").split(",")[0].strip()
    plot     = result.get("Plot", "")
    poster   = result.get("Poster", "")
    rating   = result.get("imdbRating", "")
    mtype    = result.get("Type", "movie")

    # Tavsifni boyitamiz: plot + reyting
    description = plot
    if rating and rating != "N/A":
        description += f"\n\n⭐ IMDb: {rating}/10"

    await state.update_data(
        title_uz=title_en,   # Admin keyinchalik o'zgartirishi mumkin
        title_ru=title_en,   # Ruscha ham shu — admin tahrirlaydi
        year=year,
        genres=genres,
        country=country,
        description=description,
        poster_url=poster if (poster and poster != "N/A") else "",
        poster_file_id="",   # Video yuborilganda poster ham saqlanadi
        omdb_type=mtype,
    )

    await state.set_state(OmdbAddState.waiting_video)
    await call.answer()

    # Saqlanajak ma'lumotlarni ko'rsatamiz
    info = (
        f"✅ <b>OMDb dan olingan ma'lumotlar:</b>\n\n"
        f"🎬 Nomi: <b>{title_en}</b>\n"
        f"📅 Yil: {year or '—'}\n"
        f"🎭 Janrlar: {genres.replace(chr(10), ', ')}\n"
        f"🌍 Mamlakat: {country or '—'}\n\n"
        f"📖 Tavsif: <i>{plot[:200]}{'...' if len(plot) > 200 else ''}</i>\n\n"
        f"🎥 <b>Endi film videosini yuboring:</b>"
    )

    await call.message.answer(
        info,
        reply_markup=custom_admin_kb.cancel_fsm_kb(),
        parse_mode="HTML",
    )


@router.message(OmdbAddState.waiting_video, F.video, F.from_user.id.in_(ADMINS))
async def omdb_add_video(message: Message, state: FSMContext):
    """Admin video yubordi — poster va premium tanlov qoldi."""
    await state.update_data(file_id=message.video.file_id)

    fsm_data = await state.get_data()
    lang     = await _get_user_lang(message.from_user.id)

    # Agar OMDb da poster bo'lsa — URL ni file_id ga aylantiramiz
    poster_url = fsm_data.get("poster_url", "")
    if poster_url:
        try:
            sent = await message.answer_photo(
                photo=poster_url,
                caption=_txt(
                    "✅ Video qabul qilindi. Poster IMDb dan olindi.\n\n⭐ Premium yoki tekin?",
                    "✅ Видео принято. Постер взят из IMDb.\n\n⭐ Премиум или бесплатно?",
                    lang,
                ),
                reply_markup=custom_admin_kb.is_premium_kb(),
                parse_mode="HTML",
            )
            # Telegram photo file_id ni saqlaymiz (URL emas)
            await state.update_data(poster_file_id=sent.photo[-1].file_id)
        except Exception as exc:
            logger.warning("OMDb poster yuklashda xato: %s", exc)
            await message.answer(
                _txt(
                    "⚠️ Poster yuklanmadi — poster bo'lmasdan davom etamiz.\n\n⭐ Premium yoki tekin?",
                    "⚠️ Постер не загрузился — продолжим без постера.\n\n⭐ Премиум или бесплатно?",
                    lang,
                ),
                reply_markup=custom_admin_kb.is_premium_kb(),
            )
    else:
        await message.answer(
            _txt(
                "✅ Video qabul qilindi. Poster mavjud emas.\n\n⭐ Premium yoki tekin?",
                "✅ Видео принято. Постер недоступен.\n\n⭐ Премиум или бесплатно?",
                lang,
            ),
            reply_markup=custom_admin_kb.is_premium_kb(),
        )

    await state.set_state(OmdbAddState.waiting_premium)


@router.callback_query(OmdbAddState.waiting_premium, F.data.startswith("premium_"), F.from_user.id.in_(ADMINS))
async def omdb_add_save(call: CallbackQuery, state: FSMContext, bot: Bot):
    """Barcha ma'lumotlar tayyor — bazaga saqlaymiz."""
    is_premium = 1 if call.data == "premium_yes" else 0
    data       = await state.get_data()
    await state.clear()

    title_uz = data.get("title_uz", "").strip()
    title_ru = data.get("title_ru", "").strip()
    if not title_uz:
        await call.message.edit_text("❌ Xato: nom aniqlanmadi. Jarayon bekor qilindi.")
        await call.answer()
        return

    file_id        = data.get("file_id", "")
    poster_file_id = data.get("poster_file_id", "")
    year           = data.get("year", 0)
    genres         = data.get("genres", "")
    country        = data.get("country", "")
    description    = data.get("description", "")

    async with get_db() as db:
        code = await generate_unique_code(db)
        await db.execute(
            """INSERT INTO movies
               (code, title, title_uz, title_ru, country, year, genres,
                description, file_id, poster_file_id, is_premium, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
            (
                code, title_uz, title_uz, title_ru,
                country, year, genres,
                description, file_id, poster_file_id,
                is_premium,
            ),
        )
        await db.commit()

    # Private kanalga backup
    try:
        await bot.send_video(
            chat_id=CHANNEL_PRIVATE,
            video=file_id,
            caption=(
                f"📦 BACKUP | FILM (OMDb)\n🔑 KOD: {code}\n"
                f"🎬 NOM: {title_uz} | {title_ru}"
            ),
        )
    except Exception as exc:
        logger.warning("Private backup xatosi: %s", exc)

    # Public kanalga post
    try:
        bot_user     = await bot.get_me()
        premium_tag  = "⭐ PREMIUM" if is_premium else "🔓 TEKIN"
        pub_caption  = (
            f"🎬 <b>{title_uz.upper()}</b>\n"
            f"🌍 {country} | 📅 {year}\n"
            f"🎭 {genres.replace(chr(10), ', ')}\n"
            f"Status: {premium_tag}\n\n"
            f"🍿 {description[:300]}\n\n"
            f"👇 Tomosha qilish uchun tugmani bosing"
        )
        watch_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🎬 TOMOSHA QILISH",
                url=f"https://t.me/{bot_user.username}?start=movie_{code}",
            )
        ]])
        if poster_file_id:
            await bot.send_photo(
                chat_id=CHANNEL_PUBLIC,
                photo=poster_file_id,
                caption=pub_caption,
                reply_markup=watch_kb,
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=CHANNEL_PUBLIC,
                text=pub_caption,
                reply_markup=watch_kb,
                parse_mode="HTML",
            )
    except Exception as exc:
        logger.warning("Public post xatosi: %s", exc)

    await call.message.answer(
        f"✅ <b>Film muvaffaqiyatli saqlandi!</b>\n\n"
        f"🔑 Kod: <code>{code}</code>\n"
        f"🎬 Nomi: {title_uz}\n"
        f"📅 Yil: {year} | 🌍 {country}\n"
        f"⭐ Premium: {'Ha' if is_premium else \"Yo'q\"}",
        parse_mode="HTML",
    )
    await call.answer()


# ══════════════════════════════════════════════════════════════════
#  BEKOR QILISH (OmdbAddState uchun)
# ══════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "cancel_input")
async def cancel_omdb_input(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current in (OmdbSearchState.waiting_query, OmdbAddState.waiting_video, OmdbAddState.waiting_premium):
        await state.clear()
    lang = await _get_user_lang(call.from_user.id)
    await call.message.edit_text(_txt("❌ Bekor qilindi.", "❌ Отменено.", lang))
    await call.answer()
