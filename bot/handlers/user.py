from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import get_db
from bot.keyboards.user_kb import (
    main_menu, profile_kb, lang_kb,
    notify_kb, back_kb
)

router = Router()

# ── FSM ────────────────────────────────────────────────
class RequestState(StatesGroup):
    waiting_text = State()

class SupportState(StatesGroup):
    waiting_text = State()

# ── Helpers ────────────────────────────────────────────
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

# ── /start ─────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    # Referral tekshirish
    args = message.text.split()
    if len(args) > 1:
        ref_code = args[1]
        if ref_code.startswith("ref_"):
            code = ref_code[4:]
            async with get_db() as db:
                async with db.execute(
                    "SELECT tg_id FROM users WHERE referral_code = ?", (code,)
                ) as cur:
                    inviter = await cur.fetchone()
                if inviter and inviter[0] != message.from_user.id:
                    await db.execute(
                        "UPDATE users SET referred_by = ? WHERE tg_id = ?",
                        (inviter[0], message.from_user.id)
                    )
                    await db.execute(
                        "UPDATE users SET balance = balance + 50 WHERE tg_id = ?",
                        (inviter[0],)
                    )
                    await db.commit()

    # ── movie_ deep link — inline qidiruvdan kelgan ────────────────
    args_list = message.text.split() if message.text else []
    if len(args_list) > 1 and args_list[1].startswith("movie_"):
        code = args_list[1][6:]  # "movie_" ni olib tashlash
        from bot.handlers.inline_search import handle_movie_deeplink
        await handle_movie_deeplink(message, code)
        return

    # ── premium deep link ────────────────────────────────────────────
    if len(args_list) > 1 and args_list[1] == "premium":
        from bot.handlers.premium import show_premium
        await show_premium(message)
        return

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


# ── Profil ─────────────────────────────────────────────
@router.message(F.text.in_(["👤 Profil", "👤 Профиль"]))
async def show_profile(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return
    lang = user["lang"]

    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM watch_history WHERE user_id = ?", (user["tg_id"],)
        ) as cur:
            watched = (await cur.fetchone())[0]

        async with db.execute(
            "SELECT COUNT(*) FROM favorites WHERE user_id = ?", (user["tg_id"],)
        ) as cur:
            favorites = (await cur.fetchone())[0]

    premium_status = (
        f"⭐ Premium ({user['premium_until']})" if user["is_premium"]
        else ("❌ Yo'q" if lang == "uz" else "❌ Нет")
    )

    text = txt(
        f"👤 <b>Profil</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👨 Ism: {user['full_name']}\n"
        f"🌐 Til: {'O\'zbek 🇺🇿' if lang == 'uz' else 'Русский 🇷🇺'}\n"
        f"⭐ Premium: {premium_status}\n"
        f"💰 Balans: {user['balance']} ball\n\n"
        f"📊 <b>Statistika</b>\n"
        f"🎬 Ko'rilgan: {watched} ta\n"
        f"❤️ Sevimlilar: {favorites} ta\n"
        f"👥 Referral kodi: <code>{user['referral_code']}</code>",

        f"👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👨 Имя: {user['full_name']}\n"
        f"🌐 Язык: {'O\'zbek 🇺🇿' if lang == 'uz' else 'Русский 🇷🇺'}\n"
        f"⭐ Премиум: {premium_status}\n"
        f"💰 Баланс: {user['balance']} баллов\n\n"
        f"📊 <b>Статистика</b>\n"
        f"🎬 Просмотрено: {watched}\n"
        f"❤️ Избранное: {favorites}\n"
        f"👥 Реферальный код: <code>{user['referral_code']}</code>",
        lang
    )

    await message.answer(text, reply_markup=profile_kb(lang), parse_mode="HTML")


# ── Til o'zgartirish ───────────────────────────────────
@router.callback_query(F.data == "change_lang")
async def change_lang(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    text = txt("🌐 Tilni tanlang:", "🌐 Выберите язык:", lang)
    await call.message.edit_text(text, reply_markup=lang_kb())

@router.callback_query(F.data.startswith("set_lang_"))
async def set_lang(call: CallbackQuery):
    new_lang = call.data.split("_")[-1]
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET lang = ? WHERE tg_id = ?",
            (new_lang, call.from_user.id)
        )
        await db.commit()

    msg = "✅ Til o'zgartirildi!" if new_lang == "uz" else "✅ Язык изменён!"
    await call.answer(msg)
    await call.message.delete()
    await call.message.answer(
        msg, reply_markup=main_menu(new_lang)
    )


