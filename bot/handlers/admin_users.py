"""
admin_users.py
──────────────
Foydalanuvchilar ro'yxati, ban/unban, premium berish, xabar yuborish.
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

class MsgUserState(StatesGroup):
    waiting = State()
    target  = State()

class GivePremiumState(StatesGroup):
    waiting = State()
    target  = State()

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


class UserSearchState(StatesGroup):
    waiting = State()


@router.message(F.text == "🔍 User qidirish", F.from_user.id.in_(ADMINS))
async def admin_user_search_start(message: Message, state: FSMContext):
    await state.set_state(UserSearchState.waiting)
    await message.answer(
        "🔍 Foydalanuvchi <b>ID</b>, <b>@username</b> yoki <b>ism</b>ini yuboring:",
        parse_mode="HTML"
    )


@router.message(UserSearchState.waiting, F.from_user.id.in_(ADMINS))
async def admin_user_search_process(message: Message, state: FSMContext):
    await state.clear()
    query = message.text.strip().lstrip("@")
    await _show_user_detail_by_query(message, query)


@router.message(F.text.startswith("/user_"), F.from_user.id.in_(ADMINS))
async def admin_user_detail(message: Message):
    query = message.text.split("_", 1)[1] if "_" in message.text else ""
    if not query:
        await message.answer("❌ Format: /user_123456")
        return
    await _show_user_detail_by_query(message, query)


async def _show_user_detail_by_query(message: Message, query: str):
    async with get_db() as db:
        u = None
        # 1. ID bo'yicha
        if query.lstrip("-").isdigit():
            async with db.execute("SELECT * FROM users WHERE tg_id = ?", (int(query),)) as cur:
                row = await cur.fetchone()
                if row:
                    cols = [d[0] for d in cur.description]
                    u = dict(zip(cols, row))
        # 2. Username bo'yicha
        if not u:
            async with db.execute(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (query,)
            ) as cur:
                row = await cur.fetchone()
                if row:
                    cols = [d[0] for d in cur.description]
                    u = dict(zip(cols, row))
        # 3. Ism bo'yicha
        if not u:
            async with db.execute(
                "SELECT * FROM users WHERE full_name LIKE ? LIMIT 1", (f"%{query}%",)
            ) as cur:
                row = await cur.fetchone()
                if row:
                    cols = [d[0] for d in cur.description]
                    u = dict(zip(cols, row))

        if not u:
            await message.answer(f"❌ <b>«{query}»</b> bo'yicha foydalanuvchi topilmadi.", parse_mode="HTML")
            return

        # Ko'rish tarixi (oxirgi 5 ta)
        async with db.execute(
            """SELECT
                 COALESCE(m.title_uz, m.title, s.title_uz, 'Nomsiz') as title,
                 CASE WHEN h.movie_id IS NOT NULL THEN '🎬' ELSE '📺' END as icon,
                 h.watched_at
               FROM watch_history h
               LEFT JOIN movies m ON m.id = h.movie_id
               LEFT JOIN series s ON s.id = h.series_id
               WHERE h.user_id = ?
               ORDER BY h.watched_at DESC LIMIT 5""",
            (u["tg_id"],)
        ) as cur:
            history = await cur.fetchall()

        async with db.execute(
            "SELECT COUNT(*) FROM watch_history WHERE user_id = ?", (u["tg_id"],)
        ) as cur:
            watch_total = (await cur.fetchone())[0]

        async with db.execute(
            "SELECT COUNT(*) FROM favorites WHERE user_id = ?", (u["tg_id"],)
        ) as cur:
            fav_total = (await cur.fetchone())[0]

        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE referrer_id = ?", (u["tg_id"],)
        ) as cur:
            referral_total = (await cur.fetchone())[0]

    prem_label = "✅ Ha" if u["is_premium"] else "❌ Yo'q"
    ban_label  = "🚫 Ha" if u["is_banned"]  else "✅ Yo'q"
    prem_until = u.get("premium_until") or "—"

    history_text = ""
    for title, icon, watched_at in history:
        date = (watched_at or "")[:10]
        history_text += f"  {icon} {title} <i>({date})</i>\n"
    if not history_text:
        history_text = "  — hali hech narsa ko'rмади\n"

    text = (
        f"👤 <b>Foydalanuvchi ma'lumotlari</b>\n\n"
        f"🆔 ID: <code>{u['tg_id']}</code>\n"
        f"👨 Ism: {u['full_name']}\n"
        f"🔗 Username: {'@' + u['username'] if u.get('username') else '—'}\n"
        f"🌐 Til: {u['lang']}\n"
        f"📅 Ro'yxatdan: {(u.get('created_at') or '')[:10]}\n\n"
        f"⭐ Premium: {prem_label}\n"
        f"📅 Premium muddat: {prem_until}\n"
        f"💰 Balans: {u['balance']} ball\n"
        f"🚫 Ban: {ban_label}\n\n"
        f"📊 <b>Faollik:</b>\n"
        f"  🎬 Ko'rishlar: {watch_total} ta\n"
        f"  ❤️ Sevimlilar: {fav_total} ta\n"
        f"  👥 Referrallar: {referral_total} ta\n\n"
        f"🕓 <b>Oxirgi ko'rilganlar:</b>\n{history_text}"
    )
    await message.answer(
        text,
        reply_markup=user_manage_kb(u["tg_id"], u["is_banned"]),
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

