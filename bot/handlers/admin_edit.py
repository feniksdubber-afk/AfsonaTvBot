"""
admin_edit.py  (#6)
────────────────────
Admin kinolar to'liq tahrirlash:
  - Nom (UZ / RU)
  - Tavsif
  - Janr
  - Yil
  - Mamlakat
  - Poster (rasm)
  - Video (file)
  - Premium holati

Ishlatish:
  Admin panel → 📋 Kinolar ro'yxati → /admin_movie_{id}
  → "✏️ To'liq tahrirlash" tugmasi → ushbu flow

Eski admin.py dagi process_content_status_change + edit_movie_kb
bilan birgalikda ishlaydi.
"""

import logging

from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS
from bot.database.db import get_db
from bot.keyboards.admin_kb import cancel_fsm_kb

logger = logging.getLogger(__name__)
router = Router()


# ══════════════════════════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════════════════════════

class MovieEditState(StatesGroup):
    waiting_value = State()   # yangi qiymatni kutish


# ══════════════════════════════════════════════════════════════════
#  YORDAMCHI
# ══════════════════════════════════════════════════════════════════

FIELD_META = {
    "title_uz":    ("📝 O'zbekcha nom",  "Yangi o'zbekcha nomini yuboring:",          "TEXT"),
    "title_ru":    ("🌐 Ruscha nom",     "Yangi ruscha nomini yuboring:",              "TEXT"),
    "description": ("📄 Tavsif",         "Yangi tavsifni yuboring:",                   "TEXT"),
    "genres":      ("🎭 Janr",           "Janrlarni yangi qatorda yuboring (min 1):",  "TEXT"),
    "year":        ("📅 Yil",            "Yangi yilni yuboring (masalan: 2024):",      "INT"),
    "country":     ("🌍 Mamlakat",       "Yangi mamlakatni yuboring:",                 "TEXT"),
    "poster":      ("🖼 Poster",         "Yangi poster rasmini yuboring:",             "PHOTO"),
    "file":        ("🎬 Video",          "Yangi video faylini yuboring:",              "VIDEO"),
    "premium":     ("⭐ Premium holati", "",                                           "BOOL"),
}


def _edit_fields_kb(movie_id: int, is_movie: bool = True) -> InlineKeyboardMarkup:
    """Tahrirlash maydonlari tugmalari."""
    fields = [
        ("📝 Nomi (UZ)",    f"efield_{movie_id}_title_uz"),
        ("🌐 Nomi (RU)",    f"efield_{movie_id}_title_ru"),
        ("📄 Tavsif",       f"efield_{movie_id}_description"),
        ("🎭 Janr",         f"efield_{movie_id}_genres"),
        ("📅 Yil",          f"efield_{movie_id}_year"),
        ("🌍 Mamlakat",     f"efield_{movie_id}_country"),
        ("🖼 Poster",       f"efield_{movie_id}_poster"),
    ]
    if is_movie:
        fields.append(("🎬 Video",  f"efield_{movie_id}_file"))
    fields.append(("⭐ Premium", f"efield_{movie_id}_premium"))

    # 2 ustunli grid
    buttons = []
    row = []
    for label, cb in fields:
        row.append(InlineKeyboardButton(text=label, callback_data=cb))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="close_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _premium_choose_kb(movie_id: int, is_movie: bool) -> InlineKeyboardMarkup:
    ctype = "movie" if is_movie else "series"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Premium",   callback_data=f"eprem_{movie_id}_{ctype}_1"),
            InlineKeyboardButton(text="🆓 Tekin",     callback_data=f"eprem_{movie_id}_{ctype}_0"),
        ],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="close_admin_panel")],
    ])


# ══════════════════════════════════════════════════════════════════
#  TAHRIRLASH MENYUSINI CHIQARISH
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("full_edit_"), F.from_user.id.in_(ADMINS))
async def full_edit_menu(call: CallbackQuery):
    """admin.py → admin_movie_view → 'To'liq tahrirlash' tugmasi."""
    parts   = call.data.split("_")   # full_edit_{type}_{id}
    c_type  = parts[2]               # movie | series
    c_id    = int(parts[3])
    is_movie = c_type == "movie"
    table   = "movies" if is_movie else "series"

    async with get_db() as db:
        async with db.execute(
            f"SELECT title_uz, is_premium FROM {table} WHERE id = ?", (c_id,)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await call.answer("❌ Topilmadi!", show_alert=True)
        return

    title = row[0] or "Nomsiz"
    prem  = "⭐ Premium" if row[1] else "🆓 Tekin"
    icon  = "🎬" if is_movie else "📺"

    await call.message.edit_text(
        f"{icon} <b>{title}</b>\n"
        f"Status: {prem}\n\n"
        f"Tahrirlash uchun maydonni tanlang:",
        reply_markup=_edit_fields_kb(c_id, is_movie),
        parse_mode="HTML"
    )
    await call.answer()


# ══════════════════════════════════════════════════════════════════
#  MAYDONGA BOSISH → YANGI QIYMAT KUTISH
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("efield_"), F.from_user.id.in_(ADMINS))
async def efield_chosen(call: CallbackQuery, state: FSMContext):
    """Tahrirlash maydoniga bosildi."""
    parts    = call.data.split("_")   # efield_{id}_{field}
    c_id     = int(parts[1])
    field    = "_".join(parts[2:])    # title_uz, title_ru, yoki file, poster

    # Qaysi jadval — ID bo'yicha ikkalasini tekshiramiz
    async with get_db() as db:
        async with db.execute("SELECT 1 FROM movies WHERE id = ?", (c_id,)) as cur:
            is_movie = bool(await cur.fetchone())
    c_type = "movie" if is_movie else "series"
    table  = "movies" if is_movie else "series"

    # Premium — alohida tugmali menyu
    if field == "premium":
        await call.message.edit_text(
            "⭐ Premium holatini tanlang:",
            reply_markup=_premium_choose_kb(c_id, is_movie)
        )
        await call.answer()
        return

    meta = FIELD_META.get(field)
    if not meta:
        await call.answer("❌ Noma'lum maydon!", show_alert=True)
        return

    label, prompt, ftype = meta

    await state.update_data(c_id=c_id, field=field, ftype=ftype, table=table, is_movie=is_movie)
    await state.set_state(MovieEditState.waiting_value)

    await call.message.answer(
        f"✏️ <b>{label}</b> tahrirlash\n\n{prompt}",
        reply_markup=cancel_fsm_kb(),
        parse_mode="HTML"
    )
    await call.answer()