# ── Bildirishnoma ──────────────────────────────────────
@router.callback_query(F.data == "notifications")
async def notifications(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"]
    text = txt("🔔 Bildirishnoma sozlamalari:", "🔔 Настройки уведомлений:", lang)
    await call.message.edit_text(text, reply_markup=notify_kb(user["notify"], lang))

@router.callback_query(F.data == "toggle_notify")
async def toggle_notify(call: CallbackQuery):
    user = await get_user(call.from_user.id)
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


# ── Tungi rejim ────────────────────────────────────────
@router.callback_query(F.data == "night_mode")
async def night_mode(call: CallbackQuery):
    user = await get_user(call.from_user.id)
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


# ── Referral ───────────────────────────────────────────
@router.callback_query(F.data == "referral")
async def referral(call: CallbackQuery):
    user = await get_user(call.from_user.id)
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


# ── Sevimlilar ─────────────────────────────────────────
@router.callback_query(F.data == "favorites")
async def favorites(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with get_db() as db:
        async with db.execute(
            """SELECT m.code, m.title FROM favorites f
               JOIN movies m ON f.movie_id = m.id
               WHERE f.user_id = ?
               ORDER BY f.added_at DESC LIMIT 10""",
            (user["tg_id"],)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        text = txt("❤️ Sevimlilar bo'sh.", "❤️ Избранное пусто.", lang)
    else:
        lines = "\n".join([f"🎬 <code>{r[0]}</code> — {r[1]}" for r in rows])
        text = txt(
            f"❤️ <b>Sevimlilar</b>\n\n{lines}\n\n"
            "Kino kodini yuboring — bot ko'rsatadi.",
            f"❤️ <b>Избранное</b>\n\n{lines}\n\n"
            "Отправьте код фильма — бот покажет.",
            lang
        )

    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")


# ── Ko'rish tarixi ─────────────────────────────────────
@router.callback_query(F.data == "history")
async def watch_history(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with get_db() as db:
        async with db.execute(
            """SELECT m.code, m.title, h.watched_at FROM watch_history h
               JOIN movies m ON h.movie_id = m.id
               WHERE h.user_id = ?
               ORDER BY h.watched_at DESC LIMIT 10""",
            (user["tg_id"],)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        text = txt("📜 Tarix bo'sh.", "📜 История пуста.", lang)
    else:
        lines = "\n".join([f"🎬 <code>{r[0]}</code> — {r[1]} ({r[2][:10]})" for r in rows])
        text = txt(
            f"📜 <b>Ko'rish tarixi</b>\n\n{lines}",
            f"📜 <b>История просмотров</b>\n\n{lines}",
            lang
        )

    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")


# ── Kino so'rov ────────────────────────────────────────
@router.message(F.text.in_(["📋 So'rov", "📋 Запрос"]))
async def movie_request_start(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"]
    text = txt(
        "📋 Qaysi kino yoki serialni qo'shishimizni xohlaysiz?\n"
        "Nomi, yili va tilini yozing:",
        "📋 Какой фильм или сериал вы хотите добавить?\n"
        "Напишите название, год и язык:",
        lang
    )
    await message.answer(text)
    await state.set_state(RequestState.waiting_text)

@router.message(RequestState.waiting_text)
async def movie_request_save(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"]

    async with get_db() as db:
        await db.execute(
            "INSERT INTO movie_requests (user_id, text) VALUES (?, ?)",
            (message.from_user.id, message.text)
        )
        await db.commit()

    await state.clear()
    text = txt(
        "✅ So'rovingiz qabul qilindi! Tez orada ko'rib chiqamiz.",
        "✅ Ваш запрос принят! Рассмотрим в ближайшее время.",
        lang
    )
    await message.answer(text, reply_markup=main_menu(lang))


# ── Support ────────────────────────────────────────────
@router.message(F.text.in_(["📞 Support", "📞 Поддержка"]))
async def support_start(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"]
    text = txt(
        "📞 Muammoingizni yozing, adminlar tez orada javob beradi:",
        "📞 Опишите вашу проблему, администраторы ответят в ближайшее время:",
        lang
    )
    await message.answer(text)
    await state.set_state(SupportState.waiting_text)

@router.message(SupportState.waiting_text)
async def support_save(message: Message, state: FSMContext):
    from bot.config import ADMINS
    user = await get_user(message.from_user.id)
    lang = user["lang"]

    admin_text = (
        f"📞 <b>Support xabari</b>\n\n"
        f"👤 {message.from_user.full_name} "
        f"(<code>{message.from_user.id}</code>)\n"
        f"💬 {message.text}"
    )
    for admin_id in ADMINS:
        try:
            await message.bot.send_message(admin_id, admin_text, parse_mode="HTML")
        except Exception:
            pass

    await state.clear()
    text = txt(
        "✅ Xabaringiz adminga yuborildi!",
        "✅ Ваше сообщение отправлено администратору!",
        lang
    )
    await message.answer(text, reply_markup=main_menu(lang))


# ── Back to profile ────────────────────────────────────
@router.callback_query(F.data == "back_profile")
async def back_profile(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM watch_history WHERE user_id = ?", (user["tg_id"],)
        ) as cur:
            watched = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM favorites WHERE user_id = ?", (user["tg_id"],)
        ) as cur:
            favorites_count = (await cur.fetchone())[0]

    premium_status = (
        f"⭐ Premium ({user['premium_until']})" if user["is_premium"]
        else ("❌ Yo'q" if lang == "uz" else "❌ Нет")
    )

    text = txt(
        f"👤 <b>Profil</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👨 Ism: {user['full_name']}\n"
        f"⭐ Premium: {premium_status}\n"
        f"💰 Balans: {user['balance']} ball\n\n"
        f"📊 Ko'rilgan: {watched} | ❤️ Sevimlilar: {favorites_count}",

        f"👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"👨 Имя: {user['full_name']}\n"
        f"⭐ Премиум: {premium_status}\n"
        f"💰 Баланс: {user['balance']} баллов\n\n"
        f"📊 Просмотрено: {watched} | ❤️ Избранное: {favorites_count}",
        lang
    )
    await call.message.edit_text(text, reply_markup=profile_kb(lang), parse_mode="HTML")

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()
