"""
add_movie.py
────────────
Admin caption bilan video yuborib kino qo'shadigan aqlli handler.

Ishlash tartibi:
  1. Admin video/document yuboradi (caption ixtiyoriy)
  2. Bot caption dan ma'lumotlarni avtomatik parse qiladi
  3. Admin preview ko'rib, tasdiqlaydi yoki tahrirlaydi
  4. Saqlash tugmasida kino bazaga yoziladi

Caption formatlari (hammasi ishlaydi):
  Avatar 2009 Fantastika premium
  #AVTR1 Avatar | Fantastika | 2009
  Kod: AVT1, Nom: Avatar, Janr: Drama, Yil: 2009, Premium
  Merlin S01E01 - Serial - Fantasy
  MRLN101 | Merlin | Fantasy | 2009 | serial | s1e1

MUHIM: Bu router add_movie.router sifatida main.py ga ulanishi kerak,
       va admin.router DAN OLDIN ro'yxatdan o'tishi shart.
       Aks holda FilmStates.waiting_video bilan conflict bo'ladi.
"""

import logging
import re
import random
import string

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS
from bot.database.db import get_db

logger = logging.getLogger(__name__)
router = Router()

# ─── Janrlar ro'yxati ────────────────────────────────────────────────
GENRES = [
    "Drama", "Komediya", "Boevik", "Triller", "Fantastika",
    "Melodrama", "Qo'rqinchli", "Animatsiya", "Hujjatli",
    "Biografiya", "Tarix", "Sport", "Musiqa", "Serial",
    "Fantasy", "Kriminal", "Harbiy", "Sarguzasht",
]


# ════════════════════════════════════════════════════════════════════
#  FSM STATES
# ════════════════════════════════════════════════════════════════════
class AddMovieEditState(StatesGroup):
    waiting_field_value = State()


# ════════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ════════════════════════════════════════════════════════════════════

def _gen_code(title: str) -> str:
    """Kino nomidan 6-8 belgili unikal kod generatsiya qiladi."""
    words = re.sub(r'[^a-zA-Z0-9\s]', '', title.upper()).split()
    if words:
        base = ''.join(w[:3] for w in words[:3])
    else:
        base = ''.join(random.choices(string.ascii_uppercase, k=4))
    suffix = ''.join(random.choices(string.digits, k=2))
    return (base + suffix)[:8]


