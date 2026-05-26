"""
admin_broadcast.py
──────────────────
Statistika, Broadcast xabarlari, CSV eksport, Kino so'rovlar.
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

class BroadcastState(StatesGroup):
    waiting = State()

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


