import csv
import io
import random
import asyncio
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
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

router = Router()

# ── Admin filter ───────────────────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

# ── FSM STATES ──────────────────────────────────────────
class FilmStates(StatesGroup):
    waiting_video = State()
    waiting_titles = State()
    waiting_country_year = State()
    waiting_genres = State()
    waiting_poster = State()
    waiting_description = State()
    waiting_premium = State()

class SeriesStates(StatesGroup):
    waiting_titles = State()
    waiting_country_year = State()
    waiting_genres = State()
    waiting_poster = State()
    waiting_description = State()
    waiting_premium = State()
    waiting_episodes = State()

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


# ── UTILS: KOD GENERATORI ─────────────────────────────────
async def generate_unique_code(db) -> str:
    """Kino yoki serial uchun unikal 3-4 xonali raqamli kod yaratadi"""
    while True:
        code = str(random.randint(100, 9999))
        
        # Movies dan tekshirish
        async with db.execute("SELECT id FROM movies WHERE code = ?", (code,)) as cur:
            movie = await cur.fetchone()
            
        # Series dan tekshirish
        async with db.execute("SELECT id FROM series WHERE code = ?", (code,)) as cur:
            series = await cur.fetchone()
            
        if not movie and not series:
            return code


# ── ESKI ADMIN MENU VA ASOSIY BUYRUQLAR ────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Admin Panel</b>", reply_markup=admin_menu(), parse_mode="HTML")


# ── FILM VA SERIAL QO'SHISH BOSHLANISHI ────────────────────
@router.message(F.text == "🎬 Kino qo'shish", F.from_user.id.in_(ADMINS))
async def start_add_content(message: Message):
    await message.answer("🎬 **Nima qo'shmoqchisiz?** Tanlang:", reply_markup=custom_admin_kb.content_type_kb())


# ── A. FILM QO'SHISH FLOWI (FSM) ──────────────────────────
@router.callback_query(F.data == "add_type_film", F.from_user.id.in_(ADMINS))
async def add_film_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(FilmStates.waiting_video)
    await call.message.edit_text("🎥 **Film videosini yuboring:**", reply_markup=custom_admin_kb.cancel_fsm_kb())
    await call.answer()