async def _ensure_unique_code(db, code: str) -> str:
    """
    Kod bazada mavjud bo'lsa, oxiriga raqam qo'shib unikal qiladi.
    Ikki jadvalda (movies va series) ham tekshiradi.
    """
    original = code
    attempt = 0
    while True:
        async with db.execute(
            "SELECT 1 FROM movies WHERE code = ?", (code,)
        ) as cur:
            movie_exists = await cur.fetchone()
        async with db.execute(
            "SELECT 1 FROM series WHERE code = ?", (code,)
        ) as cur:
            series_exists = await cur.fetchone()

        if not movie_exists and not series_exists:
            return code

        attempt += 1
        code = original + str(random.randint(1, 99))
        if attempt > 20:
            # Juda ko'p urinish — tasodifiy kod
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _parse_caption(caption: str) -> dict:
    """
    Caption dan kino ma'lumotlarini aqlli parse qiladi.
    Turli formatlarni qo'llab-quvvatlaydi.
    """
    data = {
        "code":        None,
        "title":       None,
        "title_uz":    None,
        "title_ru":    None,
        "genre":       None,
        "year":        None,
        "is_premium":  0,
        "is_series":   0,
        "season":      None,
        "episode":     None,
        "description": None,
    }

    text = caption.strip()
    if not text:
        return data

    # ── 1. Kod ───────────────────────────────────────────────────────
    code_match = re.search(r'#([A-Z0-9]{2,10})', text.upper())
    if not code_match:
        code_match = re.search(
            r'(?:kod|code)\s*[:\s]\s*([A-Z0-9]{2,10})', text, re.IGNORECASE
        )
    if code_match:
        data["code"] = code_match.group(1).upper()
    else:
        first_word = text.split()[0] if text.split() else ""
        if re.match(r'^[A-Z0-9]{3,10}$', first_word.upper()):
            data["code"] = first_word.upper()

    # ── 2. Yil ───────────────────────────────────────────────────────
    year_match = re.search(r'\b(19\d{2}|20[0-3]\d)\b', text)
    if year_match:
        data["year"] = int(year_match.group(1))

    # ── 3. Serial S01E01 ─────────────────────────────────────────────
    series_match = re.search(r's(\d{1,2})e(\d{1,3})', text, re.IGNORECASE)
    if series_match:
        data["is_series"] = 1
        data["season"]    = int(series_match.group(1))
        data["episode"]   = int(series_match.group(2))
    elif re.search(r'\bserial\b', text, re.IGNORECASE):
        data["is_series"] = 1

    # ── 4. Premium ───────────────────────────────────────────────────
    if re.search(r'\bpremium\b', text, re.IGNORECASE):
        data["is_premium"] = 1

    # ── 5. Janr ──────────────────────────────────────────────────────
    genre_match = re.search(
        r'(?:janr|жанр|genre)\s*[:\s]\s*([^\n,|]+)', text, re.IGNORECASE
    )
    if genre_match:
        data["genre"] = genre_match.group(1).strip()
    else:
        for g in GENRES:
            if g.lower() in text.lower():
                data["genre"] = g
                break

    # ── 6. Tavsif ────────────────────────────────────────────────────
    desc_match = re.search(
        r'(?:tavsif|описание|desc)\s*[:\s]\s*(.+)', text, re.IGNORECASE | re.DOTALL
    )
    if desc_match:
        data["description"] = desc_match.group(1).strip()[:500]

    # ── 7. Nom ───────────────────────────────────────────────────────
    # Pipe | yoki tire - ajratgichdan nom olish
    pipe_parts = [p.strip() for p in re.split(r'[|\-—]', text) if p.strip()]
    if len(pipe_parts) >= 2:
        candidate = pipe_parts[0]
        if data["code"] and candidate.upper().strip() == data["code"]:
            data["title"] = pipe_parts[1]
        else:
            data["title"] = candidate
    else:
        clean = text
        if data["code"]:
            clean = re.sub(re.escape(data["code"]), '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'#\w+', '', clean)
        clean = re.sub(r'\b(19\d{2}|20[0-3]\d)\b', '', clean)
        clean = re.sub(r'\bpremium\b', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\bserial\b', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r's\d{1,2}e\d{1,3}', '', clean, flags=re.IGNORECASE)
        clean = re.sub(
            r'(?:kod|janr|tavsif|описание|genre|desc)\s*[:\s][^\n]+', '',
            clean, flags=re.IGNORECASE
        )
        clean = re.sub(r'[|,]+', ' ', clean)
        clean = ' '.join(clean.split())
        if clean and len(clean) >= 2:
            data["title"] = clean[:100]

    # ── 8. Nom oxirgi fallback ───────────────────────────────────────
    if not data["title"] and text:
        data["title"] = text.split('\n')[0].strip()[:100]

    # title_uz = title (asosiy)
    if data["title"]:
        data["title_uz"] = data["title"]

    return data


def _preview_text(data: dict, file_type: str) -> str:
    """Preview ko'rsatish uchun matn."""
    code      = data.get("code") or "— (avtomatik)"
    title     = data.get("title") or "—"
    title_ru  = data.get("title_ru") or "—"
    genre     = data.get("genre") or "—"
    year      = data.get("year") or "—"
    premium   = "✅ Ha" if data.get("is_premium") else "❌ Yo'q"
    series_info = ""
    if data.get("is_series"):
        s = data.get("season") or "?"
        e = data.get("episode") or "?"
        series_info = f"\n📺 Serial: {s}-mavsum, {e}-qism"

    return (
        f"📋 <b>Kino ma'lumotlari:</b>\n\n"
        f"📌 Kod: <code>{code}</code>\n"
        f"🎬 Nom (UZ): {title}\n"
        f"🎬 Nom (RU): {title_ru}\n"
        f"🎭 Janr: {genre}\n"
        f"📅 Yil: {year}\n"
        f"⭐ Premium: {premium}"
        f"{series_info}\n"
        f"🎞 Fayl: {file_type}\n\n"
        f"To'g'rimi? Tasdiqlang yoki tahrirlang:"
    )


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Saqlash",    callback_data="am_save"),
            InlineKeyboardButton(text="✏️ Tahrirlash", callback_data="am_edit"),
        ],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="am_cancel")],
    ])