# ══════════════════════════════════════════════════════════════════
#  YANGI QIYMAT QABUL QILISH
# ══════════════════════════════════════════════════════════════════

@router.message(MovieEditState.waiting_value, F.from_user.id.in_(ADMINS))
async def efield_value_received(message: Message, state: FSMContext):
    data   = await state.get_data()
    c_id   = data["c_id"]
    field  = data["field"]
    ftype  = data["ftype"]
    table  = data["table"]

    # TEXT maydoni
    if ftype == "TEXT":
        if not message.text:
            await message.answer("❌ Matn yuboring!")
            return
        value = message.text.strip()
        if field == "genres":
            # Har qator alohida janr — vergul bilan birlashtirish
            lines = [l.strip() for l in message.text.splitlines() if l.strip()]
            value = ", ".join(lines)
        db_col = field
        async with get_db() as db:
            await db.execute(
                f"UPDATE {table} SET {db_col} = ? WHERE id = ?", (value, c_id)
            )
            # movies jadvalida title ustuni ham yangilansin
            if field == "title_uz" and table == "movies":
                await db.execute(
                    "UPDATE movies SET title = ? WHERE id = ?", (value, c_id)
                )
            await db.commit()
        await state.clear()
        await message.answer(
            f"✅ <b>{FIELD_META[field][0]}</b> yangilandi:\n<code>{value}</code>",
            parse_mode="HTML"
        )

    # INT maydoni
    elif ftype == "INT":
        if not message.text or not message.text.strip().isdigit():
            await message.answer("❌ Faqat raqam yuboring!")
            return
        value = int(message.text.strip())
        async with get_db() as db:
            await db.execute(
                f"UPDATE {table} SET {field} = ? WHERE id = ?", (value, c_id)
            )
            await db.commit()
        await state.clear()
        await message.answer(
            f"✅ <b>{FIELD_META[field][0]}</b> yangilandi: <code>{value}</code>",
            parse_mode="HTML"
        )

    # PHOTO (poster)
    elif ftype == "PHOTO":
        if not message.photo:
            await message.answer("❌ Rasm (foto) yuboring!")
            return
        file_id = message.photo[-1].file_id
        async with get_db() as db:
            await db.execute(
                f"UPDATE {table} SET poster_file_id = ? WHERE id = ?", (file_id, c_id)
            )
            await db.commit()
        await state.clear()
        await message.answer("✅ <b>Poster</b> yangilandi!", parse_mode="HTML")

    # VIDEO (film fayli)
    elif ftype == "VIDEO":
        if not message.video:
            await message.answer("❌ Video yuboring!")
            return
        file_id = message.video.file_id
        async with get_db() as db:
            await db.execute(
                "UPDATE movies SET file_id = ? WHERE id = ?", (file_id, c_id)
            )
            await db.commit()
        await state.clear()
        await message.answer("✅ <b>Video</b> yangilandi!", parse_mode="HTML")

    else:
        await state.clear()
        await message.answer("⚠️ Noma'lum maydon turi.")


# ══════════════════════════════════════════════════════════════════
#  PREMIUM HOLATI O'ZGARTIRISH
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("eprem_"), F.from_user.id.in_(ADMINS))
async def efield_premium_set(call: CallbackQuery):
    """eprem_{id}_{type}_{value}"""
    parts  = call.data.split("_")
    c_id   = int(parts[1])
    c_type = parts[2]
    value  = int(parts[3])
    table  = "movies" if c_type == "movie" else "series"

    async with get_db() as db:
        await db.execute(
            f"UPDATE {table} SET is_premium = ? WHERE id = ?", (value, c_id)
        )
        await db.commit()

    label = "⭐ Premium" if value else "🆓 Tekin"
    await call.message.edit_text(f"✅ Premium holati yangilandi: <b>{label}</b>", parse_mode="HTML")
    await call.answer()
