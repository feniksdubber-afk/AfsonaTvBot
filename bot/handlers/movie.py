from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot.database.db import get_db

router = Router()

# ── 1. DEEP LINK HANDLERLARI (movie.py da faqat callback'lar) ────────
# ESLATMA: /start deep_link handleri user.py ga ko'chirildi.
# Bu faylda CommandStart(deep_link=True) olib tashlandi,
# chunki u user.py dagi CommandStart() bilan ziddiyat qilardi
# va hech qachon ishlamasdi (router tartibida user.router birinchi).

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
        row_btns.append(InlineKeyboardButton(
            text=f"{ep[0]}-qism",
            callback_data=f"play_ep_{ep[1]}"
        ))
        if len(row_btns) == 3 or i == len(episodes) - 1:
            kb_buttons.append(row_btns)
            row_btns = []

    kb_buttons.append([InlineKeyboardButton(
        text="◀️ Fasllarga qaytish",
        callback_data=f"back_to_series_{series_id}"
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    await call.message.edit_caption(
        caption=f"📀 <b>{season_num}-Fasl qismlari:</b>\n\nTomosha qilmoqchi bo'lgan qismni tanlang:",
        reply_markup=kb,
        parse_mode="HTML"
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
        # TUZATISH #2: cols qattiq kodlash o'rniga cursor.description orqali dinamik olinadi
        async with db.execute("SELECT * FROM series WHERE id = ?", (series_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                await call.answer("❌ Serial topilmadi!", show_alert=True)
                return
            cols = [d[0] for d in cur.description]
            s = dict(zip(cols, row))

        async with db.execute(
            "SELECT season_number FROM seasons WHERE series_id = ? ORDER BY season_number",
            (series_id,)
        ) as cur:
            seasons = await cur.fetchall()

    kb_buttons = [
        [InlineKeyboardButton(text=f"📀 {r[0]}-Fasl", callback_data=f"show_season_{series_id}_{r[0]}")]
        for r in seasons
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    caption = (
        f"📺 <b>{s['title_uz']}</b> ({s['year']})\n"
        f"🎭 Janr: {s['genres']}\n"
        f"🌍 Davlat: {s['country']}\n\n"
        f"🍿 {s['description']}\n\n"
        f"👇 Faslni tanlang:"
    )
    await call.message.edit_caption(caption=caption, reply_markup=kb, parse_mode="HTML")
    await call.answer()
