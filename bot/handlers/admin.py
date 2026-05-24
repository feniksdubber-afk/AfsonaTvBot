import csv
import io
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS
from bot.database.db import get_db
from bot.keyboards.admin_kb import (
    admin_menu, movie_manage_kb, edit_movie_kb,
    confirm_kb, user_manage_kb, requests_kb
)
from bot.keyboards.user_kb import main_menu

router = Router()

# ── Admin filter ───────────────────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

# ── FSM ────────────────────────────────────────────────
class AddMovieState(StatesGroup):
    code        = State()
    title       = State()
    title_ru    = State()
    description = State()
    genre       = State()
    year        = State()
    country     = State()
    is_premium  = State()
    is_series   = State()
    season      = State()
    episode     = State()
    poster      = State()
    video       = State()

class EditFieldState(StatesGroup):
    waiting = State()
    movie_id = State()
    field    = State()

class BroadcastState(StatesGroup):
    waiting = State()

class MsgUserState(StatesGroup):
    waiting = State()
    target  = State()

class GivePremiumState(StatesGroup):
    waiting = State()
    target  = State()

# ── Helpers ────────────────────────────────────────────
async def get_user_db(tg_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(zip([d[0] for d in cur.description], row))
    return None

# ── /admin ─────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "👑 <b>Admin panel</b>\nXush kelibsiz!",
        reply_markup=admin_menu(),
        parse_mode="HTML"
    )

# ── Bosh menyu ─────────────────────────────────────────
@router.message(F.text == "🏠 Bosh menyu")
async def back_home(message: Message):
    if not is_admin(message.from_user.id):
        return
    user = await get_user_db(message.from_user.id)
    lang = user["lang"] if user else "uz"
    await message.answer("🏠 Bosh menyu", reply_markup=main_menu(lang))


# ════════════════════════════════════════════════════════
#  🎬 KINO QO'SHISH
# ════════════════════════════════════════════════════════
@router.message(F.text == "🎬 Kino qo'shish")
async def add_movie_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🎬 <b>Yangi kino qo'shish</b>\n\nKino kodini kiriting (masalan: <code>AVATAR1</code>):", parse_mode="HTML")
    await state.set_state(AddMovieState.code)

@router.message(AddMovieState.code)
async def add_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    async with get_db() as db:
        async with db.execute("SELECT 1 FROM movies WHERE code = ?", (code,)) as cur:
            if await cur.fetchone():
                await message.answer(f"❌ <code>{code}</code> kodi allaqachon mavjud!", parse_mode="HTML")
                return
    await state.update_data(code=code)
    await message.answer("📝 Kino nomini kiriting (UZ):")
    await state.set_state(AddMovieState.title)

@router.message(AddMovieState.title)
async def add_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("🌐 Kino nomini kiriting (RU) yoki /skip:")
    await state.set_state(AddMovieState.title_ru)

@router.message(AddMovieState.title_ru)
async def add_title_ru(message: Message, state: FSMContext):
    val = None if message.text == "/skip" else message.text.strip()
    await state.update_data(title_ru=val)
    await message.answer("📄 Tavsif kiriting yoki /skip:")
    await state.set_state(AddMovieState.description)

@router.message(AddMovieState.description)
async def add_desc(message: Message, state: FSMContext):
    val = None if message.text == "/skip" else message.text.strip()
    await state.update_data(description=val)
    await message.answer("🎭 Janrni kiriting (masalan: Drama, Action) yoki /skip:")
    await state.set_state(AddMovieState.genre)

@router.message(AddMovieState.genre)
async def add_genre(message: Message, state: FSMContext):
    val = None if message.text == "/skip" else message.text.strip()
    await state.update_data(genre=val)
    await message.answer("📅 Yilni kiriting (masalan: 2024) yoki /skip:")
    await state.set_state(AddMovieState.year)

@router.message(AddMovieState.year)
async def add_year(message: Message, state: FSMContext):
    val = None
    if message.text != "/skip":
        try:
            val = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Faqat son kiriting!")
            return
    await state.update_data(year=val)
    await message.answer("🌍 Mamlakatni kiriting yoki /skip:")
    await state.set_state(AddMovieState.country)

