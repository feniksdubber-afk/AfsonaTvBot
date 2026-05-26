"""
admin_content_add.py
────────────────────
Film va Serial qo'shish FSM flowi.

[SPLIT] admin.py (1292 qator) dan ajratildi:
  - admin_content_add.py  — film/serial qo'shish (bu fayl)
  - admin_content_list.py — kino ro'yxati, tahrirlash
  - admin_broadcast.py    — broadcast, eksport, so'rovlar
  - admin_users.py        — foydalanuvchilar boshqaruvi
  - admin_settings.py     — sozlamalar, tariflar
  - admin.py              — /admin buyrug'i, umumiy router
"""

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS, CHANNEL_PRIVATE, CHANNEL_PUBLIC
from bot.database.db import get_db
from bot.keyboards import admin_kb as custom_admin_kb
from bot.utils.admin_tools import generate_unique_code
from bot.utils.helpers import is_admin

router = Router()

# ══════════════════════════════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════════════════════════════
class FilmStates(StatesGroup):
    waiting_video        = State()
    waiting_titles       = State()
    waiting_country_year = State()
    waiting_genres       = State()
    waiting_poster       = State()
    waiting_description  = State()
    waiting_premium      = State()

class SeriesStates(StatesGroup):
    waiting_titles       = State()
    waiting_country_year = State()
    waiting_genres       = State()
    waiting_poster       = State()
    waiting_description  = State()
    waiting_premium      = State()
    waiting_episodes     = State()


# ══════════════════════════════════════════════════════════════════════
#  BOSHLANISH
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "🎬 Kino qo'shish", F.from_user.id.in_(ADMINS))
async def start_add_content(message: Message):
    await message.answer("🎬 Nima qo'shmoqchisiz? Tanlang:", reply_markup=custom_admin_kb.content_type_kb())


# ══════════════════════════════════════════════════════════════════════
#  BEKOR QILISH
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "cancel_admin_fsm")
async def cancel_admin_fsm(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Jarayon bekor qilindi.")
    await call.answer()



# ══ FILM QO'SHISH FLOWI ══
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
    from urllib.parse import quote as url_quote
    movie_deep = f"https://t.me/{bot_user.username}?start=movie_{code}"
    watch_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 TOMOSHA QILISH", url=movie_deep)],
        [InlineKeyboardButton(
            text="📤 Do'stlarga ulashish",
            url=f"https://t.me/share/url?url={url_quote(movie_deep)}"
        )],
    ])
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




# ══ SERIAL QO'SHISH FLOWI ══
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
    from urllib.parse import quote as url_quote
    series_deep = f"https://t.me/{bot_user.username}?start=series_{data['code']}"
    watch_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 SERIALNI KO'RISH", url=series_deep)],
        [InlineKeyboardButton(
            text="📤 Do'stlarga ulashish",
            url=f"https://t.me/share/url?url={url_quote(series_deep)}"
        )],
    ])
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


