from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from bot.config import ADMINS, CHANNEL_PRIVATE, CHANNEL_PUBLIC
from bot.database.db import get_db
from bot.utils.admin_tools import generate_unique_code
from bot.handlers.admin.states import SeriesStates
from bot.keyboards import admin_kb

router = Router()

@router.callback_query(F.data == "add_type_series", F.from_user.id.in_(ADMINS))
async def add_series_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(SeriesStates.waiting_titles)
    await call.message.edit_text(
        "📝 **Serial nomlarini yuboring:**\n"
        "1-qator: O'zbekcha nomi\n"
        "2-qator: Ruscha nomi", 
        reply_markup=admin_kb.cancel_fsm_kb()
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
        "🌍 **Mamlakat** va 📅 **Yilni** 2 qatorda yuboring:\n\n"
        "Misol:\n"
        "Koreya\n"
        "2023", 
        reply_markup=admin_kb.cancel_fsm_kb()
    )

@router.message(SeriesStates.waiting_country_year, F.text)
async def process_series_country_year(message: Message, state: FSMContext):
    lines = message.text.splitlines()
    if len(lines) < 2 or not lines[1].strip().isdigit():
        await message.answer("❌ Noto'g'ri format! Mamlakat va Yilni kiriting.")
        return
    await state.update_data(country=lines[0].strip(), year=int(lines[1].strip()))
    await state.set_state(SeriesStates.waiting_genres)
    await message.answer("🎭 **Kamida 2 ta janr yuboring** (Har biri yangi qatorda):", reply_markup=admin_kb.cancel_fsm_kb())

@router.message(SeriesStates.waiting_genres, F.text)
async def process_series_genres(message: Message, state: FSMContext):
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    if len(lines) < 2:
        await message.answer("❌ Kamida 2 ta janr kiritishingiz shart!")
        return
    await state.update_data(genres=", ".join(lines))
    await state.set_state(SeriesStates.waiting_poster)
    await message.answer("🖼 **Poster yuboring (Rasm):**", reply_markup=admin_kb.cancel_fsm_kb())

@router.message(SeriesStates.waiting_poster, F.photo)
async def process_series_poster(message: Message, state: FSMContext):
    await state.update_data(poster_file_id=message.photo[-1].file_id)
    await state.set_state(SeriesStates.waiting_description)
    await message.answer("✍️ **Serial uchun qisqa qiziqarli tavsif yozing:**", reply_markup=admin_kb.cancel_fsm_kb())

@router.message(SeriesStates.waiting_description, F.text)
async def process_series_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(SeriesStates.waiting_premium)
    await message.answer("⭐ **Ushbu serial Premium foydalanuvchilar uchun bo'lsinmi?**", reply_markup=admin_kb.is_premium_kb())

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
        reply_markup=admin_kb.series_control_kb()
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

    await message.answer(f"✅ {data['current_season']}-fasl {ep_num}-qism saqlandi!", reply_markup=admin_kb.series_control_kb())

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
        reply_markup=admin_kb.series_control_kb()
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