@router.message(AddMovieState.country)
async def add_country(message: Message, state: FSMContext):
    val = None if message.text == "/skip" else message.text.strip()
    await state.update_data(country=val)
    await message.answer("⭐ Premium kinomi? (ha / yo'q):")
    await state.set_state(AddMovieState.is_premium)

@router.message(AddMovieState.is_premium)
async def add_premium(message: Message, state: FSMContext):
    val = 1 if message.text.lower() in ["ha", "yes", "1"] else 0
    await state.update_data(is_premium=val)
    await message.answer("📺 Serial yoki film? (serial / film):")
    await state.set_state(AddMovieState.is_series)

@router.message(AddMovieState.is_series)
async def add_is_series(message: Message, state: FSMContext):
    is_series = 1 if message.text.lower() in ["serial", "series", "1"] else 0
    await state.update_data(is_series=is_series)
    if is_series:
        await message.answer("📺 Mavsum raqamini kiriting:")
        await state.set_state(AddMovieState.season)
    else:
        await state.update_data(season=None, episode=None)
        await message.answer("🖼 Poster rasmini yuboring yoki /skip:")
        await state.set_state(AddMovieState.poster)

@router.message(AddMovieState.season)
async def add_season(message: Message, state: FSMContext):
    try:
        await state.update_data(season=int(message.text.strip()))
    except ValueError:
        await message.answer("❌ Son kiriting!")
        return
    await message.answer("🎬 Qism raqamini kiriting:")
    await state.set_state(AddMovieState.episode)

@router.message(AddMovieState.episode)
async def add_episode(message: Message, state: FSMContext):
    try:
        await state.update_data(episode=int(message.text.strip()))
    except ValueError:
        await message.answer("❌ Son kiriting!")
        return
    await message.answer("🖼 Poster rasmini yuboring yoki /skip:")
    await state.set_state(AddMovieState.poster)

@router.message(AddMovieState.poster)
async def add_poster(message: Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(poster_id=None)
    elif message.photo:
        await state.update_data(poster_id=message.photo[-1].file_id)
    else:
        await message.answer("🖼 Rasm yuboring yoki /skip:")
        return
    await message.answer("🎬 Videoni yuboring yoki /skip:")
    await state.set_state(AddMovieState.video)

@router.message(AddMovieState.video)
async def add_video(message: Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(file_id=None)
    elif message.video:
        await state.update_data(file_id=message.video.file_id)
    elif message.document:
        await state.update_data(file_id=message.document.file_id)
    else:
        await message.answer("🎬 Video yuboring yoki /skip:")
        return

    # Saqlash
    data = await state.get_data()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO movies
               (code, title, title_ru, description, genre, year, country,
                is_premium, is_series, season, episode, poster_id, file_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["code"], data["title"], data.get("title_ru"),
                data.get("description"), data.get("genre"), data.get("year"),
                data.get("country"), data.get("is_premium", 0),
                data.get("is_series", 0), data.get("season"), data.get("episode"),
                data.get("poster_id"), data.get("file_id")
            )
        )
        await db.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>{data['title']}</b> kinosi qo'shildi!\n"
        f"📌 Kod: <code>{data['code']}</code>",
        reply_markup=admin_menu(),
        parse_mode="HTML"
    )


