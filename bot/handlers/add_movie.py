"""
Kino qo'shish — aqlli caption parser
Admin videoni caption bilan yuboradi, bot o'zi parse qiladi.

Caption misollari (hammasi ishlaydi):
  Avatar 2009 Fantastika premium
  #AVATAR1 Avatar - Fantastika - 2009
  Kod: AVT1, Nom: Avatar, Janr: Drama, Yil: 2009, Premium
  Merlin S01E01 - Serial - Fantasy
  MRLN101 | Merlin | Fantasy | 2009 | serial | s1e1
"""

import re
import random
import string

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS
from bot.database.db import get_db

router = Router()

GENRES = [
    "Drama", "Komediya", "Boevik", "Triller", "Fantastika",
    "Melodrama", "Qo'rqinchli", "Animatsiya", "Hujjatli",
    "Biografiya", "Tarix", "Sport", "Musiqa", "Serial",
    "Fantasy", "Kriminal", "Harbiy", "Sarguzasht"
]

def is_admin(uid: int) -> bool:
    return uid in ADMINS

def gen_code(title: str) -> str:
    """Kino nomidan avtomatik kod generatsiya qiladi."""
    words = re.sub(r'[^a-zA-Z0-9\s]', '', title.upper()).split()
    if words:
        code = ''.join(w[:3] for w in words[:3])
    else:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    suffix = ''.join(random.choices(string.digits, k=2))
    return (code + suffix)[:8]

def parse_caption(caption: str) -> dict:
    """
    Caption dan kino ma'lumotlarini aqlli parse qiladi.
    Turli formatlarni qo'llab-quvvatlaydi.
    """
    data = {
        "code": None,
        "title": None,
        "genre": None,
        "year": None,
        "is_premium": 0,
        "is_series": 0,
        "season": None,
        "episode": None,
        "description": None,
    }

    text = caption.strip()

    # ── 1. Kod — #KOD yoki Kod: KOD yoki KOD | ... ──────────────────
    code_match = re.search(r'#([A-Z0-9]{2,10})', text.upper())
    if not code_match:
        code_match = re.search(r'(?:kod|code)[:\s]+([A-Z0-9]{2,10})', text, re.IGNORECASE)
    if not code_match:
        # Birinchi so'z katta harf va raqamlardan iborat bo'lsa
        first_word = text.split()[0] if text.split() else ""
        if re.match(r'^[A-Z0-9]{3,10}$', first_word.upper()):
            data["code"] = first_word.upper()
    else:
        data["code"] = code_match.group(1).upper()

    # ── 2. Yil — 4 ta raqam 1900-2030 ───────────────────────────────
    year_match = re.search(r'\b(19\d{2}|20[0-3]\d)\b', text)
    if year_match:
        data["year"] = int(year_match.group(1))

    # ── 3. Serial — S01E01 yoki s1e1 yoki "serial" so'zi ────────────
    series_match = re.search(r's(\d{1,2})e(\d{1,3})', text, re.IGNORECASE)
    if series_match:
        data["is_series"] = 1
        data["season"] = int(series_match.group(1))
        data["episode"] = int(series_match.group(2))
    elif re.search(r'\bserial\b', text, re.IGNORECASE):
        data["is_series"] = 1

    # ── 4. Premium ───────────────────────────────────────────────────
    if re.search(r'\bpremium\b', text, re.IGNORECASE):
        data["is_premium"] = 1

    # ── 5. Janr ──────────────────────────────────────────────────────
    genre_match = re.search(r'(?:janr|жанр|genre)[:\s]+([^\n,|]+)', text, re.IGNORECASE)
    if genre_match:
        data["genre"] = genre_match.group(1).strip()
    else:
        for g in GENRES:
            if g.lower() in text.lower():
                data["genre"] = g
                break

    # ── 6. Tavsif ────────────────────────────────────────────────────
    desc_match = re.search(r'(?:tavsif|описание|desc)[:\s]+(.+)', text, re.IGNORECASE | re.DOTALL)
    if desc_match:
        data["description"] = desc_match.group(1).strip()[:500]

    # ── 7. Nom — eng muhim qism ──────────────────────────────────────
    # Pipe | yoki tire - ajratgichdan nom olish
    pipe_parts = [p.strip() for p in re.split(r'[|\-—]', text) if p.strip()]

    if len(pipe_parts) >= 2:
        # Birinchi qism kod bo'lishi mumkin
        candidate = pipe_parts[0]
        if data["code"] and candidate.upper() == data["code"]:
            data["title"] = pipe_parts[1] if len(pipe_parts) > 1 else None
        else:
            data["title"] = candidate
    else:
        # Oddiy matn — yil, kod, janr, kalit so'zlarni olib tashlash
        clean = text
        if data["code"]:
            clean = re.sub(re.escape(data["code"]), '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'#\w+', '', clean)
        clean = re.sub(r'\b(19\d{2}|20[0-3]\d)\b', '', clean)
        clean = re.sub(r'\bpremium\b', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\bserial\b', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r's\d{1,2}e\d{1,3}', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'(?:kod|janr|tavsif)[:\s]+[^\n]+', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'[|,]+', ' ', clean)
        clean = ' '.join(clean.split())

        if clean and len(clean) >= 2:
            data["title"] = clean[:100]

    # ── 8. Nom bo'sh bo'lsa — caption boshidan olish ─────────────────
    if not data["title"] and text:
        first_line = text.split('\n')[0].strip()
        data["title"] = first_line[:100]

    return data


def preview_text(data: dict, file_type: str) -> str:
    """Tahlil natijasini ko'rsatish uchun matn."""
    code = data.get("code") or "— (avtomatik)"
    title = data.get("title") or "—"
    genre = data.get("genre") or "—"
    year = data.get("year") or "—"
    premium = "✅ Ha" if data.get("is_premium") else "❌ Yo'q"
    is_series = data.get("is_series", 0)
    series_info = ""
    if is_series:
        s = data.get("season") or "?"
        e = data.get("episode") or "?"
        series_info = f"\n📺 Serial: {s}-mavsum, {e}-qism"

    return (
        f"📋 <b>Kino ma'lumotlari:</b>\n\n"
        f"📌 Kod: <code>{code}</code>\n"
        f"🎬 Nom: {title}\n"
        f"🎭 Janr: {genre}\n"
        f"📅 Yil: {year}\n"
        f"⭐ Premium: {premium}"
        f"{series_info}\n"
        f"🎞 Fayl: {file_type}\n\n"
        f"To'g'rimi? Tasdiqlang yoki tahrirlang:"
    )


def confirm_kb(is_correct: bool = True) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Saqlash", callback_data="movie_save"),
            InlineKeyboardButton(text="✏️ Tahrirlash", callback_data="movie_edit"),
        ],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="movie_cancel")],
    ])


