from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS
from bot.database.db import get_db
from bot.keyboards.user_kb import (
    main_menu, profile_kb, lang_kb,
    notify_kb, back_kb
)

router = Router()


# ══════════════════════════════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════════════════════════════
class RequestState(StatesGroup):
    waiting_text = State()

class SupportState(StatesGroup):
    waiting_text = State()


# ══════════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════════════════════════════════
async def get_user(tg_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE tg_id = ?", (tg_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
    return None


def txt(uz: str, ru: str, lang: str) -> str:
    return uz if lang == "uz" else ru


def _premium_label(user: dict, lang: str) -> str:
    """Premium statusini formatlangan matn ko'rinishida qaytaradi."""
    if user.get("is_premium"):
        until = user.get("premium_until") or "?"
        return f"⭐ Premium ({until})"
    return "❌ Yo'q" if lang == "uz" else "❌ Нет"


async def _profile_stats(tg_id: int) -> tuple[int, int]:
    """Ko'rilgan va sevimlilardagi jami sonini qaytaradi (kino + serial)."""
    async with get_db() as db:
        # BUG #1 FIX: watch_history faqat movies ga bog'liq edi.
        # Seriallar ham watch_history ga yozilishi kerak (movie_id = None bo'lganda).
        # Hozircha barcha yozuvlarni sanab beramiz (kino va serial birga).
        async with db.execute(
            "SELECT COUNT(*) FROM watch_history WHERE user_id = ?", (tg_id,)
        ) as cur:
            watched = (await cur.fetchone())[0]

        # BUG #2 FIX: favorites faqat movies ni ko'rsatar edi.
        # Endi movies + series birga sanalaadi.
        async with db.execute(
            "SELECT COUNT(*) FROM favorites WHERE user_id = ?", (tg_id,)
        ) as cur:
            favs = (await cur.fetchone())[0]

    return watched, favs


# ══════════════════════════════════════════════════════════════════════
#  /start — DEEP LINK HANDLERI
# ══════════════════════════════════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    # BUG #3 FIX: /start kelganda FSM holati tozalanmagan edi.
    # Agar foydalanuvchi so'rov yoki support yozayotgan bo'lsa,
    # deep link orqali /start bosganida eski holat qolib ketar edi.
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

                # BUG #4 FIX: row None bo'lishi mumkin (yangi user hali saqlanmagan).
                # AuthMiddleware allaqachon userni yaratgan bo'lishi kerak, lekin
                # agar row None bo'lsa xato chiqar edi.
                if row is not None and row[0] is None:
                    await db.execute(
                        "UPDATE users SET referred_by = ? WHERE tg_id = ?",
                        (inviter[0], message.from_user.id)
                    )
                    await db.execute(
                        "UPDATE users SET balance = balance + 50 WHERE tg_id = ?",
                        (inviter[0],)
                    )
                    await db.commit()

        # Referral bo'lsa ham greeting ko'rsatilsin — return qilmaymiz

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
async def _send_movie_by_code(message: Message, code: str, lang: str = "uz"):
    """Kino kodiga ko'ra filmni yuboradi va ko'rishlar sonini oshiradi."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM movies WHERE code = ?", (code,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                await message.answer(
                    txt("❌ Kontent topilmadi!", "❌ Контент не найден!", lang)
                )
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

    # BUG #5 FIX: Premium kino tekshiruvi yo'q edi — hamma ko'ra olar edi.
    if m.get("is_premium"):
        user = await get_user(message.from_user.id)
        if not (user and user.get("is_premium")):
            await message.answer(
                txt(
                    "⭐ Bu kontent faqat <b>Premium</b> foydalanuvchilar uchun!\n\n"
                    "Premium olish uchun: /start premium",
                    "⭐ Этот контент только для <b>Premium</b> пользователей!\n\n"
                    "Получить Premium: /start premium",
                    lang
                ),
                parse_mode="HTML"
            )
            return

    title = m.get("title_uz") or m.get("title") or "Nomsiz kino"
    caption = (
        f"🎬 <b>{title}</b> ({m.get('year', '?')})\n"
        f"🎭 {m.get('genres') or m.get('genre', '')}\n"
        f"🌍 {m.get('country', '')}\n\n"
        f"🍿 {m.get('description', '')}"
    )

    # BUG #6 FIX: views yangilanishi va watch_history yozuvi alohida DB
    # ulanishida edi — endi bitta tranzaksiyada bajariladi.
    async with get_db() as db:
        await db.execute(
            "UPDATE movies SET views = views + 1 WHERE id = ?", (m["id"],)
        )
        await db.execute(
            "INSERT INTO watch_history (user_id, movie_id) VALUES (?, ?)",
            (message.from_user.id, m["id"])
        )
        await db.commit()

    # BUG #7 FIX: file_id None bo'lsa answer_video xato berar edi.
    if not m.get("file_id"):
        await message.answer(
            txt("❌ Video fayli topilmadi!", "❌ Видеофайл не найден!", lang)
        )
        return

    await message.answer_video(
        video=m["file_id"],
        caption=caption,
        parse_mode="HTML"
    )


async def _send_series_by_code(message: Message, code: str, lang: str = "uz"):
    """Serial kodiga ko'ra serial ma'lumotini (fasllar tugmasi bilan) yuboradi."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM series WHERE code = ?", (code,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                await message.answer(
                    txt("❌ Serial topilmadi!", "❌ Сериал не найден!", lang)
                )
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

    # BUG #5 FIX: Premium serial tekshiruvi yo'q edi.
    if s.get("is_premium"):
        user = await get_user(message.from_user.id)
        if not (user and user.get("is_premium")):
            await message.answer(
                txt(
                    "⭐ Bu serial faqat <b>Premium</b> foydalanuvchilar uchun!\n\n"
                    "Premium olish uchun: /start premium",
                    "⭐ Этот сериал только для <b>Premium</b> пользователей!\n\n"
                    "Получить Premium: /start premium",
                    lang
                ),
                parse_mode="HTML"
            )
            return

    # BUG #8 FIX: seasons bo'sh bo'lsa inline_keyboard bo'sh qolardi
    # va Telegram xato berar edi.
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

    title    = s.get("title_uz") or "Nomsiz serial"
    year     = s.get("year") or "?"
    genres   = s.get("genres") or "—"
    country  = s.get("country") or "—"
    desc     = s.get("description") or ""
    caption = (
        f"📺 <b>{title}</b> ({year})\n"
        f"🎭 Janr: {genres}\n"
        f"🌍 Davlat: {country}\n\n"
        f"🍿 {desc}\n\n"
        f"👇 {'Faslni tanlang:' if lang == 'uz' else 'Выберите сезон:'}"
    )

    # BUG #9 FIX: poster_file_id None bo'lsa answer_photo xato berar edi.
    if s.get("poster_file_id"):
        await message.answer_photo(
            photo=s["poster_file_id"],
            caption=caption,
            reply_markup=kb,
            parse_mode="HTML"
        )
    else:
        await message.answer(caption, reply_markup=kb, parse_mode="HTML")


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

    text = txt(
        f"👤 <b>Profil</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👨 Ism: {user['full_name']}\n"
        f"🌐 Til: {'O\'zbek 🇺🇿' if lang == 'uz' else 'Русский 🇷🇺'}\n"
        f"⭐ Premium: {premium_status}\n"
        f"💰 Balans: {user['balance']} ball\n\n"
        f"📊 <b>Statistika</b>\n"
        f"🎬 Ko'rilgan: {watched} ta\n"
        f"❤️ Sevimlilar: {favs} ta\n"
        f"👥 Referral kodi: <code>{user['referral_code']}</code>",

        f"👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👨 Имя: {user['full_name']}\n"
        f"🌐 Язык: {'O\'zbek 🇺🇿' if lang == 'uz' else 'Русский 🇷🇺'}\n"
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
    await call.answer(msg)
    # BUG #10 FIX: delete() dan keyin answer() chaqirish xato edi —
    # delete bo'lgandan keyin message mavjud emas. Tartib: avval answer, keyin delete.
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
#  SEVIMLILAR — BUG #2 FIX: movies + series birga ko'rsatiladi
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "favorites")
async def show_favorites(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer()
        return
    lang = user["lang"]

    async with get_db() as db:
        # Filmlar
        async with db.execute(
            """SELECT COALESCE(m.title_uz, m.title, 'Nomsiz') AS title,
                      m.code, 'movie' AS content_type
               FROM favorites f
               JOIN movies m ON f.movie_id = m.id
               WHERE f.user_id = ? AND m.status = 'active'
               ORDER BY f.added_at DESC LIMIT 10""",
            (user["tg_id"],)
        ) as cur:
            movie_rows = await cur.fetchall()

        # Seriallar — series_id ustuni migration orqali qo'shilgan
        async with db.execute(
            """SELECT COALESCE(s.title_uz, 'Nomsiz serial') AS title,
                      s.code, 'series' AS content_type
               FROM favorites f
               JOIN series s ON f.series_id = s.id
               WHERE f.user_id = ? AND s.status = 'active'
               ORDER BY f.added_at DESC LIMIT 10""",
            (user["tg_id"],)
        ) as cur:
            series_rows = await cur.fetchall()

    all_items = list(movie_rows) + list(series_rows)

    if not all_items:
        text = txt("❤️ Sevimlilar bo'sh.", "❤️ Избранное пусто.", lang)
        await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
        await call.answer()
        return

    lines = []
    for title, code, ctype in all_items:
        icon = "🎬" if ctype == "movie" else "📺"
        lines.append(f"{icon} <code>{code}</code> — {title}")

    hint = txt(
        "Kino/serial kodini yuboring — bot ko'rsatadi.",
        "Отправьте код фильма/сериала — бот покажет.",
        lang
    )
    text = txt(
        f"❤️ <b>Sevimlilar</b>\n\n" + "\n".join(lines) + f"\n\n{hint}",
        f"❤️ <b>Избранное</b>\n\n" + "\n".join(lines) + f"\n\n{hint}",
        lang
    )
    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
    await call.answer()


# ══════════════════════════════════════════════════════════════════════
#  KO'RISH TARIXI — BUG #1 FIX: title_uz → COALESCE(title_uz, title)
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "history")
async def watch_history(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer()
        return
    lang = user["lang"]

    async with get_db() as db:
        # Filmlar ko'rish tarixi
        async with db.execute(
            """SELECT 'movie' AS type,
                      COALESCE(m.title_uz, m.title, 'Nomsiz') AS title,
                      h.watched_at
               FROM watch_history h
               JOIN movies m ON h.movie_id = m.id
               WHERE h.user_id = ? AND h.movie_id IS NOT NULL
               ORDER BY h.watched_at DESC LIMIT 10""",
            (user["tg_id"],)
        ) as cur:
            movie_rows = await cur.fetchall()

        # Seriallar ko'rish tarixi
        async with db.execute(
            """SELECT 'series' AS type,
                      COALESCE(s.title_uz, 'Nomsiz serial') AS title,
                      h.watched_at,
                      h.season_number,
                      h.episode_number
               FROM watch_history h
               JOIN series s ON h.series_id = s.id
               WHERE h.user_id = ? AND h.series_id IS NOT NULL
               ORDER BY h.watched_at DESC LIMIT 10""",
            (user["tg_id"],)
        ) as cur:
            series_rows = await cur.fetchall()

    lines = []
    for r in movie_rows:
        lines.append(f"🎬 {r[1]} <i>({r[2][:10]})</i>")
    for r in series_rows:
        s_ep = f"{r[3]}-fasl {r[4]}-qism" if r[3] and r[4] else ""
        lines.append(f"📺 {r[1]} {s_ep} <i>({r[2][:10]})</i>")

    # Vaqt bo'yicha saralash (ikki ro'yxat birga)
    if not lines:
        text = txt("📜 Tarix bo'sh.", "📜 История пуста.", lang)
    else:
        joined = "\n".join(lines[:20])
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
        )
    )
    await state.set_state(RequestState.waiting_text)


@router.message(RequestState.waiting_text)
async def movie_request_save(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    # BUG #11 FIX: message.text None bo'lishi mumkin (rasm, sticker yuborilsa).
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
        )
    )
    await state.set_state(SupportState.waiting_text)


@router.message(SupportState.waiting_text)
async def support_save(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    # BUG #11 FIX: matn bo'lmasa xato bo'lmasin.
    msg_text = message.text or "[Matn yo'q]"

    admin_text = (
        f"📞 <b>Support xabari</b>\n\n"
        f"👤 {message.from_user.full_name} "
        f"(<code>{message.from_user.id}</code>)\n"
        f"💬 {msg_text}"
    )
    for admin_id in ADMINS:
        try:
            await message.bot.send_message(admin_id, admin_text, parse_mode="HTML")
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
#  NOOP (hech narsa qilmaydigan tugmalar uchun)
# ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()
