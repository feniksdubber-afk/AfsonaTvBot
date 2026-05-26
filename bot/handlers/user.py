"""
user.py
───────
Foydalanuvchi handlerlari: /start, profil, sevimlilar,
ko'rish tarixi, qidiruv, kino so'rov, support, referral.

TUZATILGAN:
  #1  Ko'rish tarixi watched_at bo'yicha saralanadi (movies+series birga)
  #2  Sevimlilar: movies + series birga ko'rsatiladi
  #3  /start kelganda FSM holati tozalanadi
  #4  Referral: row None bo'lsa xato bo'lmaydi
  #5  Premium kino/serial tekshiruvi qo'shildi
  #6  views va watch_history bitta tranzaksiyada
  #7  file_id None bo'lsa answer_video xato bermasligi
  #8  seasons bo'sh bo'lsa xabar beriladi
  #9  poster_file_id None bo'lsa answer_photo xato bermasligi
  #10 delete() dan KEYIN answer() chaqirish tartiblandiReferral ball point_log ga yoziladi
  #11 message.text None bo'lsa xato bo'lmaydi
  #12 Referral ball point_log ga yoziladi (gamification bilan izchillik)
"""

from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS
from bot.database.db import get_db
from bot.utils.helpers import get_user, txt, is_admin, get_protect_setting
from bot.keyboards.user_kb import (
    main_menu, profile_kb, lang_kb,
    notify_kb, back_kb, cancel_kb, content_menu_kb,
    movie_view_kb, series_view_kb
)

router = Router()


# ══════════════════════════════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════════════════════════════
class RequestState(StatesGroup):
    waiting_text = State()

class SupportState(StatesGroup):
    waiting_text = State()

class SearchState(StatesGroup):
    waiting_query = State()


# ══════════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════════════════════════════════

def _premium_label(user: dict, lang: str) -> str:
    if user.get("is_premium"):
        until = user.get("premium_until") or "?"
        return f"⭐ Premium ({until})"
    return "❌ Yo'q" if lang == "uz" else "❌ Нет"


async def _profile_stats(tg_id: int) -> tuple[int, int]:
    """Ko'rilgan va sevimlilardagi jami sonini qaytaradi."""
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM watch_history WHERE user_id = ?", (tg_id,)
        ) as cur:
            watched = (await cur.fetchone())[0]

        async with db.execute(
            "SELECT COUNT(*) FROM favorites WHERE user_id = ?", (tg_id,)
        ) as cur:
            favs = (await cur.fetchone())[0]

    return watched, favs


