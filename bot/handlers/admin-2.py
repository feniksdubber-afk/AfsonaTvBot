import csv
import io
import asyncio
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton          # BUG #1 FIX: import qo'shildi
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS, CHANNEL_PRIVATE, CHANNEL_PUBLIC
from bot.database.db import get_db
from bot.keyboards.admin_kb import (
    admin_menu, movie_manage_kb, edit_movie_kb,
    confirm_kb, user_manage_kb, requests_kb
)
from bot.keyboards import admin_kb as custom_admin_kb
from bot.keyboards.user_kb import main_menu
from bot.utils.admin_tools import generate_unique_code

router = Router()

# ── Admin filter ───────────────────────────────────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


# ── FSM STATES ─────────────────────────────────────────────────────────
class FilmStates(StatesGroup):
    waiting_video       = State()
    waiting_titles      = State()
    waiting_country_year = State()
    waiting_genres      = State()
    waiting_poster      = State()
    waiting_description = State()
    waiting_premium     = State()

class SeriesStates(StatesGroup):
    waiting_titles       = State()
    waiting_country_year = State()
    waiting_genres       = State()
    waiting_poster       = State()
    waiting_description  = State()
    waiting_premium      = State()
    waiting_episodes     = State()

class EditContentState(StatesGroup):
    waiting_code = State()

class BroadcastState(StatesGroup):
    waiting = State()

class MsgUserState(StatesGroup):
    waiting = State()
    target  = State()

class GivePremiumState(StatesGroup):
    waiting = State()
    target  = State()


# ── /admin BUYRUG'I ────────────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Admin Panel</b>", reply_markup=admin_menu(), parse_mode="HTML")


# ── FILM VA SERIAL QO'SHISH BOSHLANISHI ───────────────────────────────
@router.message(F.text == "🎬 Kino qo'shish", F.from_user.id.in_(ADMINS))
async def start_add_content(message: Message):
    await message.answer("🎬 Nima qo'shmoqchisiz? Tanlang:", reply_markup=custom_admin_kb.content_type_kb())


# ══════════════════════════════════════════════════════════════════════
#  A. FILM QO'SHISH FLOWI (FSM)
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "add_type_film", F.from_user.id.in_(ADMINS))
async def add_film_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(FilmStates.waiting_video)
    await call.message.edit_text("🎥 Film videosini yuboring:", reply_markup=custom_admin_kb.cancel_fsm_kb())
    await call.answer()

@router.message(FilmStates.waiting_video, F.video)
async def process_film_video(message: Message, state: FSMContext):
    await state.update_data(file_id=message.video.file_id)
    await state.set_state(FilmStates.waiting_titles)
    await message.answer(
        "📝 Film nomlarini yuboring:\n1-qator: O'zbekcha nomi\n2-qator: Ruscha nomi",
        reply_markup=custom_admin_kb.cancel_fsm_kb()
    )

@router.message(FilmStates.waiting_titles, F.text)
async def process_film_titles(message: Message, state: FSMContext):
    lines = message.text.splitlines()
    if len(lines) < 2:
        await message.answer("❌ Iltimos, nomlarni 2 qatorda yuboring (O'zbekcha va Ruscha)!")
        return
    await state.update_data(title_uz=lines[0].strip(), title_ru=lines[1].strip())
    await state.set_state(FilmStates.waiting_country_year)
    await message.answer(
        "🌍 Mamlakat va 📅 Yilni 2 qatorda yuboring:\n\nMisol:\nFransiya\n2012",
        reply_markup=custom_admin_kb.cancel_fsm_kb()
    )

@router.message(FilmStates.waiting_country_year, F.text)
async def process_film_country_year(message: Message, state: FSMContext):
    lines = message.text.splitlines()
    if len(lines) < 2 or not lines[1].strip().isdigit():
        await message.answer("❌ Format xato! Mamlakat va Yilni to'g'ri kiriting.")
        return
    await state.update_data(country=lines[0].strip(), year=int(lines[1].strip()))
    await state.set_state(FilmStates.waiting_genres)
    await message.answer(
        "🎭 Kamida 2 ta janr yuboring (Har biri yangi qatorda):",
        reply_markup=custom_admin_kb.cancel_fsm_kb()
    )