# ════════════════════════════════════════════════════════
#  📋 KINOLAR RO'YXATI
# ════════════════════════════════════════════════════════
@router.message(F.text == "📋 Kinolar ro'yxati")
async def list_movies(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with get_db() as db:
        async with db.execute(
            "SELECT id, code, title, is_premium, status, views FROM movies ORDER BY id DESC LIMIT 20"
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await message.answer("🎬 Kinolar yo'q.")
        return

    lines = []
    for r in rows:
        status_icon = "✅" if r[4] == "active" else "🔒"
        premium_icon = "⭐" if r[3] else "🎬"
        lines.append(f"{status_icon}{premium_icon} <code>{r[1]}</code> — {r[2]} 👁{r[5]}")

    await message.answer(
        "📋 <b>So'nggi 20 kino:</b>\n\n" + "\n".join(lines) +
        "\n\n📌 Kod yuboring — boshqarish uchun",
        parse_mode="HTML"
    )


# ── Kod orqali admin boshqaruvi ────────────────────────
@router.message(F.text.regexp(r'^[A-Z0-9]{3,10}$') & F.from_user.func(lambda u: u.id in ADMINS))
async def admin_movie_detail(message: Message):
    code = message.text.strip().upper()
    async with get_db() as db:
        async with db.execute("SELECT * FROM movies WHERE code = ?", (code,)) as cur:
            row = await cur.fetchone()
            if not row:
                return
            movie = dict(zip([d[0] for d in cur.description], row))

    text = (
        f"🎬 <b>{movie['title']}</b>\n"
        f"📌 Kod: <code>{movie['code']}</code>\n"
        f"🎭 Janr: {movie.get('genre','—')}\n"
        f"📅 Yil: {movie.get('year','—')}\n"
        f"⭐ Premium: {'Ha' if movie['is_premium'] else 'Yo\'q'}\n"
        f"📺 Serial: {'Ha' if movie['is_series'] else 'Yo\'q'}\n"
        f"👁 Ko'rishlar: {movie['views']}\n"
        f"📊 Holat: {movie['status']}"
    )
    await message.answer(text, reply_markup=movie_manage_kb(movie["id"]), parse_mode="HTML")


# ── Tahrirlash ─────────────────────────────────────────
@router.callback_query(F.data.startswith("edit_movie_"))
async def edit_movie(call: CallbackQuery):
    movie_id = int(call.data.split("_")[2])
    await call.message.edit_text(
        "✏️ <b>Qaysi maydonni tahrirlash?</b>",
        reply_markup=edit_movie_kb(movie_id),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("efield_"))
async def edit_field_start(call: CallbackQuery, state: FSMContext):
    _, movie_id, field = call.data.split("_", 2)
    await state.update_data(movie_id=int(movie_id), field=field)

    prompts = {
        "title":       "📝 Yangi nom (UZ):",
        "title_ru":    "🌐 Yangi nom (RU):",
        "description": "📄 Yangi tavsif:",
        "genre":       "🎭 Yangi janr:",
        "year":        "📅 Yangi yil:",
        "country":     "🌍 Yangi mamlakat:",
        "poster":      "🖼 Yangi poster rasmini yuboring:",
        "file":        "🎬 Yangi videoni yuboring:",
        "premium":     "⭐ Premium? (ha / yo'q):",
    }
    await call.message.answer(prompts.get(field, "Yangi qiymat:"))
    await state.set_state(EditFieldState.waiting)
    await call.answer()

@router.message(EditFieldState.waiting)
async def edit_field_save(message: Message, state: FSMContext):
    data = await state.get_data()
    movie_id = data["movie_id"]
    field = data["field"]

    if field == "poster":
        if not message.photo:
            await message.answer("🖼 Rasm yuboring!")
            return
        value = message.photo[-1].file_id
        db_field = "poster_id"
    elif field == "file":
        if message.video:
            value = message.video.file_id
        elif message.document:
            value = message.document.file_id
        else:
            await message.answer("🎬 Video yuboring!")
            return
        db_field = "file_id"
    elif field == "premium":
        value = 1 if message.text.lower() in ["ha", "yes", "1"] else 0
        db_field = "is_premium"
    elif field == "year":
        try:
            value = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Son kiriting!")
            return
        db_field = "year"
    else:
        value = message.text.strip()
        db_field = field

    async with get_db() as db:
        await db.execute(
            f"UPDATE movies SET {db_field} = ? WHERE id = ?", (value, movie_id)
        )
        await db.commit()

    await state.clear()
    await message.answer("✅ Yangilandi!", reply_markup=admin_menu())


# ── O'chirish ──────────────────────────────────────────
@router.callback_query(F.data.startswith("del_movie_"))
async def del_movie_confirm(call: CallbackQuery):
    movie_id = int(call.data.split("_")[2])
    await call.message.edit_text(
        "🗑 Kinoni o'chirishni tasdiqlaysizmi?",
        reply_markup=confirm_kb(f"confirm_del_{movie_id}", f"admin_movie_{movie_id}")
    )

@router.callback_query(F.data.startswith("confirm_del_"))
async def del_movie_execute(call: CallbackQuery):
    movie_id = int(call.data.split("_")[2])
    async with get_db() as db:
        await db.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
        await db.commit()
    await call.message.edit_text("✅ Kino o'chirildi!")

@router.callback_query(F.data.startswith("deactivate_"))
async def deactivate_movie(call: CallbackQuery):
    movie_id = int(call.data.split("_")[1])
    async with get_db() as db:
        await db.execute("UPDATE movies SET status = 'inactive' WHERE id = ?", (movie_id,))
        await db.commit()
    await call.answer("🔒 Faolsizlashtirildi!", show_alert=True)

@router.callback_query(F.data.startswith("activate_"))
async def activate_movie(call: CallbackQuery):
    movie_id = int(call.data.split("_")[1])
    async with get_db() as db:
        await db.execute("UPDATE movies SET status = 'active' WHERE id = ?", (movie_id,))
        await db.commit()
    await call.answer("✅ Faollashtirildi!", show_alert=True)


# ════════════════════════════════════════════════════════
#  📢 BROADCAST
# ════════════════════════════════════════════════════════
@router.message(F.text == "📢 Broadcast")
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("📢 Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:")
    await state.set_state(BroadcastState.waiting)

@router.message(BroadcastState.waiting)
async def broadcast_send(message: Message, state: FSMContext):
    await state.clear()

    async with get_db() as db:
        async with db.execute("SELECT tg_id FROM users WHERE is_banned = 0") as cur:
            users = await cur.fetchall()

    success, failed = 0, 0
    for (tg_id,) in users:
        try:
            if message.photo:
                await message.bot.send_photo(
                    tg_id, message.photo[-1].file_id,
                    caption=message.caption or ""
                )
            elif message.video:
                await message.bot.send_video(
                    tg_id, message.video.file_id,
                    caption=message.caption or ""
                )
            else:
                await message.bot.send_message(tg_id, message.text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1

    await message.answer(
        f"📢 <b>Broadcast yakunlandi!</b>\n\n"
        f"✅ Yuborildi: {success}\n"
        f"❌ Xato: {failed}",
        reply_markup=admin_menu(),
        parse_mode="HTML"
    )


# ════════════════════════════════════════════════════════
#  👥 FOYDALANUVCHILAR
# ════════════════════════════════════════════════════════
@router.message(F.text == "👥 Foydalanuvchilar")
async def list_users(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "👥 Foydalanuvchi ID yoki username kiriting:\n"
        "(masalan: <code>123456789</code> yoki <code>@username</code>)",
        parse_mode="HTML"
    )

@router.message(F.text.startswith("@") | F.text.regexp(r'^\d{5,}$') &
                F.from_user.func(lambda u: u.id in ADMINS))
async def find_user(message: Message):
    query = message.text.strip()
    async with get_db() as db:
        if query.startswith("@"):
            uname = query[1:]
            async with db.execute("SELECT * FROM users WHERE username = ?", (uname,)) as cur:
                row = await cur.fetchone()
                cols = [d[0] for d in cur.description]
        else:
            async with db.execute("SELECT * FROM users WHERE tg_id = ?", (int(query),)) as cur:
                row = await cur.fetchone()
                cols = [d[0] for d in cur.description]

    if not row:
        await message.answer("❌ Foydalanuvchi topilmadi.")
        return

    user = dict(zip(cols, row))
    text = (
        f"👤 <b>Foydalanuvchi</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👤 Ism: {user['full_name']}\n"
        f"📛 Username: @{user.get('username','—')}\n"
        f"🌐 Til: {user['lang']}\n"
        f"⭐ Premium: {'Ha' if user['is_premium'] else 'Yo\'q'}\n"
        f"🚫 Ban: {'Ha' if user['is_banned'] else 'Yo\'q'}\n"
        f"💰 Balans: {user['balance']}\n"
        f"📅 Ro'yxatdan: {user['created_at'][:10]}"
    )
    await message.answer(text, reply_markup=user_manage_kb(user["tg_id"], user["is_banned"]), parse_mode="HTML")


# ── Ban / Unban ────────────────────────────────────────
@router.callback_query(F.data.startswith("ban_"))
async def ban_user(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])
    async with get_db() as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE tg_id = ?", (user_id,))
        await db.commit()
    await call.answer("🚫 Foydalanuvchi banlandi!", show_alert=True)
    await call.message.edit_reply_markup(reply_markup=user_manage_kb(user_id, 1))

@router.callback_query(F.data.startswith("unban_"))
async def unban_user(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])
    async with get_db() as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE tg_id = ?", (user_id,))
        await db.commit()
    await call.answer("✅ Ban olib tashlandi!", show_alert=True)
    await call.message.edit_reply_markup(reply_markup=user_manage_kb(user_id, 0))


# ── Shaxsiy xabar ──────────────────────────────────────
@router.callback_query(F.data.startswith("msg_user_"))
async def msg_user_start(call: CallbackQuery, state: FSMContext):
    user_id = int(call.data.split("_")[2])
    await state.update_data(target=user_id)
    await state.set_state(MsgUserState.waiting)
    await call.message.answer(f"💬 <code>{user_id}</code> ga yuboriladigan xabarni kiriting:", parse_mode="HTML")
    await call.answer()

@router.message(MsgUserState.waiting)
async def msg_user_send(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data["target"]
    try:
        await message.bot.send_message(target, f"📩 Admin xabari:\n\n{message.text}", parse_mode="HTML")
        await message.answer("✅ Xabar yuborildi!", reply_markup=admin_menu())
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}", reply_markup=admin_menu())
    await state.clear()


# ── Premium berish ─────────────────────────────────────
@router.callback_query(F.data.startswith("give_premium_"))
async def give_premium_start(call: CallbackQuery, state: FSMContext):
    user_id = int(call.data.split("_")[2])
    await state.update_data(target=user_id)
    await state.set_state(GivePremiumState.waiting)
    await call.message.answer("⭐ Necha kun premium berish? (masalan: 30):")
    await call.answer()

@router.message(GivePremiumState.waiting)
async def give_premium_save(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data["target"]
    try:
        days = int(message.text.strip())
        until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        async with get_db() as db:
            await db.execute(
                "UPDATE users SET is_premium = 1, premium_until = ? WHERE tg_id = ?",
                (until, target)
            )
            await db.commit()
        await message.bot.send_message(
            target,
            f"🎉 Sizga <b>{days} kunlik Premium</b> berildi!\n"
            f"Amal qilish muddati: <b>{until}</b>",
            parse_mode="HTML"
        )
        await message.answer(f"✅ {target} ga {days} kunlik premium berildi!", reply_markup=admin_menu())
    except ValueError:
        await message.answer("❌ Son kiriting!")
        return
    await state.clear()


# ════════════════════════════════════════════════════════
#  📊 STATISTIKA
# ════════════════════════════════════════════════════════
@router.message(F.text == "📊 Statistika")
async def show_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as cur:
            premium_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1") as cur:
            banned_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM movies WHERE status = 'active'") as cur:
            total_movies = (await cur.fetchone())[0]
        async with db.execute("SELECT SUM(views) FROM movies") as cur:
            total_views = (await cur.fetchone())[0] or 0
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')"
        ) as cur:
            today_users = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM watch_history WHERE date(watched_at) = date('now')"
        ) as cur:
            today_views = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT title, views FROM movies ORDER BY views DESC LIMIT 5"
        ) as cur:
            top_movies = await cur.fetchall()

    top_lines = "\n".join([f"  {i+1}. {r[0]} — {r[1]:,}" for i, r in enumerate(top_movies)])

    await message.answer(
        f"📊 <b>Bot statistikasi</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users:,}</b>\n"
        f"⭐ Premium: <b>{premium_users}</b>\n"
        f"🚫 Banlangan: <b>{banned_users}</b>\n"
        f"📅 Bugun qo'shildi: <b>{today_users}</b>\n\n"
        f"🎬 Jami kinolar: <b>{total_movies}</b>\n"
        f"👁 Jami ko'rishlar: <b>{total_views:,}</b>\n"
        f"📅 Bugun ko'rishlar: <b>{today_views}</b>\n\n"
        f"🏆 <b>TOP 5 kino:</b>\n{top_lines}",
        parse_mode="HTML"
    )