# ══════════════════════════════════════════════════════════════════════
#  /start — DEEP LINK HANDLERI
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text == "/help")
@router.message(F.text == "ℹ️ Yordam")
async def cmd_help(message: Message):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"
    if lang == "uz":
        text = (
            "ℹ️ <b>Bot bo'yicha yordam</b>\n\n"
            "🎬 <b>Kino ko'rish:</b>\n"
            "• Kino kodini yuboring (masalan: <code>401</code>)\n"
            "• Yoki 🍿 Tomosha qilish → Filmlar / Seriallar\n\n"
            "🔍 <b>Qidirish:</b>\n"
            "• /search yoki 🔍 Qidirish tugmasini bosing\n"
            "• Kino nomini yozing\n\n"
            "❤️ <b>Sevimlilar:</b>\n"
            "• Kino ostidagi ❤️ tugmani bosing\n"
            "• Ko'rish: 👤 Profil → ❤️ Sevimlilar\n\n"
            "📜 <b>Ko'rish tarixi:</b>\n"
            "• 👤 Profil → 📜 Tarix\n\n"
            "⭐ <b>Premium:</b>\n"
            "• /premium yoki ⭐ Premium tugmasini bosing\n\n"
            "📋 <b>Kino so'rovi:</b>\n"
            "• 📋 So'rov tugmasi orqali talab qiling\n\n"
            "📤 <b>Ulashish:</b>\n"
            "• Kino ostidagi 📤 Ulashish tugmasini bosing\n\n"
            "📞 <b>Muammo bo'lsa:</b> 📞 Support"
        )
    else:
        text = (
            "ℹ️ <b>Помощь по боту</b>\n\n"
            "🎬 <b>Смотреть фильм:</b>\n"
            "• Отправьте код фильма (например: <code>401</code>)\n"
            "• Или 🍿 Смотреть → Фильмы / Сериалы\n\n"
            "🔍 <b>Поиск:</b>\n"
            "• /search или кнопка 🔍 Поиск\n"
            "• Введите название фильма\n\n"
            "❤️ <b>Избранное:</b>\n"
            "• Нажмите ❤️ под фильмом\n"
            "• Просмотр: 👤 Профиль → ❤️ Избранное\n\n"
            "📜 <b>История просмотров:</b>\n"
            "• 👤 Профиль → 📜 История\n\n"
            "⭐ <b>Premium:</b>\n"
            "• /premium или кнопка ⭐ Премиум\n\n"
            "📋 <b>Запрос фильма:</b>\n"
            "• Через кнопку 📋 Запрос\n\n"
            "📤 <b>Поделиться:</b>\n"
            "• Нажмите 📤 под фильмом\n\n"
            "📞 <b>Проблемы:</b> 📞 Поддержка"
        )
    await message.answer(text, parse_mode="HTML")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    # FIX #3: /start kelganda FSM holati tozalanadi
    await state.clear()

    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    args_list = message.text.split() if message.text else []
    arg = args_list[1] if len(args_list) > 1 else ""

    # ── Referral ────────────────────────────────────────────────────
    if arg.startswith("ref_"):
        code = arg[4:]
        async with get_db() as db:
            async with db.execute(
                "SELECT tg_id FROM users WHERE referral_code = ?", (code,)
            ) as cur:
                inviter = await cur.fetchone()

            if inviter and inviter[0] != message.from_user.id:
                async with db.execute(
                    "SELECT referred_by FROM users WHERE tg_id = ?",
                    (message.from_user.id,)
                ) as cur:
                    row = await cur.fetchone()

                # FIX #4: row None bo'lsa xato bo'lmaydi
                if row is not None and row[0] is None:
                    await db.execute(
                        "UPDATE users SET referred_by = ? WHERE tg_id = ?",
                        (inviter[0], message.from_user.id)
                    )
                    await db.execute(
                        "UPDATE users SET balance = balance + 50 WHERE tg_id = ?",
                        (inviter[0],)
                    )
                    # FIX #12: Referral ball point_log ga yoziladi
                    await db.execute(
                        "INSERT INTO point_log (user_id, amount, reason) VALUES (?, 50, 'referral')",
                        (inviter[0],)
                    )
                    await db.commit()

    # ── movie_ deep link ────────────────────────────────────────────
    if arg.startswith("movie_"):
        code = arg[6:]
        await _send_movie_by_code(message, code, lang)
        return

    # ── series_ deep link ───────────────────────────────────────────
    if arg.startswith("series_"):
        code = arg[7:]
        await _send_series_by_code(message, code, lang)
        return

    # ── premium deep link ───────────────────────────────────────────
    if arg == "premium":
        from bot.handlers.premium import show_premium
        await show_premium(message)
        return

    # ── Oddiy /start — greeting ─────────────────────────────────────
    greeting = txt(
        f"👋 Xush kelibsiz, <b>{message.from_user.first_name}</b>!\n\n"
        "🎬 Bu bot orqali kino va seriallarni tomosha qilishingiz mumkin.\n"
        "Quyidagi menyudan foydalaning:",

        f"👋 Добро пожаловать, <b>{message.from_user.first_name}</b>!\n\n"
        "🎬 С помощью этого бота вы можете смотреть фильмы и сериалы.\n"
        "Используйте меню ниже:",
        lang
    )
    await message.answer(greeting, reply_markup=main_menu(lang), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════
#  DEEP LINK YORDAMCHI FUNKSIYALARI
# ══════════════════════════════════════════════════════════════════════
async def _send_movie_by_code(message: Message, code: str, lang: str = "uz", user_id: int = None):
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM movies WHERE code = ?", (code,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                await message.answer(txt("❌ Kontent topilmadi!", "❌ Контент не найден!", lang))
                return
            cols = [d[0] for d in cur.description]
            m = dict(zip(cols, row))

    status = m.get("status", "active")
    if status == "deleted":
        await message.answer(txt("❌ Kontent topilmadi!", "❌ Контент не найден!", lang))
        return
    if status == "archived":
        await message.answer(
            txt("⛔ Bu kontent vaqtinchalik arxivda.", "⛔ Контент временно в архиве.", lang)
        )
        return

    # FIX #5: Premium kino tekshiruvi
    if m.get("is_premium"):
        _uid = user_id or message.from_user.id
        user = await get_user(_uid)
        if not (user and user.get("is_premium")):
            await message.answer(
                txt(
                    "⭐ Bu kontent faqat <b>Premium</b> foydalanuvchilar uchun!\n\n"
                    "Premium olish uchun: /premium",
                    "⭐ Этот контент только для <b>Premium</b> пользователей!\n\n"
                    "Получить Premium: /premium",
                    lang
                ),
                parse_mode="HTML"
            )
            return

    # FIX #7: file_id None bo'lsa xato bermasligi
    if not m.get("file_id"):
        await message.answer(txt("❌ Video fayli topilmadi!", "❌ Видеофайл не найден!", lang))
        return

    title = m.get("title_uz") or m.get("title") or "Nomsiz kino"

    # OMDb cache dan IMDB reyting olish
    imdb_line = ""
    try:
        import json as _json
        title_q = title.lower()
        async with get_db() as db:
            async with db.execute(
                "SELECT data FROM omdb_cache WHERE LOWER(query) = ?", (title_q,)
            ) as cur:
                omdb_row = await cur.fetchone()
        if omdb_row:
            odata = _json.loads(omdb_row[0])
            ir = odata.get("imdbRating", "")
            if ir and ir != "N/A":
                imdb_line = f"\n⭐ IMDb: <b>{ir}/10</b>"
    except Exception:
        pass

    caption = (
        f"🎬 <b>{title}</b> ({m.get('year', '?')})\n"
        f"🎭 {m.get('genres') or m.get('genre', '') or '—'}\n"
        f"🌍 {m.get('country', '') or '—'}{imdb_line}\n\n"
        f"🍿 {m.get('description', '') or ''}"
    )

    # FIX #6: views va watch_history bitta tranzaksiyada
    async with get_db() as db:
        await db.execute(
            "UPDATE movies SET views = views + 1 WHERE id = ?", (m["id"],)
        )
        await db.execute(
            "INSERT INTO watch_history (user_id, movie_id) VALUES (?, ?)",
            (user_id or message.from_user.id, m["id"])
        )
        await db.commit()

    # Sevimlida borligini tekshirish
    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM favorites WHERE user_id = ? AND movie_id = ?",
            (user_id or message.from_user.id, m["id"])
        ) as cur:
            is_fav = (await cur.fetchone()) is not None

    # Franshiza qismlarini tekshirish (#3)
    from bot.handlers.franchise import get_movie_parts, franchise_parts_kb
    parts = await get_movie_parts(m["id"])
    protect = await get_protect_setting()
    bot_info = await message.bot.get_me()
    if parts:
        fparts_kb = franchise_parts_kb(m["id"], parts, lang)
        await message.answer_video(
            video=m["file_id"],
            caption=caption + f"\n\n🎞 Bu filmning <b>{len(parts)}</b> ta qismi mavjud:",
            parse_mode="HTML",
            protect_content=protect,
            reply_markup=fparts_kb
        )
    else:
        kb = movie_view_kb(m["id"], m.get("code", ""), is_fav, lang, bot_username=bot_info.username)
        await message.answer_video(
            video=m["file_id"],
            caption=caption,
            parse_mode="HTML",
            protect_content=protect,
            reply_markup=kb
        )


