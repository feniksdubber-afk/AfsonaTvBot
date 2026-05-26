"""
franchise.py  (#3)
──────────────────
Film franshizasi (Part 1, 2, 3…) va serialga qism/fasl qo'shish.

A. Film franshizasi:
   - Admin mavjud filmga yangi qism qo'sha oladi (movie_parts jadvalida)
   - Foydalanuvchi kino kodini yuborganda franshiza bo'lsa inline tugmalar chiqadi

B. Serialga qism/fasl qo'shish:
   - Mavjud serialga yangi fasl yoki qism qo'shish
   - Admin serial kodini yuborganda "➕ Qism qo'shish" tugmasi chiqadi

Bu modul admin.py dagi asosiy flow ni buzmasdan ishlaydi.
"""

import logging

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS, CHANNEL_PRIVATE
from bot.database.db import get_db
from bot.utils.admin_tools import generate_unique_code
from bot.utils.helpers import get_protect_setting
from bot.keyboards.admin_kb import cancel_fsm_kb, series_control_kb

logger = logging.getLogger(__name__)
router = Router()


def _txt(uz: str, ru: str, lang: str) -> str:
    return uz if lang == "uz" else ru


async def _get_lang(tg_id: int) -> str:
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT lang FROM users WHERE tg_id = ?", (tg_id,)
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else "uz"
    except Exception:
        return "uz"


# ══════════════════════════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════════════════════════

class FranchiseAddState(StatesGroup):
    """Admin mavjud filmga yangi qism qo'shadi."""
    waiting_movie_code = State()   # qaysi filmga qo'shish
    waiting_part_num   = State()   # qism raqami (1, 2, 3…)
    waiting_titles     = State()   # nomi uz\nru
    waiting_video      = State()   # video fayli


class SeriesAddEpisodeState(StatesGroup):
    """Admin mavjud serialga yangi qism/fasl qo'shadi."""
    waiting_series_code = State()   # qaysi serialga
    waiting_season      = State()   # qaysi faslga (raqam yoki "new")
    waiting_episodes    = State()   # videolarni qabul qilish


# ══════════════════════════════════════════════════════════════════
#  A. FILM FRANSHIZASI — ADMIN TOMONIDAN QO'SHISH
# ══════════════════════════════════════════════════════════════════

@router.message(F.text == "🎞 Franshizaga qism qo'shish", F.from_user.id.in_(ADMINS))
async def franchise_add_start(message: Message, state: FSMContext):
    await state.set_state(FranchiseAddState.waiting_movie_code)
    await message.answer(
        "🎞 <b>Film franshizasiga yangi qism qo'shish</b>\n\n"
        "Asosiy filmning kodini yuboring (3-5 raqam):",
        reply_markup=cancel_fsm_kb(),
        parse_mode="HTML"
    )


