"""
premium.py
──────────
Premium va to'lov handlerlari.

To'lov tizimi:
  - FAQAT karta + screenshot (manual)
  - Click va Payme o'chirilgan
  - Karta raqami va egasi — admin paneldan (settings jadvalidan) boshqariladi
  - Tarif narxlari — admin paneldan boshqariladi
"""

from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS
from bot.database.db import get_db
from bot.keyboards.user_kb import (
    main_menu, premium_tariffs_kb,
    admin_payment_kb,
)
from bot.utils.helpers import get_user, txt

router = Router()

# ── FSM ────────────────────────────────────────────────
class CardPayState(StatesGroup):
    waiting_receipt = State()
    payment_id      = State()

class PromoState(StatesGroup):
    waiting_code = State()

# ── Helpers ────────────────────────────────────────────

async def get_tariffs() -> list:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM tariffs WHERE is_active = 1 ORDER BY price"
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

async def get_setting(key: str, default: str = "") -> str:
    """settings jadvalidan qiymat oladi."""
    async with get_db() as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else default

async def activate_premium(user_id: int, days: int):
    async with get_db() as db:
        async with db.execute(
            "SELECT premium_until, is_premium FROM users WHERE tg_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()

        now = datetime.now()
        if row and row[1] and row[0]:
            try:
                current_until = datetime.strptime(row[0], "%Y-%m-%d")
                base = max(current_until, now)
            except Exception:
                base = now
        else:
            base = now

        new_until = (base + timedelta(days=days)).strftime("%Y-%m-%d")
        await db.execute(
            "UPDATE users SET is_premium = 1, premium_until = ? WHERE tg_id = ?",
            (new_until, user_id)
        )
        await db.commit()
    return new_until

# ════════════════════════════════════════════════════════
#  ⭐ PREMIUM KO'RSATISH
# ════════════════════════════════════════════════════════
@router.message(F.text.in_(["⭐ Premium", "⭐ Премиум"]))
@router.message(Command("premium"))
@router.callback_query(F.data == "show_premium")
async def show_premium(event: Message | CallbackQuery):
    user_id = event.from_user.id
    user = await get_user(user_id)
    lang = user["lang"] if user else "uz"
    tariffs = await get_tariffs()

    # Default tarifflar — bazada yo'q bo'lsa
    if not tariffs:
        async with get_db() as db:
            await db.executemany(
                "INSERT OR IGNORE INTO tariffs (name, duration, price, description) VALUES (?, ?, ?, ?)",
                [
                    ("Oylik",    30,  29900, "1 oylik premium obuna"),
                    ("3 Oylik",  90,  79900, "3 oylik — 10% chegirma"),
                    ("Yillik",  365, 249900, "1 yillik — 30% chegirma"),
                ]
            )
            await db.commit()
        tariffs = await get_tariffs()

    if user and user["is_premium"]:
        status_text = txt(
            f"✅ Sizda hozir <b>Premium</b> faol!\n"
            f"📅 Muddat: <b>{user['premium_until']}</b>\n\n"
            f"Uzaytirish uchun tarif tanlang:",
            f"✅ У вас активен <b>Premium</b>!\n"
            f"📅 До: <b>{user['premium_until']}</b>\n\n"
            f"Для продления выберите тариф:",
            lang
        )
    else:
        status_text = txt(
            "⭐ <b>Premium obuna</b>\n\n"
            "Premium afzalliklari:\n"
            "🎬 Barcha kinolar ochiq\n"
            "💬 Izoh qoldirish\n"
            "📥 Yuklab olish\n"
            "🚫 Reklama yo'q\n\n"
            "Tarif tanlang:",
            "⭐ <b>Premium подписка</b>\n\n"
            "Преимущества Premium:\n"
            "🎬 Все фильмы доступны\n"
            "💬 Комментарии\n"
            "📥 Скачивание\n"
            "🚫 Без рекламы\n\n"
            "Выберите тариф:",
            lang
        )

    kb = premium_tariffs_kb(tariffs, lang)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(status_text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(status_text, reply_markup=kb, parse_mode="HTML")


# ── Tarif tanlash ──────────────────────────────────────
@router.callback_query(F.data.startswith("buy_tariff_"))
async def buy_tariff(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split("_")[2])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with get_db() as db:
        async with db.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                await call.answer("❌ Tarif topilmadi!", show_alert=True)
                return
            tariff = dict(zip([d[0] for d in cur.description], row))

    # Karta ma'lumotlarini DB dan olish
    card_number = await get_setting("card_number", "0000 0000 0000 0000")
    card_owner  = await get_setting("card_owner",  "Bot Admin")

    async with get_db() as db:
        async with db.execute(
            """INSERT INTO payments (user_id, tariff_id, amount, method)
               VALUES (?, ?, ?, 'card') RETURNING id""",
            (call.from_user.id, tariff_id, tariff["price"])
        ) as cur:
            payment_id = (await cur.fetchone())[0]
        await db.commit()

    await state.update_data(payment_id=payment_id)
    await state.set_state(CardPayState.waiting_receipt)

    text = txt(
        f"💳 <b>Karta orqali to'lov</b>\n\n"
        f"⭐ Tarif: <b>{tariff['name']}</b>\n"
        f"📅 Muddat: {tariff['duration']} kun\n"
        f"💰 Summa: <b>{tariff['price']:,} so'm</b>\n\n"
        f"Quyidagi kartaga o'tkazing:\n"
        f"<code>{card_number}</code>\n"
        f"👤 {card_owner}\n\n"
        f"To'lovdan so'ng <b>chek (screenshot)</b> yuboring:",
        f"💳 <b>Оплата картой</b>\n\n"
        f"⭐ Тариф: <b>{tariff['name']}</b>\n"
        f"📅 Срок: {tariff['duration']} дней\n"
        f"💰 Сумма: <b>{tariff['price']:,} сум</b>\n\n"
        f"Переведите на карту:\n"
        f"<code>{card_number}</code>\n"
        f"👤 {card_owner}\n\n"
        f"После оплаты отправьте <b>чек (скриншот)</b>:",
        lang
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="show_premium")],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.message(CardPayState.waiting_receipt)
async def card_receipt_received(message: Message, state: FSMContext):
    data = await state.get_data()
    payment_id = data.get("payment_id")
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    if not (message.photo or message.document):
        text = txt(
            "🖼 Iltimos chek rasmini yuboring!",
            "🖼 Пожалуйста отправьте скриншот чека!",
            lang
        )
        await message.answer(text)
        return

    await state.clear()

    # Summa ma'lumotini DB dan olish
    amount_text = ""
    if payment_id:
        async with get_db() as db:
            async with db.execute(
                "SELECT p.amount, t.name FROM payments p LEFT JOIN tariffs t ON p.tariff_id = t.id WHERE p.id = ?",
                (payment_id,)
            ) as cur:
                prow = await cur.fetchone()
        if prow:
            amount_text = f"\n💰 Summa: {prow[0]:,} so'm | Tarif: {prow[1] or '—'}"

    caption = (
        f"💳 <b>Karta to'lov cheki</b>\n\n"
        f"👤 {message.from_user.full_name} (<code>{message.from_user.id}</code>)\n"
        f"🔑 Payment ID: {payment_id}"
        f"{amount_text}"
    )
    for admin_id in ADMINS:
        try:
            if message.photo:
                await message.bot.send_photo(
                    admin_id, message.photo[-1].file_id,
                    caption=caption,
                    reply_markup=admin_payment_kb(payment_id, message.from_user.id),
                    parse_mode="HTML"
                )
            else:
                await message.bot.send_document(
                    admin_id, message.document.file_id,
                    caption=caption,
                    reply_markup=admin_payment_kb(payment_id, message.from_user.id),
                    parse_mode="HTML"
                )
        except Exception:
            pass

    text = txt(
        "✅ Chekingiz qabul qilindi! Admin tekshirib, 30 daqiqa ichida faollashtiradi.",
        "✅ Ваш чек принят! Администратор проверит и активирует в течение 30 минут.",
        lang
    )
    await message.answer(text, reply_markup=main_menu(lang))


# ════════════════════════════════════════════════════════
#  👑 ADMIN — TO'LOV TASDIQLASH / RAD ETISH
# ════════════════════════════════════════════════════════
@router.callback_query(F.data.startswith("confirm_pay_"))
async def confirm_payment(call: CallbackQuery):
    parts = call.data.split("_")
    payment_id, user_id = int(parts[2]), int(parts[3])

    async with get_db() as db:
        async with db.execute(
            "SELECT p.*, t.duration FROM payments p LEFT JOIN tariffs t ON p.tariff_id = t.id WHERE p.id = ?",
            (payment_id,)
        ) as cur:
            row = await cur.fetchone()
            payment = dict(zip([d[0] for d in cur.description], row))

        await db.execute(
            "UPDATE payments SET status = 'paid', paid_at = datetime('now') WHERE id = ?",
            (payment_id,)
        )
        await db.commit()

    days = payment.get("duration") or 30
    new_until = await activate_premium(user_id, days)

    user = await get_user(user_id)
    lang = user["lang"] if user else "uz"

    try:
        await call.bot.send_message(
            user_id,
            txt(
                f"🎉 <b>Premium faollashtirildi!</b>\n\n"
                f"📅 Muddat: <b>{new_until}</b>\n"
                f"Barcha kinolar endi ochiq! 🎬",
                f"🎉 <b>Premium активирован!</b>\n\n"
                f"📅 До: <b>{new_until}</b>\n"
                f"Все фильмы теперь доступны! 🎬",
                lang
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    edit_text = f"✅ To'lov tasdiqlandi! Premium {new_until} gacha."
    if call.message.caption:
        await call.message.edit_caption(caption=edit_text)
    else:
        await call.message.edit_text(edit_text)


@router.callback_query(F.data.startswith("reject_pay_"))
async def reject_payment(call: CallbackQuery):
    parts = call.data.split("_")
    payment_id, user_id = int(parts[2]), int(parts[3])

    async with get_db() as db:
        await db.execute(
            "UPDATE payments SET status = 'rejected' WHERE id = ?", (payment_id,)
        )
        await db.commit()

    user = await get_user(user_id)
    lang = user["lang"] if user else "uz"

    try:
        await call.bot.send_message(
            user_id,
            txt(
                "❌ To'lovingiz rad etildi. Muammo bo'lsa /support yozing.",
                "❌ Ваш платёж отклонён. При проблемах напишите /support.",
                lang
            )
        )
    except Exception:
        pass

    edit_text = "❌ To'lov rad etildi."
    if call.message.caption:
        await call.message.edit_caption(caption=edit_text)
    else:
        await call.message.edit_text(edit_text)


# ════════════════════════════════════════════════════════
#  🎫 PROMOKOD
# ════════════════════════════════════════════════════════
@router.message(Command("promo"))
async def promo_start(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"
    await message.answer(txt("🎫 Promokodingizni kiriting:", "🎫 Введите ваш промокод:", lang))
    await state.set_state(PromoState.waiting_code)

@router.message(PromoState.waiting_code)
async def promo_check(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"
    code = (message.text or "").strip().upper()

    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM promo_codes
               WHERE code = ? AND uses_left > 0
               AND (expires_at IS NULL OR expires_at > datetime('now'))""",
            (code,)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            await state.clear()
            await message.answer(
                txt("❌ Promokod noto'g'ri yoki muddati tugagan!", "❌ Промокод неверный или истёк!", lang)
            )
            return

        promo = dict(zip([d[0] for d in cur.description], row))

        # Foydalanuvchi bu promokodni ishlatganmi tekshiramiz
        # Alohida promo_uses jadvalidan tekshiramiz (user_tasks hack emas)
        async with db.execute(
            "SELECT 1 FROM promo_uses WHERE promo_id = ? AND user_id = ?",
            (promo["id"], message.from_user.id)
        ) as cur:
            used = await cur.fetchone()

        if used:
            await state.clear()
            await message.answer(txt("❌ Bu promokodni allaqachon ishlatgansiz!", "❌ Вы уже использовали этот промокод!", lang))
            return

        if promo["type"] == "premium":
            days = promo["value"]
            new_until = await activate_premium(message.from_user.id, days)
            result_text = txt(
                f"🎉 <b>{days} kunlik Premium faollashtirildi!</b>\nMuddat: {new_until}",
                f"🎉 <b>Premium на {days} дней активирован!</b>\nДо: {new_until}",
                lang
            )
        elif promo["type"] == "balance":
            amount = promo["value"]
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE tg_id = ?",
                (amount, message.from_user.id)
            )
            result_text = txt(
                f"💰 <b>{amount} ball hisobingizga qo'shildi!</b>",
                f"💰 <b>{amount} баллов добавлено на счёт!</b>",
                lang
            )
        else:
            result_text = "✅ Promokod qabul qilindi."

        # promo_uses jadvaliga yozamiz (haqiqiy kuzatish)
        await db.execute(
            "INSERT OR IGNORE INTO promo_uses (promo_id, user_id) VALUES (?, ?)",
            (promo["id"], message.from_user.id)
        )
        await db.execute(
            "UPDATE promo_codes SET uses_left = uses_left - 1 WHERE id = ?",
            (promo["id"],)
        )
        await db.commit()

    await state.clear()
    await message.answer(result_text, reply_markup=main_menu(lang), parse_mode="HTML")


# ════════════════════════════════════════════════════════
#  ⏰ PREMIUM ESLATMA (scheduler tomonidan chaqiriladi)
# ════════════════════════════════════════════════════════
async def send_premium_reminders(bot) -> None:
    import logging
    logger = logging.getLogger(__name__)

    async with get_db() as db:
        for days_left in [3, 1]:
            target_date = (datetime.now() + timedelta(days=days_left)).strftime("%Y-%m-%d")
            async with db.execute(
                """SELECT tg_id, lang, premium_until FROM users
                   WHERE is_premium = 1 AND premium_until = ? AND notify = 1""",
                (target_date,)
            ) as cur:
                users = await cur.fetchall()

            sent = 0
            for (tg_id, lang, until) in users:
                text = txt(
                    f"⚠️ <b>Premium eslatma</b>\n\n"
                    f"Sizning Premium obunangiz <b>{days_left} kun</b> ichida tugaydi!\n"
                    f"📅 Muddat: {until}\n\nUzaytirish uchun /premium yozing.",
                    f"⚠️ <b>Напоминание о Premium</b>\n\n"
                    f"Ваша Premium подписка истекает через <b>{days_left} дня</b>!\n"
                    f"📅 До: {until}\n\nДля продления напишите /premium.",
                    lang
                )
                try:
                    await bot.send_message(tg_id, text, parse_mode="HTML")
                    sent += 1
                except Exception:
                    pass

            if users:
                logger.info("Premium eslatma: %d kun qoldi — %d/%d ga yuborildi.", days_left, sent, len(users))


async def deactivate_expired_premium(bot=None) -> None:
    import logging
    logger = logging.getLogger(__name__)
    today = datetime.now().strftime("%Y-%m-%d")

    async with get_db() as db:
        async with db.execute(
            "SELECT tg_id, lang FROM users WHERE is_premium = 1 AND premium_until < ?",
            (today,)
        ) as cur:
            expired_users = await cur.fetchall()

        if not expired_users:
            return

        await db.execute(
            "UPDATE users SET is_premium = 0, premium_until = NULL WHERE is_premium = 1 AND premium_until < ?",
            (today,)
        )
        await db.commit()

    logger.info("Premium muddati tugadi: %d foydalanuvchi deaktivatsiya.", len(expired_users))

    if bot is None:
        return

    for (tg_id, lang) in expired_users:
        text = txt(
            "😔 <b>Premium obunangiz tugadi.</b>\n\nDavom ettirish uchun /premium yozing.",
            "😔 <b>Ваша Premium подписка закончилась.</b>\n\nДля продления напишите /premium.",
            lang
        )
        try:
            await bot.send_message(tg_id, text, parse_mode="HTML")
        except Exception:
            pass


# ── Premiumni bekor qilish ─────────────────────────────
@router.callback_query(F.data == "cancel_premium")
async def cancel_premium(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    await call.message.edit_text(
        txt("❌ Bekor qilindi.", "❌ Отменено.", lang)
    )
    await call.answer()



# ════════════════════════════════════════════════════════
#  💰 BALLGA PREMIUM SOTIB OLISH  (#8)
# ════════════════════════════════════════════════════════
#
# Tarif jadvalida points_price ustuni bor (migration qo'shdi).
# Admin sozlamalardan har tarif uchun ball narxini belgilaydi.
# points_price = 0 bo'lsa — ballar bilan sotib bo'lmaydi.
#
# Flow:
#   show_premium → "💰 Balldan sotib olish" tugmasi
#   → buy_with_points_list → tarif tanlash
#   → buy_with_points_{tariff_id} → balans tekshiruvi → faollashtirish

@router.callback_query(F.data == "buy_with_points_list")
async def buy_with_points_list(call: CallbackQuery):
    """Ball bilan sotib olish uchun tarif ro'yxati."""
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    balance = user["balance"] if user else 0

    tariffs = await get_tariffs()
    # Faqat points_price > 0 bo'lganlarni ko'rsatamiz
    point_tariffs = [t for t in tariffs if t.get("points_price", 0) > 0]

    if not point_tariffs:
        await call.answer(
            txt(
                "❌ Hozircha ballga sotib bo'lmaydi.",
                "❌ Пока недоступно.",
                lang
            ),
            show_alert=True
        )
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for t in point_tariffs:
        pts = t["points_price"]
        has_enough = balance >= pts
        emoji = "✅" if has_enough else "❌"
        label = (
            f"{emoji} {t['name']} — {pts:,} ball ({t['duration']} kun)"
            if lang == "uz" else
            f"{emoji} {t['name']} — {pts:,} баллов ({t['duration']} дн.)"
        )
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"buy_with_points_{t['id']}"
        )])

    back = "◀️ Orqaga" if lang == "uz" else "◀️ Назад"
    buttons.append([InlineKeyboardButton(text=back, callback_data="show_premium")])

    balance_text = (
        f"💰 Sizning balansingiz: <b>{balance:,} ball</b>"
        if lang == "uz" else
        f"💰 Ваш баланс: <b>{balance:,} баллов</b>"
    )

    await call.message.edit_text(
        balance_text + "\n\n" + (
            "Tarif tanlang:"
            if lang == "uz" else
            "Выберите тариф:"
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("buy_with_points_") & ~F.data.in_({"buy_with_points_list"}))
async def buy_with_points_confirm(call: CallbackQuery):
    """Balldan to'lov — tasdiqlash va faollashtirish."""
    tariff_id = int(call.data.split("_")[3])
    user = await get_user(call.from_user.id)
    lang = user["lang"] if user else "uz"
    balance = user["balance"] if user else 0

    async with get_db() as db:
        async with db.execute(
            "SELECT id, name, duration, points_price FROM tariffs WHERE id = ?",
            (tariff_id,)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await call.answer(txt("❌ Tarif topilmadi!", "❌ Тариф не найден!", lang), show_alert=True)
        return

    tid, name, duration, points_price = row

    if points_price <= 0:
        await call.answer(
            txt("❌ Bu tarif ballar bilan sotib bo'lmaydi!", "❌ Этот тариф нельзя купить баллами!", lang),
            show_alert=True
        )
        return

    if balance < points_price:
        shortage = points_price - balance
        await call.answer(
            txt(
                f"❌ Balansingiz yetarli emas! {shortage:,} ball kam.",
                f"❌ Недостаточно баллов! Не хватает {shortage:,}.",
                lang
            ),
            show_alert=True
        )
        return

    # Balansdan ayirish va premiumni faollashtirish
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET balance = balance - ? WHERE tg_id = ?",
            (points_price, call.from_user.id)
        )
        await db.execute(
            "INSERT INTO point_log (user_id, amount, reason) VALUES (?, ?, 'premium_purchase')",
            (call.from_user.id, -points_price)
        )
        await db.execute(
            """INSERT INTO payments (user_id, tariff_id, amount, method, status, paid_at)
               VALUES (?, ?, ?, 'points', 'paid', datetime('now'))""",
            (call.from_user.id, tariff_id, points_price)
        )
        await db.commit()

    new_until = await activate_premium(call.from_user.id, duration)

    await call.message.edit_text(
        txt(
            f"🎉 <b>Premium faollashtirildi!</b>\n\n"
            f"⭐ Tarif: {name}\n"
            f"📅 Muddat: {new_until}\n"
            f"💰 Sarflangan: {points_price:,} ball",
            f"🎉 <b>Premium активирован!</b>\n\n"
            f"⭐ Тариф: {name}\n"
            f"📅 До: {new_until}\n"
            f"💰 Потрачено: {points_price:,} баллов",
            lang
        ),
        parse_mode="HTML"
    )
    await call.answer()