async def _send_series_by_code(message: Message, code: str, lang: str = "uz", user_id: int = None):
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM series WHERE code = ?", (code,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                await message.answer(txt("❌ Serial topilmadi!", "❌ Сериал не найден!", lang))
                return
            cols = [d[0] for d in cur.description]
            s = dict(zip(cols, row))

        async with db.execute(
            "SELECT season_number FROM seasons WHERE series_id = ? ORDER BY season_number",
            (s["id"],)
        ) as cur:
            seasons = await cur.fetchall()

    status = s.get("status", "active")
    if status == "deleted":
        await message.answer(txt("❌ Kontent topilmadi!", "❌ Контент не найден!", lang))
        return
    if status == "archived":
        await message.answer(
            txt("⛔ Bu kontent vaqtinchalik arxivda.", "⛔ Контент временно в архиве.", lang)
        )
        return

    # FIX #5: Premium serial tekshiruvi
    if s.get("is_premium"):
        _uid = user_id or message.from_user.id
        user = await get_user(_uid)
        if not (user and user.get("is_premium")):
            await message.answer(
                txt(
                    "⭐ Bu serial faqat <b>Premium</b> foydalanuvchilar uchun!\n\n"
                    "Premium olish uchun: /premium",
                    "⭐ Этот сериал только для <b>Premium</b> пользователей!\n\n"
                    "Получить Premium: /premium",
                    lang
                ),
                parse_mode="HTML"
            )
            return

    # FIX #8: seasons bo'sh bo'lsa xabar beriladi
    if not seasons:
        await message.answer(
            txt(
                "⚠️ Bu serialga hali qismlar yuklanmagan.",
                "⚠️ К этому сериалу ещё не загружены эпизоды.",
                lang
            )
        )
        return

    kb_buttons = [
        [InlineKeyboardButton(
            text=f"📀 {row[0]}-Fasl",
            callback_data=f"show_season_{s['id']}_{row[0]}"
        )]
        for row in seasons
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    title   = s.get("title_uz") or "Nomsiz serial"
    year    = s.get("year") or "?"
    genres  = s.get("genres") or "—"
    country = s.get("country") or "—"
    desc    = s.get("description") or ""
    caption = (
        f"📺 <b>{title}</b> ({year})\n"
        f"🎭 Janr: {genres}\n"
        f"🌍 Davlat: {country}\n\n"
        f"🍿 {desc}\n\n"
        f"👇 {'Faslni tanlang:' if lang == 'uz' else 'Выберите сезон:'}"
    )

    # Sevimlida borligini tekshirish
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT id FROM favorites WHERE user_id = ? AND series_id = ?",
                (user_id or message.from_user.id, s["id"])
            ) as cur:
                is_fav = (await cur.fetchone()) is not None
    except Exception:
        is_fav = False

    # Ko'rish davomini tekshirish
    last_ep = None
    try:
        async with get_db() as db:
            async with db.execute(
                """SELECT h.season_number, h.episode_number, e.id
                   FROM watch_history h
                   JOIN episodes e ON e.series_id = h.series_id
                     AND e.season_number = h.season_number
                     AND e.episode_number = h.episode_number
                   WHERE h.user_id = ? AND h.series_id = ?
                   ORDER BY h.watched_at DESC LIMIT 1""",
                (user_id or message.from_user.id, s["id"])
            ) as cur:
                last_ep = await cur.fetchone()
    except Exception:
        pass

    # Fasllar KB ga sevimli va ulashish tugmalarini qo'shamiz
    fav_text = (
        ("❤️ Sevimlilardan olib tashlash" if is_fav else "🤍 Sevimlilarga qo'shish")
        if lang == "uz" else
        ("❤️ Убрать из избранного" if is_fav else "🤍 Добавить в избранное")
    )
    share_text = "📤 Serialni ulashish" if lang == "uz" else "📤 Поделиться сериалом"
    bot_info = await message.bot.get_me()
    from urllib.parse import quote as url_quote
    deep_link = f"https://t.me/{bot_info.username}?start=series_{s['code']}"

    extra_buttons = []
    if last_ep:
        s_n, e_n, ep_id = last_ep
        cont_text = (
            f"▶️ Davom ettirish ({s_n}-fasl {e_n}-qism)"
            if lang == "uz" else
            f"▶️ Продолжить ({s_n} сезон {e_n} серия)"
        )
        extra_buttons.append([InlineKeyboardButton(text=cont_text, callback_data=f"play_ep_{ep_id}")])

    extra_buttons += [
        [InlineKeyboardButton(text=fav_text, callback_data=f"fav_series_{s['id']}")],
        [InlineKeyboardButton(
            text=share_text,
            url=f"https://t.me/share/url?url={url_quote(deep_link)}"
        )],
    ]
    kb_list = list(kb.inline_keyboard) + extra_buttons
    kb = InlineKeyboardMarkup(inline_keyboard=kb_list)

    # FIX #9: poster_file_id None bo'lsa answer_photo xato bermasligi
    protect = await get_protect_setting()
    try:
        if s.get("poster_file_id"):
            await message.answer_photo(
                photo=s["poster_file_id"],
                caption=caption,
                reply_markup=kb,
                parse_mode="HTML",
                protect_content=protect
            )
        else:
            await message.answer(caption, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("_send_series_by_code yuborishda xato: %s", e)
        try:
            await message.answer(caption, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
#  PROFIL
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text.in_(["👤 Profil", "👤 Профиль"]))
async def show_profile(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return
    lang = user["lang"]
    watched, favs = await _profile_stats(user["tg_id"])
    premium_status = _premium_label(user, lang)

    lang_label = "O'zbek \U0001f1fa\U0001f1ff" if lang == "uz" else "Ruscha \U0001f1f7\U0001f1fa"
    text = txt(
        f"👤 <b>Profil</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👨 Ism: {user['full_name']}\n"
        f"🌐 Til: {lang_label}\n"
        f"⭐ Premium: {premium_status}\n"
        f"💰 Balans: {user['balance']} ball\n\n"
        f"📊 <b>Statistika</b>\n"
        f"🎬 Ko'rilgan: {watched} ta\n"
        f"❤️ Sevimlilar: {favs} ta\n"
        f"👥 Referral kodi: <code>{user['referral_code']}</code>",

        f"👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👨 Имя: {user['full_name']}\n"
        f"🌐 Yazyk: {lang_label}\n"
        f"⭐ Премиум: {premium_status}\n"
        f"💰 Баланс: {user['balance']} баллов\n\n"
        f"📊 <b>Статистика</b>\n"
        f"🎬 Просмотрено: {watched}\n"
        f"❤️ Избранное: {favs}\n"
        f"👥 Реферальный код: <code>{user['referral_code']}</code>",
        lang
    )
    await message.answer(text, reply_markup=profile_kb(lang), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════
#  TIL O'ZGARTIRISH
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "change_lang")
async def change_lang(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    await call.message.edit_text(
        txt("🌐 Tilni tanlang:", "🌐 Выберите язык:", lang),
        reply_markup=lang_kb()
    )
    await call.answer()


@router.callback_query(F.data.startswith("set_lang_"))
async def set_lang(call: CallbackQuery):
    new_lang = call.data.split("_")[-1]
    if new_lang not in ("uz", "ru"):
        await call.answer()
        return

    async with get_db() as db:
        await db.execute(
            "UPDATE users SET lang = ? WHERE tg_id = ?",
            (new_lang, call.from_user.id)
        )
        await db.commit()

    msg = "✅ Til o'zgartirildi!" if new_lang == "uz" else "✅ Язык изменён!"
    # FIX #10: avval answer() keyin delete() — to'g'ri tartib
    await call.answer(msg)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(msg, reply_markup=main_menu(new_lang))


# ══════════════════════════════════════════════════════════════════════
#  BILDIRISHNOMA SOZLAMALARI
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "notifications")
async def notifications(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer()
        return
    lang = user["lang"]
    await call.message.edit_text(
        txt("🔔 Bildirishnoma sozlamalari:", "🔔 Настройки уведомлений:", lang),
        reply_markup=notify_kb(user["notify"], lang)
    )
    await call.answer()


@router.callback_query(F.data == "toggle_notify")
async def toggle_notify(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer()
        return
    new_val = 0 if user["notify"] else 1
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET notify = ? WHERE tg_id = ?",
            (new_val, call.from_user.id)
        )
        await db.commit()
    lang = user["lang"]
    msg = txt(
        "🔔 Yoqildi!" if new_val else "🔕 O'chirildi!",
        "🔔 Включено!" if new_val else "🔕 Выключено!",
        lang
    )
    await call.answer(msg)
    await call.message.edit_reply_markup(reply_markup=notify_kb(new_val, lang))


# ══════════════════════════════════════════════════════════════════════
#  TUNGI REJIM
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "night_mode")
async def night_mode(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer()
        return
    new_val = 0 if user["night_mode"] else 1
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET night_mode = ? WHERE tg_id = ?",
            (new_val, call.from_user.id)
        )
        await db.commit()
    lang = user["lang"]
    msg = txt(
        "🌙 Tungi rejim yoqildi!" if new_val else "☀️ Tungi rejim o'chirildi!",
        "🌙 Ночной режим включён!" if new_val else "☀️ Ночной режим выключен!",
        lang
    )
    await call.answer(msg, show_alert=True)


# ══════════════════════════════════════════════════════════════════════
#  REFERRAL
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "referral")
async def referral(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer()
        return
    lang = user["lang"]

    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (user["tg_id"],)
        ) as cur:
            count = (await cur.fetchone())[0]

    bot_info = await call.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user['referral_code']}"

    text = txt(
        f"👥 <b>Referral tizimi</b>\n\n"
        f"Har bir taklif qilingan do'stingiz uchun <b>50 ball</b> olasiz!\n\n"
        f"👤 Taklif qilganlar: <b>{count} ta</b>\n"
        f"🔗 Sizning havolangiz:\n{link}",

        f"👥 <b>Реферальная система</b>\n\n"
        f"За каждого приглашённого друга вы получаете <b>50 баллов</b>!\n\n"
        f"👤 Приглашено: <b>{count}</b>\n"
        f"🔗 Ваша ссылка:\n{link}",
        lang
    )
    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  SEVIMLILAR
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "favorites")
@router.callback_query(F.data.startswith("favorites_page_"))
async def show_favorites(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer()
        return
    lang = user["lang"]

    # Sahifa raqami
    page = 0
    if call.data.startswith("favorites_page_"):
        try:
            page = int(call.data.split("_")[2])
        except (IndexError, ValueError):
            page = 0

    PAGE_SIZE = 10

    async with get_db() as db:
        # Kino va seriallarni bitta so'rovda olamiz, added_at bo'yicha saralanadi
        async with db.execute(
            """SELECT COALESCE(m.title_uz, m.title, 'Nomsiz') AS title,
                      m.code, 'movie' AS ctype, f.movie_id AS item_id, f.added_at
               FROM favorites f
               JOIN movies m ON f.movie_id = m.id
               WHERE f.user_id = ? AND m.status = 'active' AND f.movie_id IS NOT NULL
               UNION ALL
               SELECT COALESCE(s.title_uz, 'Nomsiz serial') AS title,
                      s.code, 'series' AS ctype, f.series_id AS item_id, f.added_at
               FROM favorites f
               JOIN series s ON f.series_id = s.id
               WHERE f.user_id = ? AND s.status = 'active' AND f.series_id IS NOT NULL
               ORDER BY added_at DESC""",
            (user["tg_id"], user["tg_id"])
        ) as cur:
            all_items = await cur.fetchall()

    total = len(all_items)
    page_items = all_items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    if not page_items:
        text = txt("❤️ Sevimlilar bo'sh.", "❤️ Избранное пусто.", lang)
        await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
        await call.answer()
        return

    # Har bir kino/serial uchun alohida tugma
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for title, code, ctype, item_id, _ in page_items:
        icon = "🎬" if ctype == "movie" else "📺"
        cb = f"fav_open_movie_{code}" if ctype == "movie" else f"fav_open_series_{code}"
        buttons.append([InlineKeyboardButton(text=f"{icon} {title}", callback_data=cb)])

    # Sahifalash tugmalari
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️ Oldingi",
            callback_data=f"favorites_page_{page - 1}"
        ))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            text="Keyingi ➡️",
            callback_data=f"favorites_page_{page + 1}"
        ))
    if nav:
        buttons.append(nav)

    back_label = "◀️ Orqaga" if lang == "uz" else "◀️ Назад"
    buttons.append([InlineKeyboardButton(text=back_label, callback_data="back_profile")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    start = page * PAGE_SIZE + 1
    end = min(start + PAGE_SIZE - 1, total)
    header = txt(
        f"❤️ <b>Sevimlilar</b> ({start}–{end} / {total})",
        f"❤️ <b>Избранное</b> ({start}–{end} / {total})",
        lang
    )
    await call.message.edit_text(header, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("fav_open_movie_"))
async def fav_open_movie(call: CallbackQuery):
    code = call.data.split("fav_open_movie_")[1]
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    await call.answer()
    await _send_movie_by_code(call.message, code, lang, user_id=call.from_user.id)


@router.callback_query(F.data.startswith("fav_open_series_"))
async def fav_open_series(call: CallbackQuery):
    code = call.data.split("fav_open_series_")[1]
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    await call.answer()
    await _send_series_by_code(call.message, code, lang, user_id=call.from_user.id)


# ══════════════════════════════════════════════════════════════════════
#  KO'RISH TARIXI — FIX #1: watched_at bo'yicha to'g'ri saralanadi
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "history")
async def watch_history(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer()
        return
    lang = user["lang"]

    async with get_db() as db:
        async with db.execute(
            """SELECT 'movie' AS type,
                      COALESCE(m.title_uz, m.title, 'Nomsiz') AS title,
                      h.watched_at, NULL, NULL
               FROM watch_history h
               JOIN movies m ON h.movie_id = m.id
               WHERE h.user_id = ? AND h.movie_id IS NOT NULL""",
            (user["tg_id"],)
        ) as cur:
            movie_rows = await cur.fetchall()

        async with db.execute(
            """SELECT 'series' AS type,
                      COALESCE(s.title_uz, 'Nomsiz serial') AS title,
                      h.watched_at,
                      h.season_number,
                      h.episode_number
               FROM watch_history h
               JOIN series s ON h.series_id = s.id
               WHERE h.user_id = ? AND h.series_id IS NOT NULL""",
            (user["tg_id"],)
        ) as cur:
            series_rows = await cur.fetchall()

    # FIX #1: Ikki ro'yxat birlashtiriladi va watched_at bo'yicha saralanadi
    all_history = sorted(
        list(movie_rows) + list(series_rows),
        key=lambda x: x[2] or "",
        reverse=True
    )[:20]

    lines = []
    for ctype, title, watched_at, season, episode in all_history:
        date_str = (watched_at or "")[:10]
        if ctype == "movie":
            lines.append(f"🎬 {title} <i>({date_str})</i>")
        else:
            ep_info = f"{season}-fasl {episode}-qism" if season and episode else ""
            lines.append(f"📺 {title} {ep_info} <i>({date_str})</i>")

    if not lines:
        text = txt("📜 Tarix bo'sh.", "📜 История пуста.", lang)
    else:
        joined = "\n".join(lines)
        text = txt(
            f"📜 <b>Ko'rish tarixi</b>\n\n{joined}",
            f"📜 <b>История просмотров</b>\n\n{joined}",
            lang
        )

    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  KINO SO'ROV
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text.in_(["📋 So'rov", "📋 Запрос"]))
async def movie_request_start(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"
    await message.answer(
        txt(
            "📋 Qaysi kino yoki serialni qo'shishimizni xohlaysiz?\n"
            "Nomi, yili va tilini yozing:",
            "📋 Какой фильм или сериал вы хотите добавить?\n"
            "Напишите название, год и язык:",
            lang
        ),
        reply_markup=cancel_kb(lang)
    )
    await state.set_state(RequestState.waiting_text)


@router.message(RequestState.waiting_text)
async def movie_request_save(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    # FIX #11: message.text None bo'lishi mumkin
    if not message.text:
        await message.answer(
            txt("❌ Iltimos, matn yuboring.", "❌ Пожалуйста, отправьте текст.", lang)
        )
        return

    async with get_db() as db:
        await db.execute(
            "INSERT INTO movie_requests (user_id, text) VALUES (?, ?)",
            (message.from_user.id, message.text)
        )
        await db.commit()

    await state.clear()
    await message.answer(
        txt(
            "✅ So'rovingiz qabul qilindi! Tez orada ko'rib chiqamiz.",
            "✅ Ваш запрос принят! Рассмотрим в ближайшее время.",
            lang
        ),
        reply_markup=main_menu(lang)
    )


# ══════════════════════════════════════════════════════════════════════
#  SUPPORT
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text.in_(["📞 Support", "📞 Поддержка"]))
async def support_start(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"
    await message.answer(
        txt(
            "📞 Muammoingizni yozing, adminlar tez orada javob beradi:",
            "📞 Опишите вашу проблему, администраторы ответят в ближайшее время:",
            lang
        ),
        reply_markup=cancel_kb(lang)
    )
    await state.set_state(SupportState.waiting_text)


@router.message(SupportState.waiting_text)
async def support_save(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    msg_text = message.text or "[Matn yo'q]"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    user_id = message.from_user.id

    for admin_id in ADMINS:
        try:
            reply_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="💬 Javob berish",
                    callback_data=f"support_reply_{user_id}"
                )
            ]])
            admin_text = (
                f"📞 <b>Support xabari</b>\n\n"
                f"👤 {message.from_user.full_name} "
                f"(<code>{user_id}</code>)\n"
                f"💬 {msg_text}"
            )
            await message.bot.send_message(
                admin_id, admin_text,
                reply_markup=reply_kb,
                parse_mode="HTML"
            )
        except Exception:
            pass

    await state.clear()
    await message.answer(
        txt(
            "✅ Xabaringiz adminga yuborildi!",
            "✅ Ваше сообщение отправлено администратору!",
            lang
        ),
        reply_markup=main_menu(lang)
    )