@router.message(FilmStates.waiting_genres, F.text)
async def process_film_genres(message: Message, state: FSMContext):
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    if len(lines) < 2:
        await message.answer("❌ Kamida 2 ta janr kiriting!")
        return
    await state.update_data(genres=", ".join(lines))
    await state.set_state(FilmStates.waiting_poster)
    await message.answer("🖼 Poster yuboring (Rasm):", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(FilmStates.waiting_poster, F.photo)
async def process_film_poster(message: Message, state: FSMContext):
    await state.update_data(poster_file_id=message.photo[-1].file_id)
    await state.set_state(FilmStates.waiting_description)
    await message.answer("✍️ Film uchun qisqa qiziqarli tavsif yozing:", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(FilmStates.waiting_description, F.text)
async def process_film_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(FilmStates.waiting_premium)
    await message.answer(
        "⭐ Ushbu film Premium foydalanuvchilar uchun bo'lsinmi?",
        reply_markup=custom_admin_kb.is_premium_kb()
    )

@router.callback_query(FilmStates.waiting_premium, F.data.startswith("premium_"))
async def save_film_final(call: CallbackQuery, state: FSMContext, bot: Bot):
    is_premium = 1 if call.data == "premium_yes" else 0
    data = await state.get_data()
    await state.clear()

    title_uz = data.get("title_uz", "").strip()
    if not title_uz:
        await call.message.edit_text("❌ Xato: O'zbekcha nom aniqlanmadi, jarayon bekor qilindi.")
        await call.answer()
        return

    async with get_db() as db:
        code = await generate_unique_code(db)
        await db.execute("""
            INSERT INTO movies
              (code, title, title_uz, title_ru, country, year, genres,
               description, file_id, poster_file_id, is_premium, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (
            code, title_uz, title_uz, data["title_ru"],
            data["country"], data["year"], data["genres"],
            data["description"], data["file_id"], data["poster_file_id"],
            is_premium
        ))
        await db.commit()

    # Private kanalga backup
    try:
        await bot.send_video(
            chat_id=CHANNEL_PRIVATE,
            video=data["file_id"],
            caption=(
                f"📦 BACKUP | FILM\n🔑 KOD: {code}\n"
                f"🎬 NOM (UZ): {title_uz}\n🌐 NOM (RU): {data['title_ru']}"
            )
        )
    except Exception as e:
        print(f"Private backup error: {e}")

    # Public kanalga reklama posti
    bot_user = await bot.get_me()
    premium_tag = "⭐ PREMIUM" if is_premium else "🔓 TEKIN"
    pub_caption = (
        f"🎬 <b>{title_uz.upper()}</b>\n"
        f"🌍 {data['country']} | 📅 {data['year']}\n"
        f"🎭 {data['genres']}\n"
        f"Status: {premium_tag}\n\n"
        f"🍿 {data['description']}\n\n"
        f"👇 Tomosha qilish uchun tugmani bosing"
    )
    watch_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🎬 TOMOSHA QILISH",
            url=f"https://t.me/{bot_user.username}?start=movie_{code}"
        )
    ]])
    try:
        await bot.send_photo(
            chat_id=CHANNEL_PUBLIC,
            photo=data["poster_file_id"],
            caption=pub_caption,
            reply_markup=watch_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Public post error: {e}")

    await call.message.edit_text(
        f"✅ Film muvaffaqiyatli saqlandi!\n🔑 Avtomatik kod: <code>{code}</code>",
        parse_mode="HTML"
    )
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  B. SERIAL QO'SHISH FLOWI (FSM)
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "add_type_series", F.from_user.id.in_(ADMINS))
async def add_series_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(SeriesStates.waiting_titles)
    await call.message.edit_text(
        "📝 Serial nomlarini yuboring:\n1-qator: O'zbekcha nomi\n2-qator: Ruscha nomi",
        reply_markup=custom_admin_kb.cancel_fsm_kb()
    )
    await call.answer()

@router.message(SeriesStates.waiting_titles, F.text)
async def process_series_titles(message: Message, state: FSMContext):
    lines = message.text.splitlines()
    if len(lines) < 2:
        await message.answer("❌ Iltimos, serial nomlarini 2 qatorda yuboring!")
        return
    await state.update_data(title_uz=lines[0].strip(), title_ru=lines[1].strip())
    await state.set_state(SeriesStates.waiting_country_year)
    await message.answer(
        "🌍 Mamlakat va 📅 Yilni 2 qatorda yuboring:\n\nMisol:\nKoreya\n2023",
        reply_markup=custom_admin_kb.cancel_fsm_kb()
    )

@router.message(SeriesStates.waiting_country_year, F.text)
async def process_series_country_year(message: Message, state: FSMContext):
    lines = message.text.splitlines()
    if len(lines) < 2 or not lines[1].strip().isdigit():
        await message.answer("❌ Noto'g'ri format! Mamlakat va Yilni kiriting.")
        return
    await state.update_data(country=lines[0].strip(), year=int(lines[1].strip()))
    await state.set_state(SeriesStates.waiting_genres)
    await message.answer(
        "🎭 Kamida 2 ta janr yuboring (Har biri yangi qatorda):",
        reply_markup=custom_admin_kb.cancel_fsm_kb()
    )

@router.message(SeriesStates.waiting_genres, F.text)
async def process_series_genres(message: Message, state: FSMContext):
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    if len(lines) < 2:
        await message.answer("❌ Kamida 2 ta janr kiritishingiz shart!")
        return
    await state.update_data(genres=", ".join(lines))
    await state.set_state(SeriesStates.waiting_poster)
    await message.answer("🖼 Poster yuboring (Rasm):", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(SeriesStates.waiting_poster, F.photo)
async def process_series_poster(message: Message, state: FSMContext):
    await state.update_data(poster_file_id=message.photo[-1].file_id)
    await state.set_state(SeriesStates.waiting_description)
    await message.answer("✍️ Serial uchun qisqa qiziqarli tavsif yozing:", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(SeriesStates.waiting_description, F.text)
async def process_series_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(SeriesStates.waiting_premium)
    await message.answer(
        "⭐ Ushbu serial Premium foydalanuvchilar uchun bo'lsinmi?",
        reply_markup=custom_admin_kb.is_premium_kb()
    )

@router.callback_query(SeriesStates.waiting_premium, F.data.startswith("premium_"))
async def save_series_main_info(call: CallbackQuery, state: FSMContext):
    is_premium = 1 if call.data == "premium_yes" else 0
    await state.update_data(is_premium=is_premium, current_season=1)
    data = await state.get_data()

    async with get_db() as db:
        code = await generate_unique_code(db)
        await state.update_data(code=code)
        async with db.execute("""
            INSERT INTO series
              (code, title_uz, title_ru, country, year, genres,
               poster_file_id, description, is_premium, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (
            code, data["title_uz"], data["title_ru"],
            data["country"], data["year"], data["genres"],
            data["poster_file_id"], data["description"], is_premium
        )) as cur:
            series_id = cur.lastrowid

        await db.execute(
            "INSERT INTO seasons (series_id, season_number) VALUES (?, 1)",
            (series_id,)
        )
        await db.commit()
        await state.update_data(series_id=series_id)

    await state.set_state(SeriesStates.waiting_episodes)
    await call.message.edit_text(
        f"✅ Serial bazasi yaratildi! (Kod: <code>{code}</code>)\n\n"
        f"📀 Hozirgi joylashuv: 1-Fasl\n"
        f"📺 Endi qismlarni yuboring. Video captionga faqat qism raqamini yozing (Masalan: 1)\n\n"
        f"Tugmalardan foydalanib keyingi faslga o'tishingiz yoki jarayonni yakunlashingiz mumkin.",
        reply_markup=custom_admin_kb.series_control_kb(),
        parse_mode="HTML"
    )
    await call.answer()

@router.message(SeriesStates.waiting_episodes, F.video)
async def process_series_episode_file(message: Message, state: FSMContext, bot: Bot):
    caption = message.caption or ""
    if not caption.strip().isdigit():
        await message.answer("❌ Xato! Videoning caption qismiga faqat qism raqamini yozing (Masalan: 1)")
        return

    ep_num = int(caption.strip())
    data = await state.get_data()

    async with get_db() as db:
        try:
            await db.execute("""
                INSERT INTO episodes (series_id, season_number, episode_number, file_id)
                VALUES (?, ?, ?, ?)
            """, (data["series_id"], data["current_season"], ep_num, message.video.file_id))
            await db.commit()
        except Exception:
            await message.answer(
                f"⚠️ {data['current_season']}-fasl {ep_num}-qism allaqachon yuklangan yoki xatolik yuz berdi!"
            )
            return

    try:
        await bot.send_video(
            chat_id=CHANNEL_PRIVATE,
            video=message.video.file_id,
            caption=(
                f"📦 BACKUP | SERIAL\n🔑 KOD: {data['code']}\n"
                f"📺 {data['title_uz']}\n"
                f"📀 Fasl: {data['current_season']} | Qism: {ep_num}"
            )
        )
    except Exception:
        pass

    await message.answer(
        f"✅ {data['current_season']}-fasl {ep_num}-qism saqlandi!",
        reply_markup=custom_admin_kb.series_control_kb()
    )

@router.callback_query(SeriesStates.waiting_episodes, F.data == "series_next_season")
async def process_next_season_switch(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    next_season = data["current_season"] + 1

    async with get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO seasons (series_id, season_number) VALUES (?, ?)",
            (data["series_id"], next_season)
        )
        await db.commit()

    await state.update_data(current_season=next_season)
    await call.message.edit_text(
        f"📀 Tizim {next_season}-faslga o'tdi.\n\n"
        f"📺 Endi {next_season}-faslning videolarini yuklashingiz mumkin. "
        f"Captionga faqat qism raqamini yozing.",
        reply_markup=custom_admin_kb.series_control_kb()
    )
    await call.answer()

@router.callback_query(SeriesStates.waiting_episodes, F.data == "series_finish")
async def process_series_finish_all(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    bot_user = await bot.get_me()
    premium_tag = "⭐ PREMIUM" if data["is_premium"] else "🔓 TEKIN"
    pub_caption = (
        f"📺 <b>{data['title_uz'].upper()} (Yangi Serial)</b>\n"
        f"🎭 Janr: {data['genres']}\n"
        f"🌍 Davlat: {data['country']} | 📅 Yil: {data['year']}\n"
        f"Status: {premium_tag}\n\n"
        f"🍿 {data['description']}\n\n"
        f"👇 Barcha fasl va qismlarni ko'rish uchun pastdagi tugmani bosing"
    )
    watch_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🎬 SERIALNI KO'RISH",
            url=f"https://t.me/{bot_user.username}?start=series_{data['code']}"
        )
    ]])
    try:
        await bot.send_photo(
            chat_id=CHANNEL_PUBLIC,
            photo=data["poster_file_id"],
            caption=pub_caption,
            reply_markup=watch_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Public series post error: {e}")

    await call.message.edit_text(
        f"🚀 Serial to'liq yuklandi va e'lon qilindi!\n"
        f"🔑 Avtomatik kod: <code>{data['code']}</code>",
        parse_mode="HTML"
    )
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  FSM BEKOR QILISH
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "cancel_admin_fsm")
async def cancel_fsm_process(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Jarayon bekor qilindi.")
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  C. TAHRIRLASH, ARXIV VA SOFT-DELETE
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "✏️ Kontentni tahrirlash", F.from_user.id.in_(ADMINS))
async def admin_edit_start_process(message: Message, state: FSMContext):
    await state.set_state(EditContentState.waiting_code)
    await message.answer("🔍 Tahrirlamoqchi bo'lgan kontent (Film yoki Serial) kodini yuboring:")