@router.message(FilmStates.waiting_video, F.video)
async def process_film_video(message: Message, state: FSMContext):
    await state.update_data(file_id=message.video.file_id)
    await state.set_state(FilmStates.waiting_titles)
    await message.answer("📝 **Film nomlarini yuboring:**\n1-qator: O'zbekcha nomi\n2-qator: Ruscha nomi", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(FilmStates.waiting_titles, F.text)
async def process_film_titles(message: Message, state: FSMContext):
    lines = message.text.splitlines()
    if len(lines) < 2:
        await message.answer("❌ Iltimos, nomlarni 2 qatorda yuboring (O'zbekcha va Ruscha)!")
        return
    await state.update_data(title_uz=lines[0].strip(), title_ru=lines[1].strip())
    await state.set_state(FilmStates.waiting_country_year)
    await message.answer("🌍 **Mamlakat** va 📅 **Yilni** 2 qatorda yuboring:\n\nMisol:\nFransiya\n2012", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(FilmStates.waiting_country_year, F.text)
async def process_film_country_year(message: Message, state: FSMContext):
    lines = message.text.splitlines()
    if len(lines) < 2 or not lines[1].strip().isdigit():
        await message.answer("❌ Format xato! Mamlakat va Yilni to'g'ri kiriting.")
        return
    await state.update_data(country=lines[0].strip(), year=int(lines[1].strip()))
    await state.set_state(FilmStates.waiting_genres)
    await message.answer("🎭 **Kamida 2 ta janr yuboring** (Har biri yangi qatorda):", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(FilmStates.waiting_genres, F.text)
async def process_film_genres(message: Message, state: FSMContext):
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    if len(lines) < 2:
        await message.answer("❌ Kamida 2 ta janr kiriting!")
        return
    await state.update_data(genres=", ".join(lines))
    await state.set_state(FilmStates.waiting_poster)
    await message.answer("🖼 **Poster yuboring (Rasm):**", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(FilmStates.waiting_poster, F.photo)
async def process_film_poster(message: Message, state: FSMContext):
    await state.update_data(poster_file_id=message.photo[-1].file_id)
    await state.set_state(FilmStates.waiting_description)
    await message.answer("✍️ **Film uchun qisqa qiziqarli tavsif yozing:**", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(FilmStates.waiting_description, F.text)
async def process_film_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(FilmStates.waiting_premium)
    await message.answer("⭐ **Ushbu film Premium foydalanuvchilar uchun bo'lsinmi?**", reply_markup=custom_admin_kb.is_premium_kb())

@router.callback_query(FilmStates.waiting_premium, F.data.startswith("premium_"))
async def save_film_final(call: CallbackQuery, state: FSMContext, bot: Bot):
    is_premium = 1 if call.data == "premium_yes" else 0
    data = await state.get_data()
    await state.clear()
    
    # Ma'lumotlar to'liqligini qattiq nazorat qilish
    title_uz = data.get('title_uz', '').strip()
    if not title_uz:
        await call.message.edit_text("❌ Xato: O'zbekcha nom aniqlanmadi, jarayon bekor qilindi.")
        return
        
    async with get_db() as db:
        code = await generate_unique_code(db)
        
        # EXECUTED FIX: movies.title NOT NULL cheklovini buzmaslik uchun title_uz ni ham title, ham title_uz ustunlariga yozamiz!
        await db.execute("""
            INSERT INTO movies (code, title, title_uz, title_ru, country, year, genres, description, file_id, poster_file_id, is_premium, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (code, title_uz, title_uz, data['title_ru'], data['country'], data['year'], data['genres'], data['description'], data['file_id'], data['poster_file_id'], is_premium))
        await db.commit()

    # Private Kanalga Backup (Fayl yo'qolmasligi uchun)
    try:
        await bot.send_video(
            chat_id=CHANNEL_PRIVATE,
            video=data['file_id'],
            caption=f"📦 BACKUP | FILM\n🔑 KOD: {code}\n🎬 NOM (UZ): {title_uz}\n🌐 NOM (RU): {data['title_ru']}"
        )
    except Exception as e:
        print(f"Private Backup error: {e}")

    # Public Kanalga Reklama Posti
    bot_user = await bot.get_me()
    premium_tag = "⭐ PREMIUM" if is_premium else "🔓 TEKIN"
    
    pub_caption = (
        f"🎬 <b>{title_uz.upper()}</b>\n"
        f"🧚‍♀️ Mashhur multfilm/kino endi botimizda!\n\n"
        f"🌍 {data['country']}\n"
        f"📅 {data['year']}\n"
        f"🎭 {data['genres']}\n"
        f"Status: {premium_tag}\n\n"
        f"🍿 {data['description']}\n\n"
        f"👇 Tomosha qilish uchun tugmani bosing"
    )
    
    watch_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 TOMOSHA QILISH", url=f"https://t.me/{bot_user.username}?start=movie_{code}")]
    ])
    
    try:
        await bot.send_photo(
            chat_id=CHANNEL_PUBLIC,
            photo=data['poster_file_id'],
            caption=pub_caption,
            reply_markup=watch_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Public post error: {e}")

    await call.message.edit_text(f"✅ **Film muvaffaqiyatli saqlandi!**\n🔑 Avtomatik kod: ` {code} `", parse_mode="Markdown")
    await call.answer()


# ── B. SERIAL QO'SHISH FLOWI (FSM) ────────────────────────
@router.callback_query(F.data == "add_type_series", F.from_user.id.in_(ADMINS))
async def add_series_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(SeriesStates.waiting_titles)
    await call.message.edit_text("📝 **Serial nomlarini yuboring:**\n1-qator: O'zbekcha nomi\n2-qator: Ruscha nomi", reply_markup=custom_admin_kb.cancel_fsm_kb())
    await call.answer()

@router.message(SeriesStates.waiting_titles, F.text)
async def process_series_titles(message: Message, state: FSMContext):
    lines = message.text.splitlines()
    if len(lines) < 2:
        await message.answer("❌ Iltimos, serial nomlarini 2 qatorda yuboring!")
        return
    await state.update_data(title_uz=lines[0].strip(), title_ru=lines[1].strip())
    await state.set_state(SeriesStates.waiting_country_year)
    await message.answer("🌍 **Mamlakat** va 📅 **Yilni** 2 qatorda yuboring:\n\nMisol:\nKoreya\n2023", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(SeriesStates.waiting_country_year, F.text)
async def process_series_country_year(message: Message, state: FSMContext):
    lines = message.text.splitlines()
    if len(lines) < 2 or not lines[1].strip().isdigit():
        await message.answer("❌ Noto'g'ri format! Mamlakat va Yilni kiriting.")
        return
    await state.update_data(country=lines[0].strip(), year=int(lines[1].strip()))
    await state.set_state(SeriesStates.waiting_genres)
    await message.answer("🎭 **Kamida 2 ta janr yuboring** (Har biri yangi qatorda):", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(SeriesStates.waiting_genres, F.text)
async def process_series_genres(message: Message, state: FSMContext):
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    if len(lines) < 2:
        await message.answer("❌ Kamida 2 ta janr kiritishingiz shart!")
        return
    await state.update_data(genres=", ".join(lines))
    await state.set_state(SeriesStates.waiting_poster)
    await message.answer("🖼 **Poster yuboring (Rasm):**", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(SeriesStates.waiting_poster, F.photo)
async def process_series_poster(message: Message, state: FSMContext):
    await state.update_data(poster_file_id=message.photo[-1].file_id)
    await state.set_state(SeriesStates.waiting_description)
    await message.answer("✍️ **Serial uchun qisqa qiziqarli tavsif yozing:**", reply_markup=custom_admin_kb.cancel_fsm_kb())

@router.message(SeriesStates.waiting_description, F.text)
async def process_series_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(SeriesStates.waiting_premium)
    await message.answer("⭐ **Ushbu serial Premium foydalanuvchilar uchun bo'lsinmi?**", reply_markup=custom_admin_kb.is_premium_kb())

@router.callback_query(SeriesStates.waiting_premium, F.data.startswith("premium_"))
async def save_series_main_info(call: CallbackQuery, state: FSMContext):
    is_premium = 1 if call.data == "premium_yes" else 0
    await state.update_data(is_premium=is_premium, current_season=1)
    data = await state.get_data()
    
    async with get_db() as db:
        code = await generate_unique_code(db)
        await state.update_data(code=code)
        
        # 1. Series jadvaliga saqlash
        async with db.execute("""
            INSERT INTO series (code, title_uz, title_ru, country, year, genres, poster_file_id, description, is_premium, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (code, data['title_uz'], data['title_ru'], data['country'], data['year'], data['genres'], data['poster_file_id'], data['description'], is_premium)) as cur:
            series_id = cur.lastrowid
            
        # 2. Seasons jadvaliga default 1-faslni ochish
        await db.execute("INSERT INTO seasons (series_id, season_number) VALUES (?, 1)", (series_id,))
        await db.commit()
        await state.update_data(series_id=series_id)

    await state.set_state(SeriesStates.waiting_episodes)
    await call.message.edit_text(
        f"✅ **Serial bazasi yaratildi! (Kod: {code})**\n\n"
        f"📀 **Hozirgi joylashuv: 1-Fasl**\n"
        f"📺 Endi qismlarni yuboring. Video captioniga (izohiga) faqat qism raqamini yozing. (Masalan: `1`)\n\n"
        f"Tugmalardan foydalanib keyingi faslga o'tishingiz yoki jarayonni yakunlashingiz mumkin.",
        reply_markup=custom_admin_kb.series_control_kb()
    )
    await call.answer()

@router.message(SeriesStates.waiting_episodes, F.video)
async def process_series_episode_file(message: Message, state: FSMContext, bot: Bot):
    caption = message.caption or ""
    if not caption.strip().isdigit():
        await message.answer("❌ Xato! Videoning izoh (caption) qismiga faqat qism raqamini yozing (Masalan: 1)")
        return
        
    ep_num = int(caption.strip())
    data = await state.get_data()
    
    async with get_db() as db:
        try:
            await db.execute("""
                INSERT INTO episodes (series_id, season_number, episode_number, file_id)
                VALUES (?, ?, ?, ?)
            """, (data['series_id'], data['current_season'], ep_num, message.video.file_id))
            await db.commit()
        except Exception:
            await message.answer(f"⚠️ {data['current_season']}-fasl {ep_num}-qism allaqachon yuklangan yoki xatolik yuz berdi!")
            return

    # Private Backup
    try:
        await bot.send_video(
            chat_id=CHANNEL_PRIVATE,
            video=message.video.file_id,
            caption=f"📦 BACKUP | SERIAL\n🔑 KOD: {data['code']}\n📺 {data['title_uz']}\n📀 Fasl: {data['current_season']} | Qism: {ep_num}"
        )
    except Exception:
        pass

    await message.answer(f"✅ {data['current_season']}-fasl {ep_num}-qism saqlandi!", reply_markup=custom_admin_kb.series_control_kb())

@router.callback_query(SeriesStates.waiting_episodes, F.data == "series_next_season")
async def process_next_season_switch(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    next_season = data['current_season'] + 1
    
    async with get_db() as db:
        await db.execute("INSERT OR IGNORE INTO seasons (series_id, season_number) VALUES (?, ?)", (data['series_id'], next_season))
        await db.commit()
        
    await state.update_data(current_season=next_season)
    await call.message.edit_text(
        f"📀 **Tizim {next_season}-faslga o'tdi.**\n\n"
        f"📺 Endi {next_season}-faslning videolarini yuklashingiz mumkin. Captionga faqat qism raqamini yozing.",
        reply_markup=custom_admin_kb.series_control_kb()
    )
    await call.answer()

@router.callback_query(SeriesStates.waiting_episodes, F.data == "series_finish")
async def process_series_finish_all(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    
    # Public kanalga reklama post chiqarish
    bot_user = await bot.get_me()
    premium_tag = "⭐ PREMIUM" if data['is_premium'] else "🔓 TEKIN"
    
    pub_caption = (
        f"📺 <b>{data['title_uz'].upper()} (Yangi Serial)</b>\n"
        f"🎭 Janr: {data['genres']}\n"
        f"🌍 Davlat: {data['country']} | 📅 Yil: {data['year']}\n"
        f"Status: {premium_tag}\n\n"
        f"🍿 {data['description']}\n\n"
        f"👇 Barcha fasl va qismlarni ko'rish uchun pastdagi tugmani bosing"
    )
    
    watch_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 SERIALNI KO'RISH", url=f"https://t.me/{bot_user.username}?start=series_{data['code']}")]
    ])
    
    try:
        await bot.send_photo(
            chat_id=CHANNEL_PUBLIC,
            photo=data['poster_file_id'],
            caption=pub_caption,
            reply_markup=watch_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Public series post error: {e}")
        
    await call.message.edit_text(f"🚀 **Serial to'liq yuklandi va e'lon qilindi!**\n🔑 Avtomatik kod: ` {data['code']} `", parse_mode="Markdown")
    await call.answer()


# ── FSM BEKOR QILISH ──────────────────────────────────────
@router.callback_query(F.data == "cancel_admin_fsm")
async def cancel_fsm_process(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Jarayon bekor qilindi.")
    await call.answer()


# ── C. TAHRIRLASH, ARXIV VA SOFT-DELETE ───────────────────
@router.message(F.text == "✏️ Kontentni tahrirlash", F.from_user.id.in_(ADMINS))
async def admin_edit_start_process(message: Message, state: FSMContext):
    await state.set_state(EditContentState.waiting_code)
    await message.answer("🔍 **Tahrirlamoqchi bo'lgan kontent (Film yoki Serial) kodini yuboring:**")

@router.message(EditContentState.waiting_code, F.text)
async def process_find_content_to_edit(message: Message, state: FSMContext):
    code = message.text.strip()
    await state.clear()
    
    async with get_db() as db:
        # Filmlardan qidirish
        async with db.execute("SELECT id, title_uz, status FROM movies WHERE code = ?", (code,)) as cur:
            movie = await cur.fetchone()
        # Seriallardan qidirish
        async with db.execute("SELECT id, title_uz, status FROM series WHERE code = ?", (code,)) as cur:
            series = await cur.fetchone()

    if not movie and not series:
        await message.answer("❌ Ushbu kod bilan hech qanday kino yoki serial topilmadi!")
        return

    is_movie = True if movie else False
    c_id = movie[0] if is_movie else series[0]
    title = movie[1] if is_movie else series[1]
    status = movie[2] if is_movie else series[2]
    c_type = "movie" if is_movie else "series"

    archive_txt = "📥 Arxivga olish" if status == "active" else "📤 Arxivdan chiqarish"
    archive_cb = f"status_archive_{c_type}_{c_id}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=archive_txt, callback_data=archive_cb),
            InlineKeyboardButton(text="🗑 Soft-Delete (O'chirish)", callback_data=f"status_delete_{c_type}_{c_id}")
        ],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_admin_panel")]
    ])

    await message.answer(
        f"🎬 **Kontent topildi:**\n\n"
        f"📌 Nomi: **{title}**\n"
        f"🗂 Turi: `{c_type.upper()}`\n"
        f"🚦 Status: `{status.upper()}`\n\n"
        f"Kerakli boshqaruvni tanlang:", 
        reply_markup=kb, 
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("status_"))
async def process_content_status_change(call: CallbackQuery):
    parts = call.data.split("_")
    action = parts[1]
    c_type = parts[2]
    c_id = int(parts[3])
    
    table = "movies" if c_type == "movie" else "series"
    
    async with get_db() as db:
        if action == "delete":
            await db.execute(f"UPDATE {table} SET status = 'deleted' WHERE id = ?", (c_id,))
            msg = "🗑 Kontent muvaffaqiyatli 'deleted' holatiga o'tkazildi (soft-delete)!"
        elif action == "archive":
            async with db.execute(f"SELECT status FROM {table} WHERE id = ?", (c_id,)) as cur:
                current_status = (await cur.fetchone())[0]
            new_status = "archived" if current_status == "active" else "active"
            await db.execute(f"UPDATE {table} SET status = ? WHERE id = ?", (new_status, c_id))
            msg = f"🚀 Kontent statusi muvaffaqiyatli '{new_status}' ga yangilandi!"
            
        await db.commit()
        
    await call.message.edit_text(f"✅ {msg}")
    await call.answer()

@router.callback_query(F.data == "close_admin_panel")
async def cb_close_admin_panel_edit(call: CallbackQuery):
    await call.message.delete()
    await call.answer()


# ── ESKIDAN MAVJUD BO'LGAN BARCHA ADMIN OPERATSIYALARI ──────
@router.message(F.text == "📋 Kinolar ro'yxati")
async def admin_movies(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with get_db() as db:
        async with db.execute(
            "SELECT id, code, title FROM movies ORDER BY id DESC LIMIT 20"
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await message.answer("Kinolar yo'q.")
        return

    text = "🎬 <b>Oxirgi 20 ta kino:</b>\n\n"
    for r in rows:
        text += f"▪️ <code>{r[1]}</code> — {r[2]} /admin_movie_{r[0]}\n"
    await message.answer(text, parse_mode="HTML")

@router.message(F.text.startswith("/admin_movie_"))
async def admin_movie_view(message: Message):
    if not is_admin(message.from_user.id):
        return
    m_id = int(message.text.split("_")[2])
    async with get_db() as db:
        async with db.execute("SELECT * FROM movies WHERE id = ?", (m_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        await message.answer("Kino topilmadi.")
        return

    cols = [d[0] for d in (await get_db().execute("PRAGMA table_info(movies)")).fetchall()]
    m = dict(zip(cols, row))

    text = (
        f"🎬 <b>{m.get('title_uz') or m.get('title')}</b>\n\n"
        f"🔑 Kod: <code>{m['code']}</code>\n"
        f"🎭 Janr: {m.get('genre', '')}\n"
        f"📅 Yil: {m.get('year', '')}\n"
        f"🌍 Mamlakat: {m.get('country', '')}\n"
        f"👁 Ko'rishlar: {m.get('views', 0)}\n"
        f"⭐ Reyting: {m.get('rating', 0)}\n"
        f"🔒 Premium: {'Ha' if m.get('is_premium') else 'Yoq'}\n"
        f"🚦 Status: {m.get('status', 'active')}\n"
    )
    await message.answer(text, reply_markup=movie_manage_kb(m_id), parse_mode="HTML")

@router.message(F.text == "📊 Statistika")
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM movies") as cur:
            movies = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM series") as cur:
            series = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as cur:
            premiums = (await cur.fetchone())[0]

        # Bugun qo'shilganlar
        today = datetime.now().strftime("%Y-%m-%d")
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (f"{today}%",)
        ) as cur:
            new_users = (await cur.fetchone())[0]

    text = (
        f"📊 <b>Bot Statistikasi</b>\n\n"
        f"👥 Umumiy a'zolar: <b>{users} ta</b>\n"
        f"📈 Bugun qo'shilganlar: <b>{new_users} ta</b>\n"
        f"🎬 Umumiy kinolar: <b>{movies} ta</b>\n"
        f"📺 Umumiy seriallar: <b>{series} ta</b>\n"
        f"⭐ Premium a'zolar: <b>{premiums} ta</b>\n"
    )
    await message.answer(text, parse_mode="HTML")

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
        async with db.execute("SELECT tg_id FROM users") as cur:
            rows = await cur.fetchall()

    success, failed = 0, 0
    for r in rows:
        try:
            await message.copy_to(r[0])
            success += 1
            await asyncio.sleep(0.05)  # Flood control
        except Exception:
            failed += 1

    await message.answer(
        f"🏁 <b>Tarqatish yakunlandi:</b>\n\n"
        f"✅ Muvaffaqiyatli: {success}\n"
        f"❌ Muammoli: {failed}",
        parse_mode="HTML"
    )

@router.message(F.text == "📥 Eksport CSV")
async def admin_export(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with get_db() as db:
        async with db.execute("SELECT * FROM users") as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(cols)
    writer.writerows(rows)

    f = BufferedInputFile(output.getvalue().encode(), filename="users.csv")
    await message.answer_document(f, caption="👥 Barcha foydalanuvchilar ro'yxati (CSV)")

@router.message(F.text == "📨 Kino so'rovlar")
async def admin_requests(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with get_db() as db:
        async with db.execute(
            "SELECT r.id, r.text, u.full_name, r.user_id FROM movie_requests r "
            "JOIN users u ON r.user_id = u.tg_id WHERE r.status = 'pending' LIMIT 10"
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
        await db.execute(
            "UPDATE movie_requests SET status = 'accepted' WHERE id = ?", (req_id,)
        )
        async with db.execute(
            "SELECT user_id FROM movie_requests WHERE id = ?", (req_id,)
        ) as cur:
            row = await cur.fetchone()
        await db.commit()

    if row:
        try:
            await call.bot.send_message(
                row[0], "✅ So'rovingiz qabul qilindi! Tez orada qo'shamiz."
            )
        except Exception:
            pass

    await call.message.edit_text("✅ So'rov qabul qilindi!")

@router.callback_query(F.data.startswith("req_reject_"))
async def req_reject(call: CallbackQuery):
    req_id = int(call.data.split("_")[2])
    async with get_db() as db:
        await db.execute(
            "UPDATE movie_requests SET status = 'rejected' WHERE id = ?", (req_id,)
        )
        async with db.execute(
            "SELECT user_id FROM movie_requests WHERE id = ?", (req_id,)
        ) as cur:
            row = await cur.fetchone()
        await db.commit()

    if row:
        try:
            await call.bot.send_message(
                row[0], "❌ Kechirasiz, so'rovingiz rad etildi."
            )
        except Exception:
            pass

    await call.message.edit_text("❌ So'rov rad etildi!")