# ════════════════════════════════════════════════════════
#  📥 EKSPORT CSV
# ════════════════════════════════════════════════════════
@router.message(F.text == "📥 Eksport CSV")
async def export_csv(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with get_db() as db:
        async with db.execute(
            "SELECT tg_id, full_name, username, lang, is_premium, balance, created_at FROM users"
        ) as cur:
            rows = await cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Ism", "Username", "Til", "Premium", "Balans", "Sana"])
    writer.writerows(rows)

    file_bytes = output.getvalue().encode("utf-8-sig")
    file = BufferedInputFile(file_bytes, filename="users.csv")
    await message.answer_document(file, caption=f"📥 Jami: {len(rows)} foydalanuvchi")


# ════════════════════════════════════════════════════════
#  📨 KINO SO'ROVLAR
# ════════════════════════════════════════════════════════
@router.message(F.text == "📨 Kino so'rovlar")
async def movie_requests(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with get_db() as db:
        async with db.execute(
            """SELECT r.id, r.text, r.created_at, u.full_name, u.tg_id
               FROM movie_requests r JOIN users u ON r.user_id = u.tg_id
               WHERE r.status = 'pending'
               ORDER BY r.created_at DESC LIMIT 10"""
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await message.answer("📨 Yangi so'rovlar yo'q.")
        return

    for r in rows:
        text = (
            f"📨 <b>So'rov #{r[0]}</b>\n"
            f"👤 {r[3]} (<code>{r[4]}</code>)\n"
            f"📅 {r[2][:10]}\n\n"
            f"💬 {r[1]}"
        )
        await message.answer(text, reply_markup=requests_kb(r[0]), parse_mode="HTML")

@router.callback_query(F.data.startswith("req_accept_"))
async def req_accept(call: CallbackQuery):
    req_id = int(call.data.split("_")[2])
    async with get_db() as db:
        await db.execute(
            "UPDATE movie_requests SET status = 'accepted' WHERE id = ?", (req_id,)
        )
        async with db.execute(
            "SELECT user_id FROM movie_requests WHERE id = ?", (req_id,)
        ) as cur:
            row = await cur.fetchone()
        await db.commit()

    if row:
        try:
            await call.bot.send_message(
                row[0], "✅ So'rovingiz qabul qilindi! Tez orada qo'shamiz."
            )
        except Exception:
            pass

    await call.message.edit_text("✅ So'rov qabul qilindi!")

@router.callback_query(F.data.startswith("req_reject_"))
async def req_reject(call: CallbackQuery):
    req_id = int(call.data.split("_")[2])
    async with get_db() as db:
        await db.execute(
            "UPDATE movie_requests SET status = 'rejected' WHERE id = ?", (req_id,)
        )
        async with db.execute(
            "SELECT user_id FROM movie_requests WHERE id = ?", (req_id,)
        ) as cur:
            row = await cur.fetchone()
        await db.commit()

    if row:
        try:
            await call.bot.send_message(
                row[0], "❌ Afsuski, so'rovingiz rad etildi."
            )
        except Exception:
            pass

    await call.message.edit_text("❌ So'rov rad etildi!")