def _edit_kb() -> InlineKeyboardMarkup:
    fields = [
        ("📌 Kod",        "amedit_code"),
        ("🎬 Nom (UZ)",   "amedit_title_uz"),
        ("🎬 Nom (RU)",   "amedit_title_ru"),
        ("🎭 Janr",       "amedit_genre"),
        ("📅 Yil",        "amedit_year"),
        ("⭐ Premium",    "amedit_premium"),
        ("📺 Serial",     "amedit_series"),
        ("📝 Tavsif",     "amedit_desc"),
    ]
    buttons = [
        [InlineKeyboardButton(text=t, callback_data=c)]
        for t, c in fields
    ]
    buttons.append([
        InlineKeyboardButton(text="✅ Saqlash",  callback_data="am_save"),
        InlineKeyboardButton(text="❌ Bekor",    callback_data="am_cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ════════════════════════════════════════════════════════════════════
#  ASOSIY HANDLER — Admin video/document yuborganda
# ════════════════════════════════════════════════════════════════════

@router.message(
    F.from_user.func(lambda u: u.id in ADMINS),
    F.video | F.document
)
async def admin_video_received(message: Message, state: FSMContext) -> None:
    """
    Admin video yuborganda caption dan parse qiladi va preview ko'rsatadi.

    MUHIM: Boshqa FSM holati bo'lsa (masalan FilmStates.waiting_video),
           bu handler o'tkazib yuboradi — aiogram router tartibiga ko'ra
           FSM state filter bilan belgilangan handler birinchi ishlaydi.
    """
    current_state = await state.get_state()

    # TUZATISH: 'State' in str() noto'g'ri — to'g'ri usul: is not None
    if current_state is not None:
        # Boshqa FSM holati faol — bu handler uchun emas
        return

    caption = message.caption or ""

    if message.video:
        file_id   = message.video.file_id
        file_type = "video"
    else:
        file_id   = message.document.file_id
        file_type = "document"

    data = _parse_caption(caption)
    data["file_id"]   = file_id
    data["file_type"] = file_type

    # Kod yo'q bo'lsa avtomatik generatsiya
    if not data["code"] and data["title"]:
        data["code"] = _gen_code(data["title"])
    elif not data["code"]:
        data["code"] = _gen_code("MOVIE")

    await state.update_data(am_data=data)

    preview = _preview_text(data, file_type)
    await message.answer(preview, reply_markup=_confirm_kb(), parse_mode="HTML")


# ════════════════════════════════════════════════════════════════════
#  SAQLASH
# ════════════════════════════════════════════════════════════════════

@router.callback_query(
    F.data == "am_save",
    F.from_user.func(lambda u: u.id in ADMINS)
)
async def am_save(call: CallbackQuery, state: FSMContext) -> None:
    state_data = await state.get_data()
    data = state_data.get("am_data", {})

    if not data.get("file_id"):
        await call.answer("❌ Fayl topilmadi! Qaytadan yuboring.", show_alert=True)
        return

    async with get_db() as db:
        # Unikal kod tekshirish va zarur bo'lsa o'zgartirish
        code = await _ensure_unique_code(db, data.get("code") or _gen_code("MOVIE"))

        title_uz = (data.get("title_uz") or data.get("title") or "Nomsiz").strip()
        title_ru = (data.get("title_ru") or "").strip() or None

        await db.execute(
            """
            INSERT INTO movies
              (code, title, title_uz, title_ru, genre, genres,
               year, is_premium, is_series, season, episode,
               file_id, description, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                code,
                title_uz,              # title (asosiy)
                title_uz,              # title_uz
                title_ru,              # title_ru
                data.get("genre"),     # genre (eski ustun)
                data.get("genre"),     # genres (yangi ustun)
                data.get("year"),
                data.get("is_premium", 0),
                data.get("is_series", 0),
                data.get("season"),
                data.get("episode"),
                data.get("file_id"),
                data.get("description"),
            )
        )
        await db.commit()

    await state.clear()

    series_info = ""
    if data.get("is_series"):
        series_info = f" | {data.get('season', 1)}-mavsum {data.get('episode', 1)}-qism"

    logger.info(
        "Yangi kino saqlandi: code=%s, title=%s, admin=%s",
        code, title_uz, call.from_user.id
    )

    await call.message.edit_text(
        f"✅ <b>Kino saqlandi!</b>\n\n"
        f"📌 Kod: <code>{code}</code>\n"
        f"🎬 Nom: {title_uz}{series_info}\n"
        f"⭐ Premium: {'Ha ✅' if data.get('is_premium') else 'Yo\'q'}",
        parse_mode="HTML"
    )
    await call.answer()


# ════════════════════════════════════════════════════════════════════
#  BEKOR QILISH
# ════════════════════════════════════════════════════════════════════

@router.callback_query(
    F.data == "am_cancel",
    F.from_user.func(lambda u: u.id in ADMINS)
)
async def am_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("❌ Bekor qilindi.")
    await call.answer()


# ════════════════════════════════════════════════════════════════════
#  TAHRIRLASH MENYUSI
# ════════════════════════════════════════════════════════════════════

@router.callback_query(
    F.data == "am_edit",
    F.from_user.func(lambda u: u.id in ADMINS)
)
async def am_edit_menu(call: CallbackQuery, state: FSMContext) -> None:
    state_data = await state.get_data()
    data = state_data.get("am_data", {})
    preview = _preview_text(data, data.get("file_type", "video"))
    await call.message.edit_text(
        preview + "\n\n🔧 Qaysi maydonni tahrirlash?",
        reply_markup=_edit_kb(),
        parse_mode="HTML"
    )
    await call.answer()


# ════════════════════════════════════════════════════════════════════
#  MAYDON TANLASH
# ════════════════════════════════════════════════════════════════════

_EDIT_PROMPTS = {
    "code":     "📌 Yangi kod kiriting (masalan: AVATAR1):",
    "title_uz": "🎬 O'zbekcha nom kiriting:",
    "title_ru": "🎬 Ruscha nom kiriting:",
    "genre":    "🎭 Janr kiriting (masalan: Drama, Komediya):",
    "year":     "📅 Yil kiriting (masalan: 2024):",
    "premium":  "⭐ Premium? Yozing: ha yoki yo'q",
    "series":   "📺 Serial ma'lumot (masalan: s1e5) yoki 'yo'q':",
    "desc":     "📝 Tavsif kiriting (max 500 belgi):",
}


@router.callback_query(
    F.data.startswith("amedit_"),
    F.from_user.func(lambda u: u.id in ADMINS)
)
async def am_edit_field(call: CallbackQuery, state: FSMContext) -> None:
    field = call.data.replace("amedit_", "")
    if field not in _EDIT_PROMPTS:
        await call.answer("❌ Noto'g'ri maydon!", show_alert=True)
        return

    await state.update_data(am_edit_field=field)
    await state.set_state(AddMovieEditState.waiting_field_value)
    await call.message.answer(_EDIT_PROMPTS[field])
    await call.answer()


# ════════════════════════════════════════════════════════════════════
#  MAYDON QIYMATINI SAQLASH
# ════════════════════════════════════════════════════════════════════

@router.message(
    AddMovieEditState.waiting_field_value,
    F.from_user.func(lambda u: u.id in ADMINS)
)
async def am_edit_save(message: Message, state: FSMContext) -> None:
    state_data = await state.get_data()
    field = state_data.get("am_edit_field")
    data  = state_data.get("am_data", {})
    val   = (message.text or "").strip()

    if not val:
        await message.answer("❌ Bo'sh qiymat kiritildi. Iltimos qaytadan yuboring.")
        return

    if field == "code":
        data["code"] = re.sub(r'[^A-Z0-9]', '', val.upper())[:10] or data["code"]

    elif field == "title_uz":
        data["title_uz"] = val[:100]
        data["title"]    = val[:100]   # asosiy nom ham yangilanadi

    elif field == "title_ru":
        data["title_ru"] = val[:100]

    elif field == "genre":
        data["genre"] = val[:50]

    elif field == "year":
        if val.isdigit() and 1900 <= int(val) <= 2030:
            data["year"] = int(val)
        else:
            await message.answer("❌ Yil noto'g'ri! 1900-2030 oralig'ida kiriting.")
            return

    elif field == "premium":
        data["is_premium"] = 1 if val.lower() in ("ha", "yes", "1", "+") else 0

    elif field == "series":
        if val.lower() in ("yo'q", "yoq", "no", "0", "-"):
            data["is_series"] = 0
            data["season"]    = None
            data["episode"]   = None
        else:
            m = re.search(r's(\d+)e(\d+)', val, re.IGNORECASE)
            if m:
                data["is_series"] = 1
                data["season"]    = int(m.group(1))
                data["episode"]   = int(m.group(2))
            else:
                await message.answer("❌ Format noto'g'ri! Misol: s1e5")
                return

    elif field == "desc":
        data["description"] = val[:500]

    await state.update_data(am_data=data)
    await state.set_state(None)

    preview = _preview_text(data, data.get("file_type", "video"))
    await message.answer(preview, reply_markup=_confirm_kb(), parse_mode="HTML")