@router.message(EditContentState.waiting_code, F.text)
async def process_find_content_to_edit(message: Message, state: FSMContext):
    code = message.text.strip()
    await state.clear()

    async with get_db() as db:
        async with db.execute(
            "SELECT id, title_uz, status FROM movies WHERE code = ?", (code,)
        ) as cur:
            movie = await cur.fetchone()
        async with db.execute(
            "SELECT id, title_uz, status FROM series WHERE code = ?", (code,)
        ) as cur:
            series = await cur.fetchone()

    if not movie and not series:
        await message.answer("❌ Ushbu kod bilan hech qanday kino yoki serial topilmadi!")
        return

    is_movie = bool(movie)
    c_id     = movie[0] if is_movie else series[0]
    title    = movie[1] if is_movie else series[1]
    status   = movie[2] if is_movie else series[2]
    c_type   = "movie" if is_movie else "series"

    archive_txt = "📥 Arxivga olish" if status == "active" else "📤 Arxivdan chiqarish"
    archive_cb  = f"status_archive_{c_type}_{c_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=archive_txt, callback_data=archive_cb),
            InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"status_delete_{c_type}_{c_id}")
        ],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_admin_panel")]
    ])

    await message.answer(
        f"🎬 Kontent topildi:\n\n"
        f"📌 Nomi: <b>{title}</b>\n"
        f"🗂 Turi: <code>{c_type.upper()}</code>\n"
        f"🚦 Status: <code>{status.upper()}</code>\n\n"
        f"Kerakli boshqaruvni tanlang:",
        reply_markup=kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("status_"))
