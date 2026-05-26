"""
admin_settings.py
─────────────────
Sozlamalar: karta, tariflar, OMDb API key, ball narxlari.
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

class SettingsState(StatesGroup):
    waiting_card_number    = State()
    waiting_card_owner     = State()
    waiting_tariff_edit    = State()  # eski (saqlanadi, boshqa joylarda ishlatilishi mumkin)

class TariffEditState(StatesGroup):
    """Tarif tahrirlash — har bir maydon alohida qadam."""
    choose_field   = State()   # qaysi maydonni o'zgartirish tanlandi
    waiting_name   = State()   # yangi nom kutilmoqda
    waiting_price  = State()   # yangi narx kutilmoqda
    waiting_duration = State() # yangi muddat kutilmoqda


def _settings_kb(protect_on: bool = True):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    protect_text = "🔒 Nusxa olish: O'CHIRILGAN ✅" if protect_on else "🔓 Nusxa olish: YOQILGAN ❌"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Karta raqami",  callback_data="set_card_number")],
        [InlineKeyboardButton(text="👤 Karta egasi",   callback_data="set_card_owner")],
        [InlineKeyboardButton(text="💰 Tarif narxlari", callback_data="set_tariffs")],
        [InlineKeyboardButton(text="🔎 OMDb API kalit", callback_data="set_omdb_key")],
        [InlineKeyboardButton(text="💎 Ball narxlari",  callback_data="set_points_tariffs")],
        [InlineKeyboardButton(text=protect_text,        callback_data="toggle_protect_content")],
        [InlineKeyboardButton(text="❌ Yopish",        callback_data="close_settings")],
    ])


@router.message(F.text == "🔧 Sozlamalar", F.from_user.id.in_(ADMINS))
async def admin_settings(message: Message):
    async with get_db() as db:
        async with db.execute(
            "SELECT key, value FROM settings WHERE key IN ('card_number','card_owner','protect_content')"
        ) as cur:
            rows = await cur.fetchall()

    s = dict(rows)
    card_num   = s.get("card_number", "—")
    card_owner = s.get("card_owner",  "—")
    protect_on = s.get("protect_content", "1") == "1"
    protect_status = "🔒 O'chirilgan (himoyalangan)" if protect_on else "🔓 Yoqilgan (nusxa olish mumkin)"

    text = (
        f"🔧 <b>Sozlamalar</b>\n\n"
        f"💳 Karta raqami: <code>{card_num}</code>\n"
        f"👤 Karta egasi: <b>{card_owner}</b>\n"
        f"📋 Nusxa olish/Yuborish: {protect_status}\n\n"
        f"Tahrirlash uchun tugmani bosing:"
    )
    await message.answer(text, reply_markup=_settings_kb(protect_on), parse_mode="HTML")


@router.callback_query(F.data == "set_card_number", F.from_user.id.in_(ADMINS))
async def set_card_number_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("💳 Yangi karta raqamini yuboring:\n\nMisol: <code>8600 1234 5678 9012</code>", parse_mode="HTML")
    await state.set_state(SettingsState.waiting_card_number)
    await call.answer()


@router.message(SettingsState.waiting_card_number, F.from_user.id.in_(ADMINS))
async def set_card_number_save(message: Message, state: FSMContext):
    await state.clear()
    val = (message.text or "").strip()
    if not val:
        await message.answer("❌ Bo'sh bo'lishi mumkin emas!")
        return
    async with get_db() as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('card_number', ?)", (val,))
        await db.commit()
    await message.answer(f"✅ Karta raqami saqlandi:\n<code>{val}</code>", parse_mode="HTML",
                         reply_markup=_settings_kb())


@router.callback_query(F.data == "set_card_owner", F.from_user.id.in_(ADMINS))
async def set_card_owner_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("👤 Karta egasining ismini yuboring:\n\nMisol: Abdullayev Sardor")
    await state.set_state(SettingsState.waiting_card_owner)
    await call.answer()


@router.message(SettingsState.waiting_card_owner, F.from_user.id.in_(ADMINS))
async def set_card_owner_save(message: Message, state: FSMContext):
    await state.clear()
    val = (message.text or "").strip()
    if not val:
        await message.answer("❌ Bo'sh bo'lishi mumkin emas!")
        return
    async with get_db() as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('card_owner', ?)", (val,))
        await db.commit()
    await message.answer(f"✅ Karta egasi saqlandi: <b>{val}</b>", parse_mode="HTML",
                         reply_markup=_settings_kb())


@router.callback_query(F.data == "set_tariffs", F.from_user.id.in_(ADMINS))
async def set_tariffs_list(call: CallbackQuery):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    async with get_db() as db:
        async with db.execute("SELECT id, name, duration, price FROM tariffs ORDER BY price") as cur:
            rows = await cur.fetchall()

    if not rows:
        await call.answer("Tarifflar yo'q!", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"⭐ {name} — {price:,} so'm ({duration} kun)",
            callback_data=f"edit_tariff_{tid}"
        )]
        for tid, name, duration, price in rows
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="close_settings")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_text(
        "💰 <b>Tarif narxlari</b>\n\nTahrirlamoqchi bo'lgan tarifni tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await call.answer()


def _tariff_edit_kb(tariff_id: int) -> InlineKeyboardMarkup:
    """Tarif tahrirlash: qaysi maydonni o'zgartirish kerakligini tanlash."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Nomni o'zgartirish",    callback_data=f"trf_name_{tariff_id}")],
        [InlineKeyboardButton(text="💰 Narxni o'zgartirish",   callback_data=f"trf_price_{tariff_id}")],
        [InlineKeyboardButton(text="📅 Muddatni o'zgartirish", callback_data=f"trf_dur_{tariff_id}")],
        [InlineKeyboardButton(text="◀️ Tariflar ro'yxati",     callback_data="set_tariffs")],
    ])