# ══════════════════════════════════════════════════════════════════════
#  PROFILGA QAYTISH
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "back_profile")
async def back_profile(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer()
        return
    lang = user["lang"]
    watched, favs = await _profile_stats(user["tg_id"])
    premium_status = _premium_label(user, lang)

    text = txt(
        f"👤 <b>Profil</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👨 Ism: {user['full_name']}\n"
        f"⭐ Premium: {premium_status}\n"
        f"💰 Balans: {user['balance']} ball\n\n"
        f"📊 Ko'rilgan: {watched} | ❤️ Sevimlilar: {favs}",

        f"👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👨 Имя: {user['full_name']}\n"
        f"⭐ Премиум: {premium_status}\n"
        f"💰 Баланс: {user['balance']} баллов\n\n"
        f"📊 Просмотрено: {watched} | ❤️ Избранное: {favs}",
        lang
    )
    await call.message.edit_text(text, reply_markup=profile_kb(lang), parse_mode="HTML")
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  NOOP
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  🎬 KINOLAR MENYUSI
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text.in_(["🎬 Kinolar", "🎬 Фильмы"]))  # eski nom uchun ham ishlaydi
async def show_movies_menu_legacy(message: Message):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM movies WHERE status = 'active'"
        ) as cur:
            total = (await cur.fetchone())[0]

        async with db.execute(
            """SELECT code, COALESCE(title_uz, title, 'Nomsiz') as title,
                      year, genres, is_premium
               FROM movies WHERE status = 'active'
               ORDER BY id DESC LIMIT 8"""
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        text = txt("🎬 Hozircha kinolar yo'q.", "🎬 Фильмов пока нет.", lang)
        await message.answer(text)
        return

    lines = []
    for code, title, year, genres, is_prem in rows:
        prem = "⭐" if is_prem else "🔓"
        y = f"({year})" if year else ""
        lines.append(f"{prem} <code>{code}</code> — <b>{title}</b> {y}")

    hint = txt(
        f"\n📊 Jami: <b>{total} ta</b> kino\n\n🔍 Kino kodini yuboring — bot ko'rsatadi.\n"
        f"Qidirish uchun: /search",
        f"\n📊 Всего: <b>{total}</b> фильмов\n\n🔍 Отправьте код фильма — бот покажет.\n"
        f"Поиск: /search",
        lang
    )
    text = (
        txt("🎬 <b>Oxirgi kinolar</b>\n\n", "🎬 <b>Последние фильмы</b>\n\n", lang)
        + "\n".join(lines)
        + hint
    )
    await message.answer(text, parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════
#  🔍 QIDIRISH
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text.in_(["🔍 Qidirish", "🔍 Поиск"]))
@router.message(F.text == "/search")
async def search_start(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"
    await message.answer(
        txt(
            "🔍 Kino yoki serial nomini yozing:",
            "🔍 Введите название фильма или сериала:",
            lang
        )
    )
    await state.set_state(SearchState.waiting_query)


@router.message(SearchState.waiting_query)
async def search_process(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"
    query = (message.text or "").strip()

    if not query or len(query) < 2:
        await message.answer(txt("❌ Kamida 2 ta harf kiriting.", "❌ Введите минимум 2 символа.", lang))
        return

    await state.clear()
    like = f"%{query}%"

    async with get_db() as db:
        async with db.execute(
            """SELECT code, COALESCE(title_uz, title, 'Nomsiz') as title,
                      year, genres, is_premium
               FROM movies
               WHERE status = 'active'
                 AND (title_uz LIKE ? OR title LIKE ? OR title_ru LIKE ? OR code LIKE ?)
               ORDER BY views DESC LIMIT 10""",
            (like, like, like, like)
        ) as cur:
            movies = await cur.fetchall()

        async with db.execute(
            """SELECT code, COALESCE(title_uz, 'Nomsiz serial') as title,
                      year, genres, is_premium
               FROM series
               WHERE status = 'active'
                 AND (title_uz LIKE ? OR title_ru LIKE ? OR code LIKE ?)
               ORDER BY id DESC LIMIT 5""",
            (like, like, like)
        ) as cur:
            series_rows = await cur.fetchall()

    all_results = [("movie", *r) for r in movies] + [("series", *r) for r in series_rows]

    if not all_results:
        text = txt(
            f"🔍 «{query}» bo'yicha hech narsa topilmadi.",
            f"🔍 По запросу «{query}» ничего не найдено.",
            lang
        )
        await message.answer(text)
        return

    lines = []
    for ctype, code, title, year, genres, is_prem in all_results:
        icon = "🎬" if ctype == "movie" else "📺"
        prem = "⭐" if is_prem else "🔓"
        y = f"({year})" if year else ""
        lines.append(f"{icon} {prem} <code>{code}</code> — <b>{title}</b> {y}")

    hint = txt(
        "\nKodini yuboring — bot ko'rsatadi.",
        "\nОтправьте код — бот покажет.",
        lang
    )
    text = (
        txt(f"🔍 «{query}» natijalari:\n\n", f"🔍 Результаты «{query}»:\n\n", lang)
        + "\n".join(lines)
        + hint
    )
    await message.answer(text, parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════
#  🎬 KINO KODI — Foydalanuvchi to'g'ridan kod yozsa
# ══════════════════════════════════════════════════════════════════════
@router.message(StateFilter(None), F.text.regexp(r'^\d{3,5}$'))
async def handle_movie_code(message: Message):
    """
    Foydalanuvchi 3-5 xonali raqam yuborganda kino/serial qidiradi.
    Masalan: 847, 3291, 58043
    FSM holati bo'lsa (admin jarayonlarda) bu handler ISHLAMAYDI.
    """
    code = message.text.strip()
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    # Avval movie jadvalida qidirish
    movie = None  # FIX: UnboundLocalError oldini olish
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM movies WHERE code = ? AND status = 'active'", (code,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                cols = [d[0] for d in cur.description]
                movie = dict(zip(cols, row))

        if not row:
            # Series jadvalida qidirish
            async with db.execute(
                "SELECT * FROM series WHERE code = ? AND status = 'active'", (code,)
            ) as cur:
                row = await cur.fetchone()
                if row:
                    cols = [d[0] for d in cur.description]
                    series = dict(zip(cols, row))
                else:
                    series = None
        else:
            series = None

    if movie:
        await _send_movie_by_code(message, code, lang)
    elif series:
        await _send_series_by_code(message, code, lang)
    else:
        await message.answer(
            txt(
                f"❌ <b>{code}</b> kodi bo'yicha kino topilmadi.\n\n"
                "🔍 Qidirish uchun: /search",
                f"❌ По коду <b>{code}</b> ничего не найдено.\n\n"
                "🔍 Поиск: /search",
                lang
            ),
            parse_mode="HTML"
        )


# ══════════════════════════════════════════════════════════════════════
#  📞 SUPPORT — Admin javob berishi
# ══════════════════════════════════════════════════════════════════════
class SupportReplyState(StatesGroup):
    waiting_reply = State()


@router.callback_query(F.data.startswith("support_reply_"))
async def support_reply_start(call: CallbackQuery, state: FSMContext):
    from bot.config import ADMINS
    if call.from_user.id not in ADMINS:
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    # "support_reply_{user_id}" — user_id 10+ xonali bo'lishi mumkin
    # split("_", 2) ishlatamiz: faqat 2 ta ajratish, qolganini saqlaymiz
    parts = call.data.split("_", 2)
    user_id = int(parts[2])
    await state.update_data(support_target=user_id)
    await state.set_state(SupportReplyState.waiting_reply)
    await call.message.answer(
        f"💬 <code>{user_id}</code> ga javob yozing:",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(SupportReplyState.waiting_reply)
async def support_reply_send(message: Message, state: FSMContext):
    from bot.config import ADMINS
    if message.from_user.id not in ADMINS:
        return

    sd = await state.get_data()
    target = sd.get("support_target")
    await state.clear()

    if not target:
        await message.answer("❌ Xatolik!")
        return

    try:
        await message.bot.send_message(
            target,
            f"📞 <b>Admin javobi:</b>\n\n{message.text}",
            parse_mode="HTML"
        )
        await message.answer("✅ Javob yuborildi!")
    except Exception as e:
        await message.answer(f"❌ Yuborishda xato: {e}")


# ══════════════════════════════════════════════════════════════════════
#  ❌ BEKOR QILISH — Support va So'rov uchun
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "cancel_input")
async def cancel_input(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    await call.message.delete()
    await call.answer(
        txt("❌ Bekor qilindi", "❌ Отменено", lang)
    )


# ══════════════════════════════════════════════════════════════════════
#  🍿 TOMOSHA QILISH MENYUSI
# ══════════════════════════════════════════════════════════════════════
@router.message(F.text.in_(["🍿 Tomosha qilish", "🍿 Смотреть"]))
async def show_watch_menu(message: Message):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"
    await message.answer(
        txt(
            "🍿 <b>Tomosha qilish</b>\n\nQaysi turni tanlaysiz?",
            "🍿 <b>Смотреть</b>\n\nЧто выбираете?",
            lang
        ),
        reply_markup=content_menu_kb(lang),
        parse_mode="HTML"
    )


# ── Film ro'yxati ─────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("browse_movies_"))
async def browse_movies(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    page = int(call.data.split("_")[2])
    limit = 8
    offset = page * limit

    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM movies WHERE status = 'active'"
        ) as cur:
            total = (await cur.fetchone())[0]

        async with db.execute(
            """SELECT id, code, COALESCE(title_uz, title, 'Nomsiz') as title,
                      year, genres, is_premium, views
               FROM movies WHERE status = 'active'
               ORDER BY views DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await call.answer(txt("Kinolar yo'q", "Фильмов нет", lang), show_alert=True)
        return

    lines = []
    for mid, code, title, year, genres, is_prem, views in rows:
        prem = "⭐" if is_prem else "🔓"
        y = f"({year})" if year else ""
        lines.append(f"{prem} <code>{code}</code> — <b>{title}</b> {y}")

    # Sahifalash tugmalari
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"browse_movies_{page-1}"))
    if offset + limit < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"browse_movies_{page+1}"))

    buttons = []
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(
        text=txt("◀️ Orqaga", "◀️ Назад", lang),
        callback_data="back_watch_menu"
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = (
        txt(f"🎬 <b>Filmlar</b> ({total} ta)\n\n", f"🎬 <b>Фильмы</b> ({total})\n\n", lang)
        + "\n".join(lines)
        + txt(
            "\n\n📌 Kino kodini yuboring — bot ko'rsatadi.",
            "\n\n📌 Отправьте код фильма — бот покажет.",
            lang
        )
    )
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


# ── Serial ro'yxati ───────────────────────────────────────────────────
@router.callback_query(F.data.startswith("browse_series_"))
async def browse_series(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    page = int(call.data.split("_")[2])
    limit = 8
    offset = page * limit

    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM series WHERE status = 'active'"
        ) as cur:
            total = (await cur.fetchone())[0]

        async with db.execute(
            """SELECT id, code, COALESCE(title_uz, 'Nomsiz serial') as title,
                      year, genres, is_premium
               FROM series WHERE status = 'active'
               ORDER BY id DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await call.answer(txt("Seriallar yo'q", "Сериалов нет", lang), show_alert=True)
        return

    lines = []
    for sid, code, title, year, genres, is_prem in rows:
        prem = "⭐" if is_prem else "🔓"
        y = f"({year})" if year else ""
        lines.append(f"{prem} <code>{code}</code> — <b>{title}</b> {y}")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"browse_series_{page-1}"))
    if offset + limit < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"browse_series_{page+1}"))

    buttons = []
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(
        text=txt("◀️ Orqaga", "◀️ Назад", lang),
        callback_data="back_watch_menu"
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = (
        txt(f"📺 <b>Seriallar</b> ({total} ta)\n\n", f"📺 <b>Сериалы</b> ({total})\n\n", lang)
        + "\n".join(lines)
        + txt(
            "\n\n📌 Serial kodini yuboring — bot ko'rsatadi.",
            "\n\n📌 Отправьте код сериала — бот покажет.",
            lang
        )
    )
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


# ── TOP kinolar ───────────────────────────────────────────────────────
@router.callback_query(F.data == "browse_top")
async def browse_top(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"

    async with get_db() as db:
        async with db.execute(
            """SELECT code, COALESCE(title_uz, title, 'Nomsiz') as title,
                      year, views, is_premium
               FROM movies WHERE status = 'active'
               ORDER BY views DESC LIMIT 10"""
        ) as cur:
            rows = await cur.fetchall()

    lines = []
    for i, (code, title, year, views, is_prem) in enumerate(rows, 1):
        prem = "⭐" if is_prem else "🔓"
        y = f"({year})" if year else ""
        lines.append(f"{i}. {prem} <code>{code}</code> — <b>{title}</b> {y} 👁{views:,}")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=txt("◀️ Orqaga", "◀️ Назад", lang),
            callback_data="back_watch_menu"
        )
    ]])

    text = (
        txt("🔥 <b>TOP 10 — Eng ko'p ko'rilgan</b>\n\n",
            "🔥 <b>ТОП 10 — Самые просматриваемые</b>\n\n", lang)
        + "\n".join(lines)
    )
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


