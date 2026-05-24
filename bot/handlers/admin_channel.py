"""
Admin: Majburiy kanal boshqaruvi
──────────────────────────────────
Buyruqlar:
  /channels         — kanal ro'yxati + boshqaruv
  + kanal qo'shish (ID yoki @username)
  + kanal o'chirish
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS
from bot.utils.channels import (
    get_required_channels,
    set_required_channels,
    fetch_channel_info
)

router = Router()


def is_admin(uid: int) -> bool:
    return uid in ADMINS


# ─── FSM ────────────────────────────────────────────────────────────
class AddChannelState(StatesGroup):
    waiting_channel = State()


# ─── Klaviatura ─────────────────────────────────────────────────────
def channels_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for i, ch in enumerate(channels):
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {ch['title']}",
                callback_data=f"del_channel_{i}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel")
    ])
    if channels:
        buttons.append([
            InlineKeyboardButton(text="🗑 Hammasini o'chirish", callback_data="clear_channels")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── /channels — asosiy ko'rinish ───────────────────────────────────
@router.message(Command("channels"))
@router.message(F.text == "🔧 Kanallar")
async def cmd_channels(message: Message):
    if not is_admin(message.from_user.id):
        return

    channels = await get_required_channels()
    await _show_channels(message, channels, edit=False)


async def _show_channels(event: Message | CallbackQuery, channels: list, edit: bool = False):
    if not channels:
        text = (
            "📢 <b>Majburiy obuna kanallari</b>\n\n"
            "❌ Hozircha hech qanday kanal yo'q.\n"
            "Foydalanuvchilar obunasiz ham botdan foydalana oladi.\n\n"
            "➕ Kanal qo'shish uchun tugmani bosing:"
        )
    else:
        lines = "\n".join(
            f"  {i+1}. <a href='{ch['link']}'>{ch['title']}</a> (<code>{ch['id']}</code>)"
            for i, ch in enumerate(channels)
        )
        text = (
            f"📢 <b>Majburiy obuna kanallari</b>\n\n"
            f"{lines}\n\n"
            f"Jami: <b>{len(channels)} ta</b>\n\n"
            f"🗑 O'chirish uchun kanal tugmasini bosing:"
        )

    kb = channels_kb(channels)

    if edit and isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    elif isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── Kanal qo'shish ─────────────────────────────────────────────────
@router.callback_query(F.data == "add_channel")
async def cb_add_channel(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return

    await call.message.answer(
        "➕ <b>Kanal qo'shish</b>\n\n"
        "Kanal <b>ID</b> yoki <b>@username</b> ni yuboring:\n\n"
        "<i>Misol: <code>-1001234567890</code> yoki <code>@mening_kanalim</code></i>\n\n"
        "⚠️ Bot kanalga <b>admin</b> bo'lishi kerak!",
        parse_mode="HTML"
    )
    await state.set_state(AddChannelState.waiting_channel)
    await call.answer()


@router.message(AddChannelState.waiting_channel)
async def process_add_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    channel_input = message.text.strip()

    # Kanal ma'lumotlarini Telegramdan olish
    await message.answer("🔍 Kanal tekshirilmoqda...")
    ch_info = await fetch_channel_info(message.bot, channel_input)

    if not ch_info:
        await message.answer(
            "❌ <b>Kanal topilmadi!</b>\n\n"
            "Tekshiring:\n"
            "• Bot kanal adminimi?\n"
            "• ID yoki username to'g'rimi?\n\n"
            "Qayta urinib ko'ring:",
            parse_mode="HTML"
        )
        return

    # Mavjud kanallar ro'yxatiga qo'shish
    channels = await get_required_channels()

    # Takrorlanishni tekshirish
    if any(ch["id"] == ch_info["id"] for ch in channels):
        await message.answer(
            f"⚠️ <b>{ch_info['title']}</b> kanali allaqachon qo'shilgan!",
            parse_mode="HTML"
        )
        await state.clear()
        return

    channels.append(ch_info)
    await set_required_channels(channels)

    await state.clear()
    await message.answer(
        f"✅ <b>{ch_info['title']}</b> kanali qo'shildi!\n\n"
        f"Endi foydalanuvchilar bu kanalga obuna bo'lmasa botdan foydalana olmaydi.",
        parse_mode="HTML"
    )

    # Yangilangan ro'yxatni ko'rsatish
    await _show_channels(message, channels, edit=False)


# ─── Kanal o'chirish ────────────────────────────────────────────────
@router.callback_query(F.data.startswith("del_channel_"))
async def cb_del_channel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    idx = int(call.data.split("_")[2])
    channels = await get_required_channels()

    if idx >= len(channels):
        await call.answer("❌ Kanal topilmadi!", show_alert=True)
        return

    removed = channels.pop(idx)
    await set_required_channels(channels)

    await call.answer(f"✅ {removed['title']} o'chirildi!")
    await _show_channels(call, channels, edit=True)


# ─── Hammasini o'chirish ─────────────────────────────────────────────
@router.callback_query(F.data == "clear_channels")
async def cb_clear_channels(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    # Tasdiqlash
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, hammasini o'chir", callback_data="confirm_clear_channels"),
        InlineKeyboardButton(text="❌ Yo'q", callback_data="back_to_channels"),
    ]])
    await call.message.edit_text(
        "⚠️ Barcha majburiy kanallarni o'chirishni tasdiqlaysizmi?\n"
        "Foydalanuvchilar obunasiz ham botdan foydalana oladi.",
        reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data == "confirm_clear_channels")
async def cb_confirm_clear(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    await set_required_channels([])
    await call.answer("✅ Barcha kanallar o'chirildi!")
    await _show_channels(call, [], edit=True)


@router.callback_query(F.data == "back_to_channels")
async def cb_back_to_channels(call: CallbackQuery):
    channels = await get_required_channels()
    await _show_channels(call, channels, edit=True)
    await call.answer()
