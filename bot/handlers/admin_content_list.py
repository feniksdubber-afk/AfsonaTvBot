"""
admin_content_list.py
─────────────────────
Kinolar ro'yxati, tahrirlash, faollashtirish/o'chirish.
"""

import asyncio
import csv
import io
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
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
from bot.utils.helpers import is_admin, get_user, txt

router = Router()

class EditContentState(StatesGroup):
    waiting_code = State()

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
        [InlineKeyboardButton(text="✏️ To'liq tahrirlash", callback_data=f"full_edit_{c_type}_{c_id}")],
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
    # ✏️ To'liq tahrirlash tugmasi qo'shildi (#6)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb_admin_movie = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ To'liq tahrirlash", callback_data=f"full_edit_movie_{m_id}")],
        [
            InlineKeyboardButton(text="📥 Arxiv",    callback_data=f"status_archive_movie_{m_id}"),
            InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"status_delete_movie_{m_id}"),
        ],
    ])
    await message.answer(text, reply_markup=kb_admin_movie, parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════
#  E. STATISTIKA