# ── Orqaga — tomosha menyusi ──────────────────────────────────────────
@router.callback_query(F.data == "back_watch_menu")
async def back_watch_menu(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    try:
        await call.message.edit_text(
            txt("🍿 <b>Tomosha qilish</b>\n\nQaysi turni tanlaysiz?",
                "🍿 <b>Смотреть</b>\n\nЧто выбираете?", lang),
            reply_markup=content_menu_kb(lang),
            parse_mode="HTML"
        )
    except Exception:
        pass
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  🎲 TASODIFIY KINO
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "random_movie")
async def cb_random_movie(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    is_prem = user.get("is_premium", 0) if user else 0

    async with get_db() as db:
        query = (
            "SELECT code FROM movies WHERE status = 'active' ORDER BY RANDOM() LIMIT 1"
            if is_prem else
            "SELECT code FROM movies WHERE status = 'active' AND is_premium = 0 ORDER BY RANDOM() LIMIT 1"
        )
        async with db.execute(query) as cur:
            row = await cur.fetchone()

    await call.answer()
    if not row:
        await call.message.answer(txt("❌ Kinolar topilmadi!", "❌ Фильмы не найдены!", lang))
        return
    await _send_movie_by_code(call.message, row[0], lang, user_id=call.from_user.id)


# ══════════════════════════════════════════════════════════════════════
#  🎭 JANRLAR BO'YICHA KO'RISH
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "genre_list")
async def cb_genre_list(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"

    async with get_db() as db:
        async with db.execute(
            "SELECT genres FROM movies WHERE status = 'active' AND genres IS NOT NULL"
        ) as cur:
            rows = await cur.fetchall()

    genre_set = set()
    for (genres_raw,) in rows:
        for g in genres_raw.replace("\n", ",").split(","):
            g = g.strip()
            if g:
                genre_set.add(g)

    genres_sorted = sorted(genre_set)[:20]
    buttons = []
    for i in range(0, len(genres_sorted), 2):
        row_btns = [InlineKeyboardButton(
            text=genres_sorted[i], callback_data=f"genre_movies_{genres_sorted[i][:30]}_0"
        )]
        if i + 1 < len(genres_sorted):
            row_btns.append(InlineKeyboardButton(
                text=genres_sorted[i + 1], callback_data=f"genre_movies_{genres_sorted[i+1][:30]}_0"
            ))
        buttons.append(row_btns)
    buttons.append([InlineKeyboardButton(
        text=txt("◀️ Orqaga", "◀️ Назад", lang), callback_data="back_watch_menu"
    )])

    title = txt("🎭 <b>Janrni tanlang:</b>", "🎭 <b>Выберите жанр:</b>", lang)
    try:
        await call.message.edit_text(title, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    except Exception:
        await call.message.answer(title, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("genre_movies_"))
async def cb_genre_movies(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"

    parts = call.data.split("_")
    page = int(parts[-1]) if parts[-1].isdigit() else 0
    genre = "_".join(parts[2:-1])

    per_page = 8
    offset = page * per_page

    async with get_db() as db:
        async with db.execute(
            """SELECT code, COALESCE(title_uz, title, 'Nomsiz') as title, year, is_premium
               FROM movies
               WHERE status = 'active' AND (genres LIKE ? OR genre LIKE ?)
               ORDER BY views DESC LIMIT ? OFFSET ?""",
            (f"%{genre}%", f"%{genre}%", per_page + 1, offset)
        ) as cur:
            rows = await cur.fetchall()

    has_next = len(rows) > per_page
    rows = rows[:per_page]

    if not rows:
        await call.answer(txt("Bu janrda film yo'q!", "Нет фильмов в этом жанре!", lang), show_alert=True)
        return

    lines = []
    for code, title, year, is_prem_flag in rows:
        icon = "⭐" if is_prem_flag else "🎬"
        y = f"({year})" if year else ""
        lines.append(f"{icon} <code>{code}</code> — {title} {y}")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"genre_movies_{genre}_{page-1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"genre_movies_{genre}_{page+1}"))

    buttons = []
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(
        text=txt("◀️ Janrlar", "◀️ Жанры", lang), callback_data="genre_list"
    )])

    text = (
        txt(f"🎭 <b>{genre}</b> janridagi kinolar:\n\n",
            f"🎭 Фильмы жанра <b>{genre}</b>:\n\n", lang)
        + "\n".join(lines)
        + txt("\n\n📌 Kod yuboring → kino ochiladi", "\n\n📌 Отправьте код → откроется фильм", lang)
    )
    try:
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  👍👎 LIKE / DISLIKE
# ══════════════════════════════════════════════════════════════════════
async def _ensure_reactions_table():
    async with get_db() as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS movie_reactions (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL,
                movie_id INTEGER NOT NULL,
                reaction TEXT NOT NULL,
                UNIQUE(user_id, movie_id)
            )"""
        )
        await db.commit()


@router.callback_query(F.data.startswith("react_like_"))
@router.callback_query(F.data.startswith("react_dislike_"))
async def cb_movie_react(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"

    is_like  = call.data.startswith("react_like_")
    movie_id = int(call.data.split("_")[-1])
    reaction = "like" if is_like else "dislike"

    await _ensure_reactions_table()

    async with get_db() as db:
        async with db.execute(
            "SELECT reaction FROM movie_reactions WHERE user_id = ? AND movie_id = ?",
            (call.from_user.id, movie_id)
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            if existing[0] == reaction:
                await call.answer(
                    txt("Siz allaqachon bu reaksiyani qoldirdingiz!",
                        "Вы уже оставили эту реакцию!", lang),
                    show_alert=False
                )
                return
            await db.execute(
                "UPDATE movie_reactions SET reaction = ? WHERE user_id = ? AND movie_id = ?",
                (reaction, call.from_user.id, movie_id)
            )
        else:
            await db.execute(
                "INSERT INTO movie_reactions (user_id, movie_id, reaction) VALUES (?, ?, ?)",
                (call.from_user.id, movie_id, reaction)
            )
        await db.commit()

        async with db.execute(
            "SELECT COUNT(*) FROM movie_reactions WHERE movie_id = ? AND reaction = 'like'",
            (movie_id,)
        ) as cur:
            likes = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM movie_reactions WHERE movie_id = ? AND reaction = 'dislike'",
            (movie_id,)
        ) as cur:
            dislikes = (await cur.fetchone())[0]

    emoji = "👍" if is_like else "👎"
    await call.answer(
        txt(f"{emoji} Rahmat! 👍{likes} 👎{dislikes}",
            f"{emoji} Спасибо! 👍{likes} 👎{dislikes}", lang),
        show_alert=False
    )


# ══════════════════════════════════════════════════════════════════════
#  ❤️ SEVIMLILARGA QO'SHISH / OLIB TASHLASH
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data.startswith("fav_toggle_"))
async def fav_toggle_movie(call: CallbackQuery):
    # "fav_toggle_123" → split("_", 2) → ["fav", "toggle", "123"]
    movie_id = int(call.data.split("_", 2)[2])
    user_id = call.from_user.id
    user = await get_user(user_id)
    lang = user["lang"] if user else "uz"

    async with get_db() as db:
        # Avval barcha duplicate qatorlarni tozalaymiz (eski xato yozuvlar)
        await db.execute(
            """DELETE FROM favorites
               WHERE id NOT IN (
                   SELECT MIN(id) FROM favorites
                   WHERE user_id = ? AND movie_id = ?
               )
               AND user_id = ? AND movie_id = ?""",
            (user_id, movie_id, user_id, movie_id)
        )

        async with db.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND movie_id = ?",
            (user_id, movie_id)
        ) as cur:
            exists = await cur.fetchone()

        if exists:
            await db.execute(
                "DELETE FROM favorites WHERE user_id = ? AND movie_id = ?",
                (user_id, movie_id)
            )
            msg = txt("💔 Sevimlilardan olib tashlandi!", "💔 Удалено из избранного!", lang)
        else:
            await db.execute(
                "INSERT INTO favorites (user_id, movie_id) VALUES (?, ?)",
                (user_id, movie_id)
            )
            msg = txt("❤️ Sevimlilarga qo'shildi!", "❤️ Добавлено в избранное!", lang)
        await db.commit()

    await call.answer(msg, show_alert=True)


@router.callback_query(F.data.startswith("fav_series_"))
async def fav_toggle_series(call: CallbackQuery):
    # "fav_series_123" → split("_", 2) → ["fav", "series", "123"]
    series_id = int(call.data.split("_", 2)[2])
    user_id = call.from_user.id
    user = await get_user(user_id)
    lang = user["lang"] if user else "uz"

    async with get_db() as db:
        # Avval barcha duplicate qatorlarni tozalaymiz (eski xato yozuvlar)
        await db.execute(
            """DELETE FROM favorites
               WHERE id NOT IN (
                   SELECT MIN(id) FROM favorites
                   WHERE user_id = ? AND series_id = ?
               )
               AND user_id = ? AND series_id = ?""",
            (user_id, series_id, user_id, series_id)
        )

        async with db.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND series_id = ?",
            (user_id, series_id)
        ) as cur:
            exists = await cur.fetchone()

        if exists:
            await db.execute(
                "DELETE FROM favorites WHERE user_id = ? AND series_id = ?",
                (user_id, series_id)
            )
            msg = txt("💔 Sevimlilardan olib tashlandi!", "💔 Удалено из избранного!", lang)
        else:
            await db.execute(
                "INSERT INTO favorites (user_id, series_id) VALUES (?, ?)",
                (user_id, series_id)
            )
            msg = txt("❤️ Sevimlilarga qo'shildi!", "❤️ Добавлено в избранное!", lang)
        await db.commit()

    await call.answer(msg, show_alert=True)
