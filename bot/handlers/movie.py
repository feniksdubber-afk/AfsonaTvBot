"""
movie.py
────────
Serial fasl va qism handlerlari.

Tuzatilgan xatolar (v2):
  1. edit_caption crash  → _safe_edit() poster yo'q bo'lsa edit_text ishlatadi
  2. watch_history       → play_ep_ da ko'rilgan qism yoziladi
  3. series_id           → SELECT ga qo'shildi (watch_history + premium uchun)
  4. NULL caption        → or "—" bilan himoyalandi, hech qachon "None" ko'rinmaydi
  5. Premium tekshiruvi  → play_ep_ da ham ishlaydi (callback orqali o'tib ketmaslik uchun)
  6. Lang                → DB dan olinadi — to'g'ri til
  7. Seasons bo'sh       → back_to_series_ da alohida xabar beriladi
  8. Ball (+2)           → har bir ko'rilgan qism uchun beriladi
  9. Xato boshqaruvi     → try/except + logger hamma joyda
"""

import logging

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from bot.database.db import get_db
from bot.utils.helpers import get_protect_setting

logger = logging.getLogger(__name__)
router = Router()


# ══════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════════════════════════════

async def _get_lang(user_id: int) -> str:
    """Foydalanuvchi tilini DB dan oladi. Xato bo'lsa 'uz' qaytaradi."""
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT lang FROM users WHERE tg_id = ?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else "uz"
    except Exception:
        return "uz"


def _txt(uz: str, ru: str, lang: str) -> str:
    return uz if lang == "uz" else ru


