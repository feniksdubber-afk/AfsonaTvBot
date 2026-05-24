from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from bot.config import ADMINS, CHANNEL_PRIVATE, CHANNEL_PUBLIC
from bot.database.db import get_db
from bot.utils.admin_tools import generate_unique_code
from bot.handlers.admin.states import FilmStates
from bot.keyboards import admin_kb

router = Router()

@router.message(F.text == "🎬 Kino qo'shish", F.from_user.id.in_(ADMINS))
async def start_add_content(message: Message):
    await message.answer("🎬 **Nima qo'shmoqchisiz?** Tanlang:", reply_markup=admin_kb.content_type_kb())

@router.callback_query(F.data == "add_type_film", F.from_user.id.in_(ADMINS))
async def add_film_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(FilmStates.waiting_video)
    await call.message.edit_text("🎥 **Film videosini yuboring:**", reply_markup=admin_kb.cancel_fsm_kb())
    await call.answer()

@router.message(FilmStates.waiting_video, F.video)
async def process_film_video(message: Message, state: FSMContext):
    await state.update_data(file_id=message.video.file_id)
    await state.set_state(FilmStates.waiting_titles)
    await message.answer(
        "📝 **Film nomlarini yuboring:**\n"
        "1-qator: O'zbekcha nomi\n"
        "2-qator: Ruscha nomi", 
        reply_markup=admin_kb.cancel_fsm_kb()
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
        "🌍 **Mamlakat** va 📅 **Yilni** 2 qatorda yuboring:\n\n"
        "Misol:\n"
        "Fransiya\n"
        "2012", 
        reply_markup=admin_kb.cancel_fsm_kb()
    )

@router.message(FilmStates.waiting_country_year, F.text)
async def process_film_country_year(message: Message, state: FSMContext):
    lines = message.text.splitlines()
    if len(lines) < 2 or not lines[1].strip().isdigit():
        await message.answer("❌ Format xato! Mamlakat va Yilni to'g'ri kiriting (Mamlakat birinchi qatorda, yil ikkinchi qatorda).")
        return
    await state.update_data(country=lines[0].strip(), year=int(lines[1].strip()))
    await state.set_state(FilmStates.waiting_genres)
    await message.answer("🎭 **Kamida 2 ta janr yuboring** (Har biri yangi qatorda):", reply_markup=admin_kb.cancel_fsm_kb())

@router.message(FilmStates.waiting_genres, F.text)
async def process_film_genres(message: Message, state: FSMContext):
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    if len(lines) < 2:
        await message.answer("❌ Kamida 2 ta janr kiriting!")
        return
    await state.update_data(genres=", ".join(lines))
    await state.set_state(FilmStates.waiting_poster)
    await message.answer("🖼 **Poster yuboring (Rasm):**", reply_markup=admin_kb.cancel_fsm_kb())

@router.message(FilmStates.waiting_poster, F.photo)
async def process_film_poster(message: Message, state: FSMContext):
    await state.update_data(poster_file_id=message.photo[-1].file_id)
    await state.set_state(FilmStates.waiting_description)
    await message.answer("✍js **Film uchun qisqa qiziqarli tavsif yozing:**", reply_markup=admin_kb.cancel_fsm_kb())

@router.message(FilmStates.waiting_description, F.text)
async def process_film_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(FilmStates.waiting_premium)
    await message.answer("⭐ **Ushbu film Premium foydalanuvchilar uchun bo'lsinmi?**", reply_markup=admin_kb.is_premium_kb())

@router.callback_query(FilmStates.waiting_premium, F.data.startswith("premium_"))
async def save_film_final(call: CallbackQuery, state: FSMContext, bot: Bot):
    is_premium = 1 if call.data == "premium_yes" else 0
    data = await state.get_data()
    await state.clear()
    
    async with get_db() as db:
        code = await generate_unique_code(db)
        
        # Database'ga yozish
        await db.execute("""
            INSERT INTO movies (code, title_uz, title_ru, country, year, genres, description, file_id, poster_file_id, is_premium, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (code, data['title_uz'], data['title_ru'], data['country'], data['year'], data['genres'], data['description'], data['file_id'], data['poster_file_id'], is_premium))
        await db.commit()

    # Private Kanalga Backup (Fayl yo'qolmasligi va telegram keshida qolishi uchun)
    try:
        await bot.send_video(
            chat_id=CHANNEL_PRIVATE,
            video=data['file_id'],
            caption=f"📦 BACKUP | FILM\n🔑 KOD: {code}\n🎬 NOM (UZ): {data['title_uz']}\n🌐 NOM (RU): {data['title_ru']}"
        )
    except Exception as e:
        print(f"Private Backup error: {e}")

    # Public Kanalga Reklama Posti
    bot_user = await bot.get_me()
    premium_tag = "⭐ PREMIUM" if is_premium else "🔓 TEKIN"
    
    pub_caption = (
        f"🎬 <b>{data['title_uz'].upper()}</b>\n"
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

@router.callback_query(F.data == "cancel_admin_fsm")
async def cancel_fsm_process(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Jarayon bekor qilindi.")
    await call.answer()

```
