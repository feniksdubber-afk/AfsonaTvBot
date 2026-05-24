from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.config import ADMINS
from bot.database.db import get_db

router = Router()

class EditContentState(StatesGroup):
    waiting_code = State()

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

    # Statusga qarab dinamik tugmalar
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
    action = parts[1]  # archive / delete
    c_type = parts[2]  # movie / series
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