def edit_kb() -> InlineKeyboardMarkup:
    fields = [
        ("📌 Kod",      "medit_code"),
        ("🎬 Nom",      "medit_title"),
        ("🎭 Janr",     "medit_genre"),
        ("📅 Yil",      "medit_year"),
        ("⭐ Premium",  "medit_premium"),
        ("📺 Serial",   "medit_series"),
        ("📝 Tavsif",   "medit_desc"),
    ]
    buttons = [
        [InlineKeyboardButton(text=t, callback_data=c)]
        for t, c in fields
    ]
    buttons.append([
        InlineKeyboardButton(text="✅ Saqlash", callback_data="movie_save"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="movie_cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


class EditFieldState(StatesGroup):
    waiting = State()
    field   = State()


# ════════════════════════════════════════════════════════════════════
#  ASOSIY HANDLER — Admin video yuborganda
# ════════════════════════════════════════════════════════════════════

@router.message(
    F.from_user.func(lambda u: u.id in ADMINS),
    F.video | F.document
)
async def admin_video_received(message: Message, state: FSMContext):
    """Admin video yuborganda caption dan parse qiladi."""

    # Faqat admin panel rejimida ishlaydi
    # (boshqa FSM holati bo'lsa — o'tkazib yuboramiz)
    current_state = await state.get_state()
    if current_state and "State" in str(current_state):
        # Boshqa FSM holati bor — bu handler uchun emas
        return

    caption = message.caption or ""

    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    else:
        file_id = message.document.file_id
        file_type = "document"

    # Parse qilish
    data = parse_caption(caption)
    data["file_id"] = file_id
    data["file_type"] = file_type

    # Kod yo'q bo'lsa avtomatik generatsiya
    if not data["code"] and data["title"]:
        data["code"] = gen_code(data["title"])

    # State ga saqlash
    await state.update_data(movie_data=data)

    preview = preview_text(data, file_type)
    await message.answer(preview, reply_markup=confirm_kb(), parse_mode="HTML")


# ── Saqlash ──────────────────────────────────────────────────────────
@router.callback_query(F.data == "movie_save", F.from_user.func(lambda u: u.id in ADMINS))
async def movie_save(call: CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    data = state_data.get("movie_data", {})

    if not data.get("file_id"):
        await call.answer("❌ Fayl topilmadi!", show_alert=True)
        return

    # Kod bo'sh bo'lsa generatsiya
    if not data.get("code"):
        data["code"] = gen_code(data.get("title", "MOVIE"))

    # Kod unique tekshirish
    async with get_db() as db:
        async with db.execute(
            "SELECT 1 FROM movies WHERE code = ?", (data["code"],)
        ) as cur:
            exists = await cur.fetchone()

    if exists:
        # Kod mavjud — oxiriga raqam qo'shamiz
        data["code"] = data["code"] + str(random.randint(1, 99))

    async with get_db() as db:
        await db.execute("""
            INSERT INTO movies
            (code, title, genre, year, is_premium, is_series,
             season, episode, file_id, description, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (
            data.get("code"),
            data.get("title") or "Nomsiz",
            data.get("genre"),
            data.get("year"),
            data.get("is_premium", 0),
            data.get("is_series", 0),
            data.get("season"),
            data.get("episode"),
            data.get("file_id"),
            data.get("description"),
        ))
        await db.commit()

    await state.clear()

    series_info = ""
    if data.get("is_series"):
        series_info = f" | {data.get('season',1)}-mavsum {data.get('episode',1)}-qism"

    await call.message.edit_text(
        f"✅ <b>Kino saqlandi!</b>\n\n"
        f"📌 Kod: <code>{data['code']}</code>\n"
        f"🎬 Nom: {data.get('title') or 'Nomsiz'}{series_info}\n"
        f"⭐ Premium: {'Ha' if data.get('is_premium') else 'Yo'q'}",
        parse_mode="HTML"
    )
    await call.answer()


# ── Bekor qilish ─────────────────────────────────────────────────────
@router.callback_query(F.data == "movie_cancel", F.from_user.func(lambda u: u.id in ADMINS))
async def movie_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Bekor qilindi.")
    await call.answer()


# ── Tahrirlash menyusi ───────────────────────────────────────────────
@router.callback_query(F.data == "movie_edit", F.from_user.func(lambda u: u.id in ADMINS))
async def movie_edit_menu(call: CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    data = state_data.get("movie_data", {})
    preview = preview_text(data, data.get("file_type", "video"))
    await call.message.edit_text(
        preview + "\n\nQaysi maydonni tahrirlash?",
        reply_markup=edit_kb(),
        parse_mode="HTML"
    )
    await call.answer()


# ── Maydon tahrirlash ────────────────────────────────────────────────
@router.callback_query(
    F.data.startswith("medit_"),
    F.from_user.func(lambda u: u.id in ADMINS)
)
async def movie_edit_field(call: CallbackQuery, state: FSMContext):
    field = call.data.replace("medit_", "")
    prompts = {
        "code":    "📌 Yangi kod kiriting (masalan: AVATAR1):",
        "title":   "🎬 Yangi nom kiriting:",
        "genre":   "🎭 Janr kiriting (masalan: Drama, Komediya):",
        "year":    "📅 Yil kiriting (masalan: 2024):",
        "premium": "⭐ Premium? ha yoki yo'q:",
        "series":  "📺 Serial ma'lumot kiriting (masalan: s1e5) yoki 'yo'q':",
        "desc":    "📝 Tavsif kiriting:",
    }
    await state.update_data(edit_field=field)
    await state.set_state(EditFieldState.waiting)
    await call.message.answer(prompts.get(field, "Yangi qiymat:"))
    await call.answer()


@router.message(EditFieldState.waiting, F.from_user.func(lambda u: u.id in ADMINS))
async def movie_edit_save(message: Message, state: FSMContext):
    state_data = await state.get_data()
    field = state_data.get("edit_field")
    data = state_data.get("movie_data", {})
    val = message.text.strip()

    if field == "code":
        data["code"] = val.upper()
    elif field == "title":
        data["title"] = val
    elif field == "genre":
        data["genre"] = val
    elif field == "year":
        try:
            data["year"] = int(val)
        except ValueError:
            await message.answer("❌ Faqat son kiriting!")
            return
    elif field == "premium":
        data["is_premium"] = 1 if val.lower() in ("ha", "yes", "1") else 0
    elif field == "series":
        if val.lower() in ("yo'q", "yoq", "no", "0"):
            data["is_series"] = 0
            data["season"] = None
            data["episode"] = None
        else:
            m = re.search(r's(\d+)e(\d+)', val, re.IGNORECASE)
            if m:
                data["is_series"] = 1
                data["season"] = int(m.group(1))
                data["episode"] = int(m.group(2))
            else:
                await message.answer("❌ Format: s1e5 (mavsum 1, qism 5)")
                return
    elif field == "desc":
        data["description"] = val[:500]

    await state.update_data(movie_data=data)
    await state.set_state(None)

    preview = preview_text(data, data.get("file_type", "video"))
    await message.answer(preview, reply_markup=confirm_kb(), parse_mode="HTML")