async def _safe_edit(call: CallbackQuery, caption: str,
                     reply_markup: InlineKeyboardMarkup) -> None:
    """
    Xabarni xavfsiz tahrirlaydi.
    - Foto/video xabar bo'lsa → edit_caption
    - Matn xabar bo'lsa (poster yo'q serial) → edit_text
    Ikkalasi ham muvaffaqiyatsiz bo'lsa — logger ga yozib o'tadi.
    """
    try:
        await call.message.edit_caption(
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return
    except Exception:
        pass

    try:
        await call.message.edit_text(
            text=caption,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning("_safe_edit: xabarni tahrirlashda xato — %s", e)


def _build_episode_kb(episodes: list, series_id: int) -> InlineKeyboardMarkup:
    """
    Qismlar tugmalarini 3 ustunli grid ko'rinishida yaratadi.
    episodes = [(episode_number, episode_db_id), ...]
    """
    kb_buttons: list = []
    row_btns: list = []

    for i, ep in enumerate(episodes):
        ep_num, ep_db_id = ep[0], ep[1]
        row_btns.append(InlineKeyboardButton(
            text=f"{ep_num}-qism",
            callback_data=f"play_ep_{ep_db_id}"
        ))
        if len(row_btns) == 3 or i == len(episodes) - 1:
            kb_buttons.append(row_btns.copy())
            row_btns = []

    # "Fasllarga qaytish" tugmasi — har doim pastda
    kb_buttons.append([InlineKeyboardButton(
        text="◀️ Fasllarga qaytish",
        callback_data=f"back_to_series_{series_id}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=kb_buttons)


def _build_seasons_kb(seasons: list, series_id: int,
                      lang: str) -> InlineKeyboardMarkup:
    """Fasllar tugmalar klaviaturasini yaratadi."""
    label = "Fasl" if lang == "uz" else "Сезон"
    kb_buttons = [
        [InlineKeyboardButton(
            text=f"📀 {r[0]}-{label}",
            callback_data=f"show_season_{series_id}_{r[0]}"
        )]
        for r in seasons
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb_buttons)


def _series_caption(s: dict, lang: str) -> str:
    """
    Serial ma'lumotlari uchun caption matnini yaratadi.
    Barcha maydonlar NULL bo'lishi mumkin — himoyalangan.
    """
    title   = s.get("title_uz") or "Nomsiz serial"
    year    = s.get("year") or "?"
    genres  = s.get("genres") or "—"
    country = s.get("country") or "—"
    desc    = s.get("description") or ""
    choose  = _txt("Faslni tanlang:", "Выберите сезон:", lang)

    if lang == "uz":
        return (
            f"📺 <b>{title}</b> ({year})\n"
            f"🎭 Janr: {genres}\n"
            f"🌍 Davlat: {country}\n\n"
            f"🍿 {desc}\n\n"
            f"👇 {choose}"
        )
    else:
        title_display = s.get("title_ru") or title
        return (
            f"📺 <b>{title_display}</b> ({year})\n"
            f"🎭 Жанр: {genres}\n"
            f"🌍 Страна: {country}\n\n"
            f"🍿 {desc}\n\n"
            f"👇 {choose}"
        )


async def _add_watch_points(user_id: int) -> None:
    """
    Qism ko'rilganda foydalanuvchiga +2 ball beradi.
    gamification.add_points orqali — point_log ga ham yoziladi.
    Xato bo'lsa asosiy funksiyani bloklamamaydi.
    """
    try:
        from bot.handlers.gamification import add_points, tournament_add_points
        await add_points(user_id, 2, reason="watch_episode")
        await tournament_add_points(user_id, 2)
    except Exception as e:
        logger.warning("Ball qo'shishda xato (user_id=%s): %s", user_id, e)


# ══════════════════════════════════════════════════════════════════
#  1. FASL BOSILGANDA QISMLARNI CHIQARISH
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("show_season_"))
async def cb_show_season_episodes(call: CallbackQuery):
    """
    Fasl tugmasi bosilganda o'sha fasldagi barcha qismlarni ko'rsatadi.
    callback_data: show_season_{series_id}_{season_num}
    """
    try:
        parts = call.data.split("_")
        series_id = int(parts[2])
        season_num = int(parts[3])
    except (IndexError, ValueError):
        await call.answer("❌ Noto'g'ri so'rov!", show_alert=True)
        return

    lang = await _get_lang(call.from_user.id)

    async with get_db() as db:
        async with db.execute(
            """SELECT episode_number, id
               FROM episodes
               WHERE series_id = ? AND season_number = ?
               ORDER BY episode_number""",
            (series_id, season_num)
        ) as cur:
            episodes = await cur.fetchall()

    if not episodes:
        msg = _txt(
            "⚠️ Bu faslda hali qismlar yuklanmagan!",
            "⚠️ В этом сезоне ещё нет эпизодов!",
            lang
        )
        await call.answer(msg, show_alert=True)
        return

    kb = _build_episode_kb(episodes, series_id)

    caption = _txt(
        f"📀 <b>{season_num}-Fasl qismlari</b>\n\n"
        f"Tomosha qilmoqchi bo'lgan qismni tanlang:",
        f"📀 <b>Эпизоды {season_num}-го сезона</b>\n\n"
        f"Выберите эпизод для просмотра:",
        lang
    )

    await _safe_edit(call, caption, kb)
    await call.answer()


# ══════════════════════════════════════════════════════════════════
#  2. QISM BOSILGANDA VIDEO YUBORISH
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("play_ep_"))
async def cb_play_selected_episode(call: CallbackQuery):
    """
    Qism tugmasi bosilganda:
      1. Premium tekshiruvi (serial premium bo'lsa)
      2. Video yuborish
      3. watch_history ga yozish
      4. Ball berish (+2)
    """
    try:
        ep_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.answer("❌ Noto'g'ri so'rov!", show_alert=True)
        return

    lang = await _get_lang(call.from_user.id)

    # ── Epizod va serial ma'lumotlarini olish ────────────────────
    async with get_db() as db:
        async with db.execute(
            """SELECT e.file_id,
                      s.title_uz,
                      s.title_ru,
                      e.season_number,
                      e.episode_number,
                      e.series_id,
                      s.is_premium
               FROM episodes e
               JOIN series s ON e.series_id = s.id
               WHERE e.id = ?""",
            (ep_id,)
        ) as cur:
            res = await cur.fetchone()

    if not res:
        msg = _txt("❌ Video fayl topilmadi!", "❌ Видеофайл не найден!", lang)
        await call.answer(msg, show_alert=True)
        return

    file_id, title_uz, title_ru, season, episode, series_id, is_premium = res

    # ── Premium tekshiruvi ────────────────────────────────────────
    # Foydalanuvchi callback orqali ham kelishi mumkin (boshqa foydalanuvchi
    # havolasidan), shuning uchun bu yerda ham tekshirish SHART.
    if is_premium:
        async with get_db() as db:
            async with db.execute(
                "SELECT is_premium FROM users WHERE tg_id = ?",
                (call.from_user.id,)
            ) as cur:
                user_row = await cur.fetchone()

        if not (user_row and user_row[0]):
            msg = _txt(
                "⭐ Bu qism faqat <b>Premium</b> foydalanuvchilar uchun!\n\n"
                "Premium olish: /start premium",
                "⭐ Этот эпизод только для <b>Premium</b> пользователей!\n\n"
                "Получить Premium: /start premium",
                lang
            )
            await call.answer()
            await call.message.answer(msg, parse_mode="HTML")
            return

    # ── Video yuborish ────────────────────────────────────────────
    title = title_uz if lang == "uz" else (title_ru or title_uz or "Nomsiz")
    season_label  = _txt(f"{season}-fasl",   f"{season}-й сезон",   lang)
    episode_label = _txt(f"{episode}-qism",  f"{episode}-я серия",  lang)

    protect = await get_protect_setting()
    try:
        await call.message.answer_video(
            video=file_id,
            caption=(
                f"📺 <b>{title}</b>\n"
                f"📀 {season_label} | {episode_label}"
            ),
            parse_mode="HTML",
            protect_content=protect
        )
    except Exception as e:
        logger.error("Video yuborishda xato (ep_id=%s): %s", ep_id, e)
        err = _txt(
            "❌ Video yuborishda xato yuz berdi. Iltimos qayta urinib ko'ring.",
            "❌ Ошибка при отправке видео. Пожалуйста, попробуйте снова.",
            lang
        )
        await call.message.answer(err)
        await call.answer()
        return

    # ── watch_history yozish ──────────────────────────────────────
    try:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO watch_history
                   (user_id, series_id, season_number, episode_number)
                   VALUES (?, ?, ?, ?)""",
                (call.from_user.id, series_id, season, episode)
            )
            await db.commit()
    except Exception as e:
        logger.warning("watch_history yozishda xato (user=%s): %s", call.from_user.id, e)

    # ── Ball berish (+2) ──────────────────────────────────────────
    await _add_watch_points(call.from_user.id)

    await call.answer()


# ══════════════════════════════════════════════════════════════════
#  3. SERIAL ASOSIY MENYUSIGA QAYTISH
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("back_to_series_"))
async def cb_back_to_series_menu(call: CallbackQuery):
    """
    "Fasllarga qaytish" tugmasi bosilganda serial asosiy menyusini ko'rsatadi.
    callback_data: back_to_series_{series_id}
    """
    try:
        series_id = int(call.data.split("_")[3])
    except (IndexError, ValueError):
        await call.answer("❌ Noto'g'ri so'rov!", show_alert=True)
        return

    lang = await _get_lang(call.from_user.id)

    async with get_db() as db:
        # cursor.description orqali dinamik ustun nomlari — qattiq kodlash yo'q
        async with db.execute(
            "SELECT * FROM series WHERE id = ?", (series_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                msg = _txt("❌ Serial topilmadi!", "❌ Сериал не найден!", lang)
                await call.answer(msg, show_alert=True)
                return
            cols = [d[0] for d in cur.description]
            s = dict(zip(cols, row))

        async with db.execute(
            "SELECT season_number FROM seasons WHERE series_id = ? ORDER BY season_number",
            (series_id,)
        ) as cur:
            seasons = await cur.fetchall()

    # Fasllar bo'sh bo'lsa
    if not seasons:
        msg = _txt(
            "⚠️ Bu serialga hali fasllar yuklanmagan.",
            "⚠️ К этому сериалу ещё не добавлены сезоны.",
            lang
        )
        await call.answer(msg, show_alert=True)
        return

    kb = _build_seasons_kb(seasons, series_id, lang)
    caption = _series_caption(s, lang)

    await _safe_edit(call, caption, kb)
    await call.answer()
