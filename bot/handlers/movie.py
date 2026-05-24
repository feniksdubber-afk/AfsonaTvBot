from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from bot.database.db import get_db

router = Router()

# ── 1. START DECODER TIZIMI ─────────────────────────────────────────
@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink_process(message: Message):
    args = message.text.split()[1]
    
    # A. FILM CHIKARISH
    if args.startswith("movie_"):
        code = args.replace("movie_", "")
        async with get_db() as db:
            async with db.execute("SELECT * FROM movies WHERE code = ?", (code,)) as cur:
                movie = await cur.fetchone()
                
        if not movie:
            await message.answer("❌ Kontent topilmadi yoki o'chirilgan!")
            return
            
        # Ustunlarni xavfsiz moslash
        cols = [d[0] for d in (await get_db().execute("PRAGMA table_info(movies)")).fetchall()]
        m_dict = dict(zip(cols, movie))
        
        # Soft-delete va Arxiv tekshirish
        if m_dict.get("status") == "deleted":
            await message.answer("❌ Kontent topilmadi!")
            return
        if m_dict.get("status") == "archived":
            await message.answer("⛔ Bu kontent vaqtinchalik arxivda.")
            return

        # BACKWARD COMPATIBILITY: Eski va yangi title ustunlarini xavfsiz tekshirib nomlash
        title_display = m_dict.get('title_uz') or m_dict.get('title') or "Nomsiz kino"

        caption = (
            f"🎬 <b>{title_display}</b> ({m_dict.get('year', '?')})\n"
            f"🎭 {m_dict.get('genres') or m_dict.get('genre', '')}\n"
            f"🌍 {m_dict.get('country', '')}\n\n"
            f"🍿 {m_dict.get('description', '')}"
        )
        
        # Views sonini oshirish
        async with get_db() as db:
            await db.execute("UPDATE movies SET views = views + 1 WHERE id = ?", (m_dict['id'],))
            await db.commit()

        await message.answer_video(video=m_dict['file_id'], caption=caption, parse_mode="HTML")

    # B. SERIAL INFOSINI CHIKARISH
    elif args.startswith("series_"):
        code = args.replace("series_", "")
        async with get_db() as db:
            async with db.execute("SELECT * FROM series WHERE code = ?", (code,)) as cur:
                series = await cur.fetchone()
                
        if not series:
            await message.answer("❌ Serial topilmadi!")
            return
            
        cols = ["id", "code", "title_uz", "title_ru", "country", "year", "genres", "poster_file_id", "description", "is_premium", "status"]
        s_dict = dict(zip(cols, series))
        
        if s_dict["status"] == "deleted":
            await message.answer("❌ Kontent topilmadi!")
            return
        if s_dict["status"] == "archived":
            await message.answer("⛔ Bu kontent vaqtinchalik arxivda.")
            return

        # Fasllarni bazadan olish
        async with get_db() as db:
            async with db.execute("SELECT season_number FROM seasons WHERE series_id = ? ORDER BY season_number", (s_dict['id'],)) as cur:
                seasons = await cur.fetchall()

        kb_buttons = []
        for row in seasons:
            kb_buttons.append([InlineKeyboardButton(text=f"📀 {row[0]}-Fasl", callback_data=f"show_season_{s_dict['id']}_{row[0]}")])
            
        kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
        caption = (
            f"📺 <b>{s_dict['title_uz']}</b> ({s_dict['year']})\n"
            f"🎭 Janr: {s_dict['genres']}\n"
            f"🌍 Davlat: {s_dict['country']}\n\n"
            f"🍿 {s_dict['description']}\n\n"
            f"👇 Faslni tanlang:"
        )
        
        await message.answer_photo(photo=s_dict['poster_file_id'], caption=caption, reply_markup=kb, parse_mode="HTML")

# ── 2. FASL BOSILGANDA QISMLARNI CHIKARISH ───────────────────────────
@router.callback_query(F.data.startswith("show_season_"))
async def cb_show_season_episodes(call: CallbackQuery):
    parts = call.data.split("_")
    series_id = int(parts[2])
    season_num = int(parts[3])
    
    async with get_db() as db:
        async with db.execute("""
            SELECT episode_number, id FROM episodes 
            WHERE series_id = ? AND season_number = ? 
            ORDER BY episode_number
        """, (series_id, season_num)) as cur:
            episodes = await cur.fetchall()
            
    if not episodes:
        await call.answer("⚠️ Bu faslda qismlar yuklanmagan!", show_alert=True)
        return
        
    kb_buttons = []
    row_btns = []
    for i, ep in enumerate(episodes):
        row_btns.append(InlineKeyboardButton(text=f"{ep[0]}-qism", callback_data=f"play_ep_{ep[1]}"))
        if len(row_btns) == 3 or i == len(episodes) - 1:
            kb_buttons.append(row_btns)
            row_btns = []
            
    kb_buttons.append([InlineKeyboardButton(text="◀️ Fasllarga qaytish", callback_data=f"back_to_series_{series_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    
    await call.message.edit_caption(
        caption=f"📀 **{season_num}-Fasl qismlari:**\n\nTomosha qilmoqchi bo'lgan qismni tanlang:", 
        reply_markup=kb, 
        parse_mode="Markdown"
    )
    await call.answer()

# ── 3. EPIZOD BOSILGANDA VIDEONI YUBORISH ───────────────────────────
@router.callback_query(F.data.startswith("play_ep_"))
async def cb_play_selected_episode(call: CallbackQuery):
    ep_id = int(call.data.split("_")[2])
    
    async with get_db() as db:
        async with db.execute("""
            SELECT e.file_id, s.title_uz, e.season_number, e.episode_number 
            FROM episodes e 
            JOIN series s ON e.series_id = s.id 
            WHERE e.id = ?
        """, (ep_id,)) as cur:
            res = await cur.fetchone()
            
    if not res:
        await call.answer("❌ Video fayl topilmadi!", show_alert=True)
        return
        
    file_id, title_uz, season, episode = res
    await call.message.answer_video(
        video=file_id,
        caption=f"📺 <b>{title_uz}</b>\n📀 {season}-fasl | {episode}-qism",
        parse_mode="HTML"
    )
    await call.answer()

# ── 4. SERIAL MENYUSIGA QAYTISH ─────────────────────────────────────
@router.callback_query(F.data.startswith("back_to_series_"))
async def cb_back_to_series_menu(call: CallbackQuery):
    series_id = int(call.data.split("_")[3])
    
    async with get_db() as db:
        async with db.execute("SELECT * FROM series WHERE id = ?", (series_id,)) as cur:
            series = await cur.fetchone()
        async with db.execute("SELECT season_number FROM seasons WHERE series_id = ? ORDER BY season_number", (series_id,)) as cur:
            seasons = await cur.fetchall()
            
    cols = ["id", "code", "title_uz", "title_ru", "country", "year", "genres", "poster_file_id", "description", "is_premium", "status"]
    s_dict = dict(zip(cols, series))
    
    kb_buttons = [[InlineKeyboardButton(text=f"📀 {r[0]}-Fasl", callback_data=f"show_season_{series_id}_{r[0]}")] for r in seasons]
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    
    caption = (
        f"📺 <b>{s_dict['title_uz']}</b> ({s_dict['year']})\n"
        f"🎭 Janr: {s_dict['genres']}\n"
        f"🌍 Davlat: {s_dict['country']}\n\n"
        f"🍿 {s_dict['description']}\n\n"
        f"👇 Faslni tanlang:"
    )
    await call.message.edit_caption(caption=caption, reply_markup=kb, parse_mode="HTML")
    await call.answer()