@router.callback_query(F.data.startswith("edit_tariff_"), F.from_user.id.in_(ADMINS))
async def edit_tariff_start(call: CallbackQuery):
    tariff_id = int(call.data.split("_")[2])
    async with get_db() as db:
        async with db.execute(
            "SELECT id, name, duration, price FROM tariffs WHERE id = ?", (tariff_id,)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await call.answer("❌ Tarif topilmadi!", show_alert=True)
        return

    tid, name, duration, price = row
    await call.message.edit_text(
        f"⭐ <b>{name}</b>\n"
        f"💰 Narx: <b>{price:,} so'm</b>\n"
        f"📅 Muddat: <b>{duration} kun</b>\n\n"
        f"Nimani o'zgartirmoqchisiz?",
        reply_markup=_tariff_edit_kb(tid),
        parse_mode="HTML"
    )
    await call.answer()


# ── Nomni o'zgartirish ──────────────────────────────────────────────
@router.callback_query(F.data.startswith("trf_name_"), F.from_user.id.in_(ADMINS))
async def tariff_name_start(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split("_")[2])
    async with get_db() as db:
        async with db.execute("SELECT name FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()

    old_name = row[0] if row else "?"
    await state.update_data(tariff_id=tariff_id)
    await state.set_state(TariffEditState.waiting_name)
    await call.message.answer(
        f"✏️ Hozirgi nom: <b>{old_name}</b>\n\n"
        f"Yangi nomni yuboring:\n"
        f"Misol: <code>Oylik</code>, <code>Yillik</code>, <code>3 Oylik</code>",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(TariffEditState.waiting_name, F.from_user.id.in_(ADMINS))
async def tariff_name_save(message: Message, state: FSMContext):
    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("❌ Nom bo'sh bo'lishi mumkin emas!")
        return

    data = await state.get_data()
    tariff_id = data.get("tariff_id")
    await state.clear()

    async with get_db() as db:
        async with db.execute("SELECT name FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()
        old_name = row[0] if row else "?"
        await db.execute("UPDATE tariffs SET name = ? WHERE id = ?", (new_name, tariff_id))
        await db.commit()

    await message.answer(
        f"✅ Tarif nomi yangilandi:\n"
        f"<b>{old_name}</b> → <b>{new_name}</b>",
        parse_mode="HTML",
        reply_markup=_tariff_edit_kb(tariff_id)
    )


# ── Narxni o'zgartirish ─────────────────────────────────────────────
@router.callback_query(F.data.startswith("trf_price_"), F.from_user.id.in_(ADMINS))
async def tariff_price_start(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split("_")[2])
    async with get_db() as db:
        async with db.execute("SELECT name, price FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()

    name, price = (row[0], row[1]) if row else ("?", 0)
    await state.update_data(tariff_id=tariff_id)
    await state.set_state(TariffEditState.waiting_price)
    await call.message.answer(
        f"💰 <b>{name}</b>\n"
        f"Hozirgi narx: <b>{price:,} so'm</b>\n\n"
        f"Yangi narxni yuboring (faqat raqam):\n"
        f"Misol: <code>49900</code> yoki <code>49 900</code>",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(TariffEditState.waiting_price, F.from_user.id.in_(ADMINS))
async def tariff_price_save(message: Message, state: FSMContext):
    raw = (message.text or "").replace(",", "").replace(" ", "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("❌ Faqat musbat raqam yuboring!\nMisol: <code>49900</code>", parse_mode="HTML")
        return

    new_price = int(raw)
    data = await state.get_data()
    tariff_id = data.get("tariff_id")
    await state.clear()

    async with get_db() as db:
        async with db.execute("SELECT name, price FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()
        old_name, old_price = (row[0], row[1]) if row else ("?", 0)
        await db.execute("UPDATE tariffs SET price = ? WHERE id = ?", (new_price, tariff_id))
        await db.commit()

    await message.answer(
        f"✅ <b>{old_name}</b> narxi yangilandi:\n"
        f"💰 <b>{old_price:,}</b> → <b>{new_price:,} so'm</b>",
        parse_mode="HTML",
        reply_markup=_tariff_edit_kb(tariff_id)
    )


# ── Muddatni o'zgartirish ───────────────────────────────────────────
@router.callback_query(F.data.startswith("trf_dur_"), F.from_user.id.in_(ADMINS))
async def tariff_dur_start(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split("_")[2])
    async with get_db() as db:
        async with db.execute("SELECT name, duration FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()

    name, duration = (row[0], row[1]) if row else ("?", 0)
    await state.update_data(tariff_id=tariff_id)
    await state.set_state(TariffEditState.waiting_duration)
    await call.message.answer(
        f"📅 <b>{name}</b>\n"
        f"Hozirgi muddat: <b>{duration} kun</b>\n\n"
        f"Yangi muddatni <b>kun</b> hisobida yuboring:\n"
        f"Misol: <code>30</code> (1 oy), <code>365</code> (1 yil), <code>7</code> (1 hafta)",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(TariffEditState.waiting_duration, F.from_user.id.in_(ADMINS))
async def tariff_dur_save(message: Message, state: FSMContext):
    raw = (message.text or "").replace(" ", "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("❌ Faqat musbat raqam (kun) yuboring!\nMisol: <code>30</code>", parse_mode="HTML")
        return

    new_dur = int(raw)
    data = await state.get_data()
    tariff_id = data.get("tariff_id")
    await state.clear()

    async with get_db() as db:
        async with db.execute("SELECT name, duration FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()
        old_name, old_dur = (row[0], row[1]) if row else ("?", 0)
        await db.execute("UPDATE tariffs SET duration = ? WHERE id = ?", (new_dur, tariff_id))
        await db.commit()

    await message.answer(
        f"✅ <b>{old_name}</b> muddati yangilandi:\n"
        f"📅 <b>{old_dur} kun</b> → <b>{new_dur} kun</b>",
        parse_mode="HTML",
        reply_markup=_tariff_edit_kb(tariff_id)
    )


@router.callback_query(F.data == "toggle_protect_content", F.from_user.id.in_(ADMINS))
async def toggle_protect_content(call: CallbackQuery):
    """Protect content sozlamasini yoqish/o'chirish."""
    async with get_db() as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'protect_content'") as cur:
            row = await cur.fetchone()
        current = (row[0] if row else "1")
        new_val = "0" if current == "1" else "1"
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('protect_content', ?)",
            (new_val,)
        )
        await db.commit()

        async with db.execute(
            "SELECT key, value FROM settings WHERE key IN ('card_number','card_owner','protect_content')"
        ) as cur:
            rows = await cur.fetchall()

    s = dict(rows)
    protect_on = s.get("protect_content", "1") == "1"
    protect_status = "🔒 O'chirilgan (himoyalangan)" if protect_on else "🔓 Yoqilgan (nusxa olish mumkin)"

    text = (
        f"🔧 <b>Sozlamalar</b>\n\n"
        f"💳 Karta raqami: <code>{s.get('card_number', '—')}</code>\n"
        f"👤 Karta egasi: <b>{s.get('card_owner', '—')}</b>\n"
        f"📋 Nusxa olish/Yuborish: {protect_status}\n\n"
        f"Tahrirlash uchun tugmani bosing:"
    )
    status_msg = "✅ Nusxa olish o'chirildi (himoyalandi)" if protect_on else "✅ Nusxa olish yoqildi"
    await call.answer(status_msg, show_alert=True)
    try:
        await call.message.edit_text(text, reply_markup=_settings_kb(protect_on), parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data == "close_settings", F.from_user.id.in_(ADMINS))
async def close_settings(call: CallbackQuery):
    await call.message.edit_text("🔧 Sozlamalar yopildi.")
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  🏠 BOSH MENYU (admin paneldan qaytish)
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "🏠 Bosh menyu", F.from_user.id.in_(ADMINS))
async def admin_back_to_main(message: Message):
    async with get_db() as db:
        async with db.execute("SELECT lang FROM users WHERE tg_id = ?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
    lang = row[0] if row else "uz"
    await message.answer(
        "🏠 Bosh menyuga qaytildi.",
        reply_markup=main_menu(lang)
    )


# ── OMDb API Key sozlash ───────────────────────────────────────────────
class OmdbKeyState(StatesGroup):
    waiting = State()

class PointsTariffState(StatesGroup):
    waiting = State()
    tariff_id = State()


@router.callback_query(F.data == "set_omdb_key", F.from_user.id.in_(ADMINS))
async def set_omdb_key_start(call: CallbackQuery, state: FSMContext):
    async with get_db() as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'omdb_api_key'") as cur:
            row = await cur.fetchone()
    current = row[0] if row else "(kiritilmagan)"
    await call.message.answer(
        f"🔎 <b>OMDb API Key</b>\n\n"
        f"Hozirgi: <code>{current}</code>\n\n"
        f"Yangi API kalitni yuboring:\n"
        f"👉 Bepul kalit olish: https://www.omdbapi.com/apikey.aspx\n"
        f"(1000 so'rov/kun)",
        parse_mode="HTML"
    )
    await state.set_state(OmdbKeyState.waiting)
    await call.answer()


@router.message(OmdbKeyState.waiting, F.from_user.id.in_(ADMINS))
async def set_omdb_key_save(message: Message, state: FSMContext):
    await state.clear()
    key = (message.text or "").strip()
    if not key or len(key) < 8:
        await message.answer("❌ Kalit noto'g'ri ko'rinadi!")
        return
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('omdb_api_key', ?)", (key,)
        )
        await db.commit()
    await message.answer(
        f"✅ OMDb API kalit saqlandi: <code>{key}</code>\n\n"
        f"Foydalanuvchilar /imdb buyrug'ini ishlatishi mumkin!",
        parse_mode="HTML",
        reply_markup=_settings_kb()
    )


# ── Ball narxlari (tariffs.points_price) sozlash ─────────────────────
@router.callback_query(F.data == "set_points_tariffs", F.from_user.id.in_(ADMINS))
async def set_points_tariffs_list(call: CallbackQuery):
    async with get_db() as db:
        async with db.execute(
            "SELECT id, name, duration, price, points_price FROM tariffs ORDER BY price"
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await call.answer("Tarifflar yo'q!", show_alert=True)
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [
        [InlineKeyboardButton(
            text=f"⭐ {name} — {pts or 0:,} ball",
            callback_data=f"edit_pts_tariff_{tid}"
        )]
        for tid, name, duration, price, pts in rows
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="close_settings")])
    await call.message.edit_text(
        "💎 <b>Ball narxlari</b>\n\n"
        "Tarif tanlang va ball narxini belgilang.\n"
        "0 = ballar bilan sotib bo'lmaydi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("edit_pts_tariff_"), F.from_user.id.in_(ADMINS))
async def edit_pts_tariff_start(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split("_")[3])
    async with get_db() as db:
        async with db.execute(
            "SELECT name, duration, points_price FROM tariffs WHERE id = ?", (tariff_id,)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await call.answer("❌ Topilmadi!", show_alert=True)
        return

    name, duration, pts = row
    await state.update_data(tariff_id=tariff_id)
    await state.set_state(PointsTariffState.waiting)
    await call.message.answer(
        f"⭐ <b>{name}</b> ({duration} kun)\n"
        f"Hozirgi ball narxi: <b>{pts or 0:,} ball</b>\n\n"
        f"Yangi ball narxini yuboring (0 = o'chirilgan):",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(PointsTariffState.waiting, F.from_user.id.in_(ADMINS))
async def edit_pts_tariff_save(message: Message, state: FSMContext):
    data = await state.get_data()
    tariff_id = data.get("tariff_id")
    await state.clear()

    text = (message.text or "").strip().replace(",", "").replace(" ", "")
    if not text.isdigit():
        await message.answer("❌ Faqat raqam yuboring!")
        return

    pts = int(text)
    async with get_db() as db:
        await db.execute(
            "UPDATE tariffs SET points_price = ? WHERE id = ?", (pts, tariff_id)
        )
        await db.commit()

    label = f"{pts:,} ball" if pts > 0 else "0 (o'chirilgan)"
    await message.answer(
        f"✅ Ball narxi yangilandi: <b>{label}</b>",
        parse_mode="HTML",
        reply_markup=_settings_kb()
    )