async def process_content_status_change(call: CallbackQuery):
    parts  = call.data.split("_")
    action = parts[1]
    c_type = parts[2]
    c_id   = int(parts[3])
    table  = "movies" if c_type == "movie" else "series"

    async with get_db() as db:
        if action == "delete":
            await db.execute(f"UPDATE {table} SET status = 'deleted' WHERE id = ?", (c_id,))
            msg = "🗑 Kontent muvaffaqiyatli 'deleted' holatiga o'tkazildi (soft-delete)!"
        elif action == "archive":
            async with db.execute(
                f"SELECT status FROM {table} WHERE id = ?", (c_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                await call.answer("❌ Kontent topilmadi!", show_alert=True)
                return
            new_status = "archived" if row[0] == "active" else "active"
            await db.execute(f"UPDATE {table} SET status = ? WHERE id = ?", (new_status, c_id))
            msg = f"🚀 Kontent statusi muvaffaqiyatli '{new_status}' ga yangilandi!"
        else:
            await call.answer()
            return
        await db.commit()

    await call.message.edit_text(f"✅ {msg}")
    await call.answer()

@router.callback_query(F.data == "close_admin_panel")
async def cb_close_admin_panel_edit(call: CallbackQuery):
    await call.message.delete()
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  D. KINOLAR RO'YXATI VA KO'RISH
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "📋 Kinolar ro'yxati")
async def admin_movies(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with get_db() as db:
        async with db.execute(
            "SELECT id, code, COALESCE(title_uz, title, 'Nomsiz') FROM movies ORDER BY id DESC LIMIT 20"
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await message.answer("Kinolar yo'q.")
        return

    text = "🎬 <b>Oxirgi 20 ta kino:</b>\n\n"
    for r in rows:
        text += f"▪️ <code>{r[1]}</code> — {r[2]} /admin_movie_{r[0]}\n"
    await message.answer(text, parse_mode="HTML")


# BUG #2 FIX: get_db() context manager tashqarisida ishlatilgan edi —
# to'liq qayta yozildi. Endi barcha DB operatsiyalari bitta `async with` ichida.
@router.message(F.text.startswith("/admin_movie_"))
async def admin_movie_view(message: Message):
    if not is_admin(message.from_user.id):
        return

    # BUG #2 FIX: "/admin_movie_" prefix uzunligi 13. split("_")[2] emas,
    # to'g'ridan-to'g'ri slice ishlatamiz (split xato indeks berishi mumkin).
    try:
        m_id = int(message.text[len("/admin_movie_"):])
    except ValueError:
        await message.answer("❌ Noto'g'ri kino ID!")
        return

    # BUG #2 FIX: barcha DB ishini bitta context ichida bajaramiz.
    # Oldin DB ni yopib, keyin get_db().execute() deb qayta ochilayotgan edi —
    # bu context manager tashqarisida await bo'lgan singan pattern edi.
    async with get_db() as db:
        async with db.execute("SELECT * FROM movies WHERE id = ?", (m_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                await message.answer("Kino topilmadi.")
                return
            cols = [d[0] for d in cur.description]   # cursor hali ochiq — to'g'ri
            m    = dict(zip(cols, row))

    text = (
        f"🎬 <b>{m.get('title_uz') or m.get('title', 'Nomsiz')}</b>\n\n"
        f"🔑 Kod: <code>{m['code']}</code>\n"
        f"🎭 Janr: {m.get('genres') or m.get('genre', '—')}\n"
        f"📅 Yil: {m.get('year', '—')}\n"
        f"🌍 Mamlakat: {m.get('country', '—')}\n"
        f"👁 Ko'rishlar: {m.get('views', 0)}\n"
        f"⭐ Reyting: {m.get('rating', 0)}\n"
        f"🔒 Premium: {'Ha' if m.get('is_premium') else 'Yoq'}\n"
        f"🚦 Status: {m.get('status', 'active')}\n"
    )
    await message.answer(text, reply_markup=movie_manage_kb(m_id), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════
#  E. STATISTIKA
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "📊 Statistika")
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    today = datetime.now().strftime("%Y-%m-%d")
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM movies WHERE status = 'active'") as cur:
            movies = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM series WHERE status = 'active'") as cur:
            series = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as cur:
            premiums = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (f"{today}%",)
        ) as cur:
            new_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM watch_history") as cur:
            total_views = (await cur.fetchone())[0]

    text = (
        f"📊 <b>Bot Statistikasi</b>\n\n"
        f"👥 Umumiy a'zolar: <b>{users} ta</b>\n"
        f"📈 Bugun qo'shilganlar: <b>{new_users} ta</b>\n"
        f"⭐ Premium a'zolar: <b>{premiums} ta</b>\n\n"
        f"🎬 Aktiv kinolar: <b>{movies} ta</b>\n"
        f"📺 Aktiv seriallar: <b>{series} ta</b>\n"
        f"👁 Jami ko'rishlar: <b>{total_views} ta</b>\n"
    )
    await message.answer(text, parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════
#  F. BROADCAST
# BUG #1 FIX: ReplyKeyboardMarkup va KeyboardButton endi import qilingan
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "📢 Broadcast")
async def admin_broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(BroadcastState.waiting)
    await message.answer(
        "📢 Reklama xabarini yuboring (text, rasm, video, va h.k.).\n"
        "Xabar qanday bo'lsa shundayligicha barchaga yuboriladi.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
            resize_keyboard=True
        )
    )

@router.message(BroadcastState.waiting)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
        return

    await state.clear()
    await message.answer("🚀 Tarqatish boshlandi...", reply_markup=admin_menu())

    async with get_db() as db:
        async with db.execute("SELECT tg_id FROM users WHERE is_banned = 0") as cur:
            rows = await cur.fetchall()

    success, failed = 0, 0
    for r in rows:
        try:
            await message.copy_to(r[0])
            success += 1
            await asyncio.sleep(0.05)   # Flood control
        except Exception:
            failed += 1

    await message.answer(
        f"🏁 <b>Tarqatish yakunlandi:</b>\n\n"
        f"✅ Muvaffaqiyatli: {success}\n"
        f"❌ Muammoli: {failed}",
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════════════════════
#  G. EKSPORT CSV
# BUG #3 FIX: admin tekshiruvi qo'shildi (oldin yo'q edi)
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "📥 Eksport CSV")
async def admin_export(message: Message):
    if not is_admin(message.from_user.id):   # BUG #3 FIX
        return
    async with get_db() as db:
        async with db.execute("SELECT * FROM users") as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(cols)
    writer.writerows(rows)

    f = BufferedInputFile(output.getvalue().encode("utf-8"), filename="users.csv")
    await message.answer_document(f, caption="👥 Barcha foydalanuvchilar ro'yxati (CSV)")


# ══════════════════════════════════════════════════════════════════════
#  H. KINO SO'ROVLAR
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "📨 Kino so'rovlar")
async def admin_requests(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with get_db() as db:
        async with db.execute(
            "SELECT r.id, r.text, u.full_name, r.user_id "
            "FROM movie_requests r "
            "JOIN users u ON r.user_id = u.tg_id "
            "WHERE r.status = 'pending' "
            "ORDER BY r.id DESC LIMIT 10"
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await message.answer("Yangi so'rovlar yo'q.")
        return

    for r in rows:
        text = (
            f"📨 <b>Kino So'rovi:</b>\n\n"
            f"👤 Kimdan: {r[2]} (<code>{r[3]}</code>)\n"
            f"🍿 So'rov: {r[1]}\n"
        )
        await message.answer(text, reply_markup=requests_kb(r[0]), parse_mode="HTML")

@router.callback_query(F.data.startswith("req_accept_"))
async def req_accept(call: CallbackQuery):
    req_id = int(call.data.split("_")[2])
    async with get_db() as db:
        async with db.execute(
            "SELECT user_id FROM movie_requests WHERE id = ?", (req_id,)
        ) as cur:
            row = await cur.fetchone()
        await db.execute(
            "UPDATE movie_requests SET status = 'accepted' WHERE id = ?", (req_id,)
        )
        await db.commit()

    if row:
        try:
            await call.bot.send_message(row[0], "✅ So'rovingiz qabul qilindi! Tez orada qo'shamiz.")
        except Exception:
            pass

    await call.message.edit_text("✅ So'rov qabul qilindi!")
    await call.answer()

@router.callback_query(F.data.startswith("req_reject_"))
async def req_reject(call: CallbackQuery):
    req_id = int(call.data.split("_")[2])
    async with get_db() as db:
        async with db.execute(
            "SELECT user_id FROM movie_requests WHERE id = ?", (req_id,)
        ) as cur:
            row = await cur.fetchone()
        await db.execute(
            "UPDATE movie_requests SET status = 'rejected' WHERE id = ?", (req_id,)
        )
        await db.commit()

    if row:
        try:
            await call.bot.send_message(row[0], "❌ Kechirasiz, so'rovingiz rad etildi.")
        except Exception:
            pass

    await call.message.edit_text("❌ So'rov rad etildi!")
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  👥 FOYDALANUVCHILAR BOSHQARUVI
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "👥 Foydalanuvchilar", F.from_user.id.in_(ADMINS))
async def admin_users_list(message: Message):
    async with get_db() as db:
        async with db.execute(
            "SELECT tg_id, full_name, username, is_premium, is_banned FROM users ORDER BY id DESC LIMIT 20"
        ) as cur:
            rows = await cur.fetchall()
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as cur:
            premium_count = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1") as cur:
            banned_count = (await cur.fetchone())[0]

    if not rows:
        await message.answer("Foydalanuvchilar yo'q.")
        return

    lines = [
        f"👥 <b>Foydalanuvchilar</b>\n"
        f"📊 Jami: {total} | ⭐ Premium: {premium_count} | 🚫 Ban: {banned_count}\n\n"
        "Oxirgi 20 ta:\n"
    ]
    for tg_id, name, username, is_prem, is_ban in rows:
        prem = "⭐" if is_prem else "  "
        ban  = "🚫" if is_ban  else "  "
        uname = f"@{username}" if username else "—"
        lines.append(f"{prem}{ban} <code>{tg_id}</code> — {name} ({uname})")

    lines.append("\n\nFoydalanuvchi ID sini /user_123456 formatda yuboring.")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text.startswith("/user_"), F.from_user.id.in_(ADMINS))
async def admin_user_detail(message: Message):
    try:
        user_id = int(message.text.split("_")[1])
    except (IndexError, ValueError):
        await message.answer("❌ Format: /user_123456")
        return

    async with get_db() as db:
        async with db.execute("SELECT * FROM users WHERE tg_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                await message.answer("❌ Foydalanuvchi topilmadi.")
                return
            cols = [d[0] for d in cur.description]
            u = dict(zip(cols, row))

    prem_label = "Ha" if u["is_premium"] else "Yoq"
    ban_label  = "Ha" if u["is_banned"]  else "Yoq"
    text = (
        f"👤 <b>Foydalanuvchi</b>\n\n"
        f"🆔 ID: <code>{u['tg_id']}</code>\n"
        f"👨 Ism: {u['full_name']}\n"
        f"@username: {u.get('username') or '—'}\n"
        f"🌐 Til: {u['lang']}\n"
        f"⭐ Premium: {prem_label}\n"
        f"📅 Premium muddat: {u.get('premium_until') or '—'}\n"
        f"💰 Balans: {u['balance']} ball\n"
        f"🚫 Ban: {ban_label}\n"
        f"📅 Qo'shildi: {u.get('created_at', '?')[:10]}"
    )
    await message.answer(
        text,
        reply_markup=user_manage_kb(u['tg_id'], u['is_banned']),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("ban_"), F.from_user.id.in_(ADMINS))
async def ban_user(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])
    async with get_db() as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE tg_id = ?", (user_id,))
        await db.commit()
    await call.answer("🚫 Foydalanuvchi ban qilindi!", show_alert=True)
    try:
        await call.message.edit_reply_markup(reply_markup=user_manage_kb(user_id, 1))
    except Exception:
        pass


@router.callback_query(F.data.startswith("unban_"), F.from_user.id.in_(ADMINS))
async def unban_user(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])
    async with get_db() as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE tg_id = ?", (user_id,))
        await db.commit()
    await call.answer("✅ Ban olib tashlandi!", show_alert=True)
    try:
        await call.message.edit_reply_markup(reply_markup=user_manage_kb(user_id, 0))
    except Exception:
        pass


@router.callback_query(F.data.startswith("give_premium_"), F.from_user.id.in_(ADMINS))
async def give_premium_cb(call: CallbackQuery, state: FSMContext):
    user_id = int(call.data.split("_")[2])
    await state.update_data(target=user_id)
    await state.set_state(GivePremiumState.waiting)
    await call.message.answer(f"⭐ Necha kun premium berish? (<code>{user_id}</code>)", parse_mode="HTML")
    await call.answer()


@router.message(GivePremiumState.waiting, F.from_user.id.in_(ADMINS))
async def give_premium_days(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data.get("target")
    await state.clear()

    if not message.text or not message.text.strip().isdigit():
        await message.answer("❌ Kunlar sonini raqam bilan yuboring!")
        return

    days = int(message.text.strip())
    from bot.handlers.premium import activate_premium
    new_until = await activate_premium(target, days)

    await message.answer(f"✅ {target} ga {days} kun premium berildi. Muddat: {new_until}")
    try:
        await message.bot.send_message(
            target,
            f"🎉 Sizga <b>{days} kunlik Premium</b> berildi!\n📅 Muddat: {new_until}",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("msg_user_"), F.from_user.id.in_(ADMINS))
async def msg_user_cb(call: CallbackQuery, state: FSMContext):
    user_id = int(call.data.split("_")[2])
    await state.update_data(target=user_id)
    await state.set_state(MsgUserState.waiting)
    await call.message.answer(f"💬 Xabar yozing (<code>{user_id}</code> ga yuboriladi):", parse_mode="HTML")
    await call.answer()


@router.message(MsgUserState.waiting, F.from_user.id.in_(ADMINS))
async def msg_user_send(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data.get("target")
    await state.clear()
    try:
        await message.bot.send_message(target, message.text or "")
        await message.answer("✅ Xabar yuborildi!")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")


# ══════════════════════════════════════════════════════════════════════
#  🔧 SOZLAMALAR — Karta raqami va obuna narxlari
# ══════════════════════════════════════════════════════════════════════
class SettingsState(StatesGroup):
    waiting_card_number = State()
    waiting_card_owner  = State()
    waiting_tariff_edit = State()
    tariff_id           = State()


def _settings_kb():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Karta raqami",  callback_data="set_card_number")],
        [InlineKeyboardButton(text="👤 Karta egasi",   callback_data="set_card_owner")],
        [InlineKeyboardButton(text="💰 Tarif narxlari", callback_data="set_tariffs")],
        [InlineKeyboardButton(text="❌ Yopish",        callback_data="close_settings")],
    ])


@router.message(F.text == "🔧 Sozlamalar", F.from_user.id.in_(ADMINS))
async def admin_settings(message: Message):
    async with get_db() as db:
        async with db.execute("SELECT key, value FROM settings WHERE key IN ('card_number','card_owner')") as cur:
            rows = await cur.fetchall()

    s = dict(rows)
    card_num   = s.get("card_number", "—")
    card_owner = s.get("card_owner",  "—")

    text = (
        f"🔧 <b>Sozlamalar</b>\n\n"
        f"💳 Karta raqami: <code>{card_num}</code>\n"
        f"👤 Karta egasi: <b>{card_owner}</b>\n\n"
        f"Tahrirlash uchun tugmani bosing:"
    )
    await message.answer(text, reply_markup=_settings_kb(), parse_mode="HTML")


@router.callback_query(F.data == "set_card_number", F.from_user.id.in_(ADMINS))
async def set_card_number_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("💳 Yangi karta raqamini yuboring:\n\nMisol: <code>8600 1234 5678 9012</code>", parse_mode="HTML")
    await state.set_state(SettingsState.waiting_card_number)
    await call.answer()


@router.message(SettingsState.waiting_card_number, F.from_user.id.in_(ADMINS))
async def set_card_number_save(message: Message, state: FSMContext):
    await state.clear()
    val = (message.text or "").strip()
    if not val:
        await message.answer("❌ Bo'sh bo'lishi mumkin emas!")
        return
    async with get_db() as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('card_number', ?)", (val,))
        await db.commit()
    await message.answer(f"✅ Karta raqami saqlandi:\n<code>{val}</code>", parse_mode="HTML",
                         reply_markup=_settings_kb())


@router.callback_query(F.data == "set_card_owner", F.from_user.id.in_(ADMINS))
async def set_card_owner_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("👤 Karta egasining ismini yuboring:\n\nMisol: Abdullayev Sardor")
    await state.set_state(SettingsState.waiting_card_owner)
    await call.answer()


@router.message(SettingsState.waiting_card_owner, F.from_user.id.in_(ADMINS))
async def set_card_owner_save(message: Message, state: FSMContext):
    await state.clear()
    val = (message.text or "").strip()
    if not val:
        await message.answer("❌ Bo'sh bo'lishi mumkin emas!")
        return
    async with get_db() as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('card_owner', ?)", (val,))
        await db.commit()
    await message.answer(f"✅ Karta egasi saqlandi: <b>{val}</b>", parse_mode="HTML",
                         reply_markup=_settings_kb())


@router.callback_query(F.data == "set_tariffs", F.from_user.id.in_(ADMINS))
async def set_tariffs_list(call: CallbackQuery):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    async with get_db() as db:
        async with db.execute("SELECT id, name, duration, price FROM tariffs ORDER BY price") as cur:
            rows = await cur.fetchall()

    if not rows:
        await call.answer("Tarifflar yo'q!", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"⭐ {name} — {price:,} so'm ({duration} kun)",
            callback_data=f"edit_tariff_{tid}"
        )]
        for tid, name, duration, price in rows
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="close_settings")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_text("💰 <b>Tarif narxlari</b>\n\nTahrirlamoqchi bo'lgan tarifni tanlang:", reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("edit_tariff_"), F.from_user.id.in_(ADMINS))
async def edit_tariff_start(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split("_")[2])
    async with get_db() as db:
        async with db.execute("SELECT id, name, duration, price FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()

    if not row:
        await call.answer("❌ Tarif topilmadi!", show_alert=True)
        return

    tid, name, duration, price = row
    await state.update_data(tariff_id=tid)
    await state.set_state(SettingsState.waiting_tariff_edit)
    await call.message.answer(
        f"⭐ <b>{name}</b>\n"
        f"📅 Muddat: {duration} kun\n"
        f"💰 Narx: {price:,} so'm\n\n"
        f"Yangi narxni yuboring (faqat so'mda):\nMisol: 29900",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(SettingsState.waiting_tariff_edit, F.from_user.id.in_(ADMINS))
async def edit_tariff_save(message: Message, state: FSMContext):
    data = await state.get_data()
    tariff_id = data.get("tariff_id")
    await state.clear()

    val = (message.text or "").strip().replace(" ", "").replace(",", "")
    if not val.isdigit():
        await message.answer("❌ Faqat raqam kiriting (so'mda)!\nMisol: 29900")
        return

    price = int(val)
    async with get_db() as db:
        await db.execute("UPDATE tariffs SET price = ? WHERE id = ?", (price, tariff_id))
        await db.commit()

    await message.answer(f"✅ Tarif narxi yangilandi: <b>{price:,} so'm</b>", parse_mode="HTML",
                         reply_markup=_settings_kb())


@router.callback_query(F.data == "close_settings", F.from_user.id.in_(ADMINS))
async def close_settings(call: CallbackQuery):
    await call.message.edit_text("🔧 Sozlamalar yopildi.")
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  🏠 BOSH MENYU (admin paneldan qaytish)
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "🏠 Bosh menyu", F.from_user.id.in_(ADMINS))
async def admin_back_to_main(message: Message):
    async with get_db() as db:
        async with db.execute("SELECT lang FROM users WHERE tg_id = ?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
    lang = row[0] if row else "uz"
    await message.answer(
        "🏠 Bosh menyuga qaytildi.",
        reply_markup=main_menu(lang)
    )