@router.message(FranchiseAddState.waiting_movie_code, F.text, F.from_user.id.in_(ADMINS))
async def franchise_movie_code(message: Message, state: FSMContext):
    code = (message.text or "").strip()

    async with get_db() as db:
        async with db.execute(
            "SELECT id, title_uz, status FROM movies WHERE code = ?", (code,)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await message.answer(
            "❌ Bu kod bilan film topilmadi! Qaytadan kiriting:",
            reply_markup=cancel_fsm_kb()
        )
        return

    if row[2] == "deleted":
        await message.answer("❌ Bu film o'chirilgan!")
        await state.clear()
        return

    await state.update_data(movie_id=row[0], movie_title=row[1])
    await state.set_state(FranchiseAddState.waiting_part_num)

    # Mavjud qismlarni ko'rsatish
    async with get_db() as db:
        async with db.execute(
            "SELECT part_num, title_uz FROM movie_parts WHERE movie_id = ? ORDER BY part_num",
            (row[0],)
        ) as cur:
            parts = await cur.fetchall()

    parts_text = ""
    if parts:
        parts_text = "\n\n📋 Mavjud qismlar:\n" + "\n".join(
            f"  {p[0]}-qism: {p[1] or '—'}" for p in parts
        )

    await message.answer(
        f"✅ Film topildi: <b>{row[1]}</b>{parts_text}\n\n"
        f"📝 Yangi qismning raqamini yuboring (masalan: <code>2</code>):",
        reply_markup=cancel_fsm_kb(),
        parse_mode="HTML"
    )


@router.message(FranchiseAddState.waiting_part_num, F.text, F.from_user.id.in_(ADMINS))
async def franchise_part_num(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) < 1:
        await message.answer("❌ Faqat musbat raqam kiriting (1, 2, 3…):")
        return

    part_num = int(text)
    data = await state.get_data()

    # Mavjud qism tekshiruvi
    async with get_db() as db:
        async with db.execute(
            "SELECT 1 FROM movie_parts WHERE movie_id = ? AND part_num = ?",
            (data["movie_id"], part_num)
        ) as cur:
            exists = await cur.fetchone()

    if exists:
        await message.answer(
            f"⚠️ {part_num}-qism allaqachon mavjud! Boshqa raqam kiriting:",
            reply_markup=cancel_fsm_kb()
        )
        return

    await state.update_data(part_num=part_num)
    await state.set_state(FranchiseAddState.waiting_titles)
    await message.answer(
        f"📝 {part_num}-qismning nomini yuboring:\n"
        f"1-qator: O'zbekcha\n2-qator: Ruscha\n\n"
        f"Misol:\n<code>Avengers: Infinity War\nМстители: Война бесконечности</code>",
        reply_markup=cancel_fsm_kb(),
        parse_mode="HTML"
    )


@router.message(FranchiseAddState.waiting_titles, F.text, F.from_user.id.in_(ADMINS))
async def franchise_titles(message: Message, state: FSMContext):
    lines = (message.text or "").splitlines()
    if len(lines) < 2:
        await message.answer("❌ 2 qatorda yuboring (UZ va RU):")
        return

    await state.update_data(title_uz=lines[0].strip(), title_ru=lines[1].strip())
    await state.set_state(FranchiseAddState.waiting_video)
    data = await state.get_data()
    await message.answer(
        f"🎬 {data['part_num']}-qism videosini yuboring:",
        reply_markup=cancel_fsm_kb()
    )


@router.message(FranchiseAddState.waiting_video, F.video, F.from_user.id.in_(ADMINS))
async def franchise_video(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    async with get_db() as db:
        try:
            await db.execute(
                """INSERT INTO movie_parts (movie_id, part_num, title_uz, title_ru, file_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (data["movie_id"], data["part_num"],
                 data["title_uz"], data["title_ru"],
                 message.video.file_id)
            )
            await db.commit()
        except Exception as e:
            await message.answer(f"❌ Saqlashda xato: {e}")
            return

    # Backup
    try:
        await bot.send_video(
            chat_id=CHANNEL_PRIVATE,
            video=message.video.file_id,
            caption=(
                f"📦 BACKUP | FRANSHIZA\n"
                f"🎬 Film: {data['movie_title']}\n"
                f"🔢 {data['part_num']}-qism: {data['title_uz']}"
            )
        )
    except Exception:
        pass

    await message.answer(
        f"✅ <b>{data['part_num']}-qism muvaffaqiyatli saqlandi!</b>\n"
        f"🎬 {data['title_uz']}",
        parse_mode="HTML"
    )

    # Franshiza kino sevimlilarida bor userlarga bildirishnoma
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT user_id FROM favorites WHERE movie_id = ?", (data["movie_id"],)
            ) as cur:
                fav_users = await cur.fetchall()
        for (uid,) in fav_users:
            try:
                await bot.send_message(
                    uid,
                    f"🎬 <b>{data['movie_title']}</b> filmiga yangi qism qo'shildi!\n\n"
                    f"📽 {data['part_num']}-qism: <b>{data['title_uz']}</b>\n\n"
                    f"Tomosha qilish uchun filmni oching.",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning("Franshiza bildirishnomasi xatosi: %s", e)



# ══════════════════════════════════════════════════════════════════
#  A2. INLINE TUGMALAR ORQALI QO'SHISH (admin_content_list dan)
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("add_franchise_part_"), F.from_user.id.in_(ADMINS))
async def cb_add_franchise_part(call: CallbackQuery, state: FSMContext):
    """'🎞 Franshiza qism qo'shish' tugmasi bosilganda — movie_id oldindan ma'lum."""
    movie_id = int(call.data.split("_")[-1])

    async with get_db() as db:
        async with db.execute(
            "SELECT title_uz, status, code FROM movies WHERE id = ?", (movie_id,)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await call.answer("❌ Film topilmadi!", show_alert=True)
        return
    if row[1] == "deleted":
        await call.answer("❌ Film o'chirilgan!", show_alert=True)
        return

    # Mavjud qismlar
    async with get_db() as db:
        async with db.execute(
            "SELECT part_num, title_uz FROM movie_parts WHERE movie_id = ? ORDER BY part_num",
            (movie_id,)
        ) as cur:
            parts = await cur.fetchall()

    parts_text = ""
    if parts:
        parts_text = "\n\n📋 Mavjud qismlar:\n" + "\n".join(
            f"  {p[0]}-qism: {p[1] or '—'}" for p in parts
        )

    await state.update_data(movie_id=movie_id, movie_title=row[0])
    await state.set_state(FranchiseAddState.waiting_part_num)

    await call.message.answer(
        f"🎞 <b>Franshizaga qism qo'shish</b>\n"
        f"🎬 Film: <b>{row[0]}</b> (kod: <code>{row[2]}</code>){parts_text}\n\n"
        f"📝 Yangi qismning raqamini yuboring (masalan: <code>2</code>):",
        reply_markup=cancel_fsm_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("add_series_episode_"), F.from_user.id.in_(ADMINS))
async def cb_add_series_episode(call: CallbackQuery, state: FSMContext):
    """'📺 Qism qo'shish' tugmasi bosilganda — series_id oldindan ma'lum."""
    series_id = int(call.data.split("_")[-1])

    async with get_db() as db:
        async with db.execute(
            "SELECT title_uz, status, code FROM series WHERE id = ?", (series_id,)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await call.answer("❌ Serial topilmadi!", show_alert=True)
        return
    if row[1] == "deleted":
        await call.answer("❌ Serial o'chirilgan!", show_alert=True)
        return

    async with get_db() as db:
        async with db.execute(
            "SELECT season_number FROM seasons WHERE series_id = ? ORDER BY season_number",
            (series_id,)
        ) as cur:
            seasons = await cur.fetchall()

    await state.update_data(
        series_id=series_id,
        series_title=row[0],
        series_code=row[2]
    )
    await state.set_state(SeriesAddEpisodeState.waiting_season)

    seasons_text = "📋 Mavjud fasllar: " + ", ".join(str(s[0]) for s in seasons) if seasons else "📋 Hali fasl yo'q"
    next_season = (seasons[-1][0] + 1) if seasons else 1

    kb = InlineKeyboardMarkup(inline_keyboard=[
        *[
            [InlineKeyboardButton(
                text=f"📀 {s[0]}-Faslga qo'shish",
                callback_data=f"sae_season_{series_id}_{s[0]}"
            )]
            for s in seasons
        ],
        [InlineKeyboardButton(
            text=f"➕ Yangi {next_season}-fasl ochish",
            callback_data=f"sae_season_{series_id}_{next_season}_new"
        )],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_admin_fsm")],
    ])

    await call.message.answer(
        f"📺 <b>Serialga qism qo'shish</b>\n"
        f"📺 Serial: <b>{row[0]}</b> (kod: <code>{row[2]}</code>)\n"
        f"{seasons_text}\n\n"
        f"Qaysi faslga qism qo'shmoqchisiz?",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await call.answer()


# ══════════════════════════════════════════════════════════════════
#  B. SERIALGA QISM/FASL QO'SHISH — ADMIN
# ══════════════════════════════════════════════════════════════════

@router.message(F.text == "📺 Serialga qism qo'shish", F.from_user.id.in_(ADMINS))
async def series_add_ep_start(message: Message, state: FSMContext):
    await state.set_state(SeriesAddEpisodeState.waiting_series_code)
    await message.answer(
        "📺 <b>Mavjud serialga qism qo'shish</b>\n\n"
        "Serial kodini yuboring:",
        reply_markup=cancel_fsm_kb(),
        parse_mode="HTML"
    )


@router.message(SeriesAddEpisodeState.waiting_series_code, F.text, F.from_user.id.in_(ADMINS))
async def series_add_ep_code(message: Message, state: FSMContext):
    code = (message.text or "").strip()

    async with get_db() as db:
        async with db.execute(
            "SELECT id, title_uz, status FROM series WHERE code = ?", (code,)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            await message.answer("❌ Serial topilmadi! Kodni qayta kiriting:", reply_markup=cancel_fsm_kb())
            return

        if row[2] == "deleted":
            await message.answer("❌ Bu serial o'chirilgan!")
            await state.clear()
            return

        series_id = row[0]

        async with db.execute(
            "SELECT season_number FROM seasons WHERE series_id = ? ORDER BY season_number",
            (series_id,)
        ) as cur:
            seasons = await cur.fetchall()

    await state.update_data(
        series_id=series_id,
        series_title=row[1],
        series_code=code
    )

    seasons_text = ""
    if seasons:
        seasons_text = "📋 Mavjud fasllar: " + ", ".join(str(s[0]) for s in seasons)
    else:
        seasons_text = "📋 Hali fasl yo'q"

    await state.set_state(SeriesAddEpisodeState.waiting_season)

    next_season = (seasons[-1][0] + 1) if seasons else 1
    kb = InlineKeyboardMarkup(inline_keyboard=[
        *[
            [InlineKeyboardButton(
                text=f"📀 {s[0]}-Faslga qo'shish",
                callback_data=f"sae_season_{series_id}_{s[0]}"
            )]
            for s in seasons
        ],
        [InlineKeyboardButton(
            text=f"➕ Yangi {next_season}-fasl ochish",
            callback_data=f"sae_season_{series_id}_{next_season}_new"
        )],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_admin_fsm")],
    ])

    await message.answer(
        f"✅ Serial: <b>{row[1]}</b>\n{seasons_text}\n\n"
        f"Qaysi faslga qism qo'shmoqchisiz?",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(
    F.data.startswith("sae_season_"),
    F.from_user.id.in_(ADMINS)
)
async def series_add_ep_season_chosen(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    # sae_season_{series_id}_{season_num} yoki sae_season_{series_id}_{season_num}_new
    series_id  = int(parts[2])
    season_num = int(parts[3])
    is_new     = len(parts) > 4 and parts[4] == "new"

    data = await state.get_data()

    if is_new:
        async with get_db() as db:
            await db.execute(
                "INSERT OR IGNORE INTO seasons (series_id, season_number) VALUES (?, ?)",
                (series_id, season_num)
            )
            await db.commit()

    await state.update_data(current_season=season_num)
    await state.set_state(SeriesAddEpisodeState.waiting_episodes)

    prefix = "Yangi " if is_new else ""
    await call.message.edit_text(
        f"📀 <b>{prefix}{season_num}-Fasl</b> — Videolarni yuboring\n\n"
        f"📺 Serial: {data.get('series_title', '')}\n\n"
        f"⚠️ Videoning <b>caption</b> qismiga faqat qism raqamini yozing:\n"
        f"Misol caption: <code>5</code>  (5-qism uchun)\n\n"
        f"Bir nechta qism yuborishingiz mumkin.",
        reply_markup=_sae_control_kb(),
        parse_mode="HTML"
    )
    await call.answer()


def _sae_control_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yakunlash", callback_data="sae_finish")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_admin_fsm")],
    ])


@router.message(SeriesAddEpisodeState.waiting_episodes, F.video, F.from_user.id.in_(ADMINS))
async def series_add_ep_video(message: Message, state: FSMContext, bot: Bot):
    caption = (message.caption or "").strip()
    if not caption.isdigit():
        await message.answer(
            "❌ Captionni faqat raqam qiling (qism raqami)!\n"
            "Masalan: videoning captioniga faqat <code>5</code> yozing.",
            parse_mode="HTML",
            reply_markup=_sae_control_kb()
        )
        return

    ep_num = int(caption)
    data = await state.get_data()
    series_id = data["series_id"]
    season    = data["current_season"]

    async with get_db() as db:
        try:
            await db.execute(
                """INSERT INTO episodes (series_id, season_number, episode_number, file_id)
                   VALUES (?, ?, ?, ?)""",
                (series_id, season, ep_num, message.video.file_id)
            )
            await db.commit()
        except Exception:
            await message.answer(
                f"⚠️ {season}-fasl {ep_num}-qism allaqachon mavjud!",
                reply_markup=_sae_control_kb()
            )
            return

    try:
        await bot.send_video(
            chat_id=CHANNEL_PRIVATE,
            video=message.video.file_id,
            caption=(
                f"📦 BACKUP | SERIAL (qo'shimcha)\n"
                f"📺 {data.get('series_title', '')}\n"
                f"📀 {season}-fasl {ep_num}-qism"
            )
        )
    except Exception:
        pass

    await message.answer(
        f"✅ {season}-fasl {ep_num}-qism saqlandi!",
        reply_markup=_sae_control_kb()
    )

    # Serial sevimlilarida bor userlarga bildirishnoma
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT user_id FROM favorites WHERE series_id = ?", (series_id,)
            ) as cur:
                fav_users = await cur.fetchall()
        series_title = data.get("series_title", "")
        for (uid,) in fav_users:
            try:
                await bot.send_message(
                    uid,
                    f"📺 <b>{series_title}</b> serialiga yangi qism qo'shildi!\n\n"
                    f"📀 {season}-fasl, {ep_num}-qism\n\n"
                    f"Tomosha qilish uchun serialingizni oching.",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning("Serial bildirishnomasi xatosi: %s", e)


@router.callback_query(F.data == "sae_finish", F.from_user.id.in_(ADMINS))
async def series_add_ep_finish(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    # Jami qismlar sonini hisoblash
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM episodes WHERE series_id = ?",
            (data.get("series_id", 0),)
        ) as cur:
            total = (await cur.fetchone())[0]

    await call.message.edit_text(
        f"✅ <b>Muvaffaqiyatli yakunlandi!</b>\n\n"
        f"📺 Serial: {data.get('series_title', '')}\n"
        f"📊 Jami qismlar soni: {total} ta",
        parse_mode="HTML"
    )
    await call.answer()


# ══════════════════════════════════════════════════════════════════
#  FOYDALANUVCHI TOMONIDAN — FRANSHIZA TUGMALARI
# ══════════════════════════════════════════════════════════════════

async def get_movie_parts(movie_id: int) -> list:
    """Filmning barcha qismlarini qaytaradi."""
    async with get_db() as db:
        async with db.execute(
            """SELECT part_num, title_uz, title_ru, file_id
               FROM movie_parts WHERE movie_id = ? ORDER BY part_num""",
            (movie_id,)
        ) as cur:
            return await cur.fetchall()


def franchise_parts_kb(movie_id: int, parts: list, lang: str) -> InlineKeyboardMarkup:
    """Franshiza qismlari uchun inline tugmalar."""
    buttons = []
    for p in parts:
        part_num, title_uz, title_ru, _ = p
        title = title_uz if lang == "uz" else (title_ru or title_uz or f"{part_num}-qism")
        buttons.append([InlineKeyboardButton(
            text=f"🎬 {part_num}-qism: {title}",
            callback_data=f"watch_part_{movie_id}_{part_num}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("watch_part_"))
async def cb_watch_franchise_part(call: CallbackQuery):
    """Franshiza qismini ko'rsatadi."""
    try:
        parts_split = call.data.split("_")
        movie_id = int(parts_split[2])
        part_num = int(parts_split[3])
    except (IndexError, ValueError):
        await call.answer("❌ Noto'g'ri so'rov!", show_alert=True)
        return

    lang = await _get_lang(call.from_user.id)

    async with get_db() as db:
        async with db.execute(
            """SELECT mp.file_id, mp.title_uz, mp.title_ru,
                      m.is_premium, m.title_uz as main_title
               FROM movie_parts mp
               JOIN movies m ON mp.movie_id = m.id
               WHERE mp.movie_id = ? AND mp.part_num = ?""",
            (movie_id, part_num)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await call.answer(
            _txt("❌ Video topilmadi!", "❌ Видео не найдено!", lang),
            show_alert=True
        )
        return

    file_id, title_uz, title_ru, is_premium, main_title = row

    # Premium tekshiruvi
    if is_premium:
        async with get_db() as db:
            async with db.execute(
                "SELECT is_premium FROM users WHERE tg_id = ?", (call.from_user.id,)
            ) as cur:
                user_row = await cur.fetchone()
        if not (user_row and user_row[0]):
            await call.answer()
            await call.message.answer(
                _txt(
                    "⭐ Bu qism faqat <b>Premium</b> uchun!\n/premium",
                    "⭐ Этот эпизод только для <b>Premium</b>!\n/premium",
                    lang
                ),
                parse_mode="HTML"
            )
            return

    title = title_uz if lang == "uz" else (title_ru or title_uz)
    protect = await get_protect_setting()
    await call.message.answer_video(
        video=file_id,
        caption=(
            f"🎬 <b>{main_title}</b>\n"
            f"📽 {part_num}-qism: {title}"
        ),
        parse_mode="HTML",
        protect_content=protect
    )
    await call.answer()
