from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import (
    ADMINS, CLICK_SERVICE_ID, CLICK_MERCHANT_ID,
    PAYME_MERCHANT_ID
)
from bot.database.db import get_db
from bot.keyboards.user_kb import (
    main_menu, premium_tariffs_kb, payment_method_kb,
    payment_confirm_kb, admin_payment_kb, back_kb
)

router = Router()

# ── FSM ────────────────────────────────────────────────
class CardPayState(StatesGroup):
    waiting_receipt = State()
    payment_id      = State()

class PromoState(StatesGroup):
    waiting_code = State()

# ── Helpers ────────────────────────────────────────────
async def get_user(tg_id: int) -> dict | None:
    async with await get_db() as db:
        async with db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(zip([d[0] for d in cur.description], row))
    return None

async def get_tariffs() -> list:
    async with await get_db() as db:
        async with db.execute(
            "SELECT * FROM tariffs WHERE is_active = 1 ORDER BY price"
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

async def activate_premium(user_id: int, days: int):
    async with await get_db() as db:
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

def txt(uz, ru, lang):
    return uz if lang == "uz" else ru


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
        async with await get_db() as db:
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
async def buy_tariff(call: CallbackQuery):
    tariff_id = int(call.data.split("_")[2])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with await get_db() as db:
        async with db.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                await call.answer("❌ Tarif topilmadi!", show_alert=True)
                return
            tariff = dict(zip([d[0] for d in cur.description], row))

    text = txt(
        f"⭐ <b>{tariff['name']}</b>\n\n"
        f"📅 Muddat: {tariff['duration']} kun\n"
        f"💰 Narx: {tariff['price']:,} so'm\n\n"
        f"To'lov usulini tanlang:",
        f"⭐ <b>{tariff['name']}</b>\n\n"
        f"📅 Срок: {tariff['duration']} дней\n"
        f"💰 Цена: {tariff['price']:,} сум\n\n"
        f"Выберите способ оплаты:",
        lang
    )
    await call.message.edit_text(text, reply_markup=payment_method_kb(tariff_id, lang), parse_mode="HTML")


# ════════════════════════════════════════════════════════
#  💳 CLICK TO'LOV
# ════════════════════════════════════════════════════════
@router.callback_query(F.data.startswith("pay_click_"))
async def pay_click(call: CallbackQuery):
    tariff_id = int(call.data.split("_")[2])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with await get_db() as db:
        async with db.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()
            tariff = dict(zip([d[0] for d in cur.description], row))

        # To'lov yozuvi yaratish
        async with db.execute(
            """INSERT INTO payments (user_id, tariff_id, amount, method)
               VALUES (?, ?, ?, 'click') RETURNING id""",
            (call.from_user.id, tariff_id, tariff["price"])
        ) as cur:
            payment_id = (await cur.fetchone())[0]
        await db.commit()

    # Click to'lov havolasi
    amount_tiyin = tariff["price"] * 100  # so'm → tiyin
    click_url = (
        f"https://my.click.uz/services/pay"
        f"?service_id={CLICK_SERVICE_ID}"
        f"&merchant_id={CLICK_MERCHANT_ID}"
        f"&amount={amount_tiyin}"
        f"&transaction_param={payment_id}"
        f"&return_url=https://t.me/{(await call.bot.get_me()).username}"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Click orqali to'lash", url=click_url)],
        [InlineKeyboardButton(text="✅ To'lovni tekshirish", callback_data=f"verify_click_{payment_id}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="show_premium")],
    ])

    text = txt(
        f"💳 <b>Click orqali to'lov</b>\n\n"
        f"💰 Summa: <b>{tariff['price']:,} so'm</b>\n"
        f"🔑 To'lov ID: <code>{payment_id}</code>\n\n"
        f"Tugmani bosib to'lovni amalga oshiring,\n"
        f"so'ng «✅ To'lovni tekshirish» tugmasini bosing.",
        f"💳 <b>Оплата через Click</b>\n\n"
        f"💰 Сумма: <b>{tariff['price']:,} сум</b>\n"
        f"🔑 ID платежа: <code>{payment_id}</code>\n\n"
        f"Нажмите кнопку для оплаты,\n"
        f"затем нажмите «✅ Проверить оплату».",
        lang
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("verify_click_"))
async def verify_click(call: CallbackQuery):
    payment_id = int(call.data.split("_")[2])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with await get_db() as db:
        async with db.execute(
            "SELECT * FROM payments WHERE id = ? AND user_id = ?",
            (payment_id, call.from_user.id)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                await call.answer("❌ To'lov topilmadi!", show_alert=True)
                return
            payment = dict(zip([d[0] for d in cur.description], row))

    if payment["status"] == "paid":
        await call.answer(
            txt("✅ To'lov allaqachon tasdiqlangan!", "✅ Оплата уже подтверждена!", lang),
            show_alert=True
        )
        return

    # Click API orqali tekshirish (sandbox uchun — real integratsiyada webhook ishlatiladi)
    # Hozircha admin tasdiqlashiga yo'naltiramiz
    text = txt(
        f"⏳ To'lovingiz tekshirilmoqda...\n"
        f"🔑 To'lov ID: <code>{payment_id}</code>\n\n"
        f"Agar to'lov o'tgan bo'lsa, 1-5 daqiqa ichida faollashadi.\n"
        f"Muammo bo'lsa /support yozing.",
        f"⏳ Ваш платёж проверяется...\n"
        f"🔑 ID: <code>{payment_id}</code>\n\n"
        f"Если оплата прошла, активация в течение 1-5 минут.\n"
        f"При проблемах напишите /support.",
        lang
    )
    await call.message.edit_text(text, parse_mode="HTML")

    # Adminlarga xabar
    for admin_id in ADMINS:
        try:
            await call.bot.send_message(
                admin_id,
                f"💳 <b>Click to'lov tekshiruvi</b>\n\n"
                f"👤 {call.from_user.full_name} (<code>{call.from_user.id}</code>)\n"
                f"💰 {payment['amount']:,} so'm\n"
                f"🔑 Payment ID: {payment_id}",
                reply_markup=admin_payment_kb(payment_id, call.from_user.id),
                parse_mode="HTML"
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════
#  💳 PAYME TO'LOV
# ════════════════════════════════════════════════════════
@router.callback_query(F.data.startswith("pay_payme_"))
async def pay_payme(call: CallbackQuery):
    tariff_id = int(call.data.split("_")[2])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with await get_db() as db:
        async with db.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()
            tariff = dict(zip([d[0] for d in cur.description], row))

        async with db.execute(
            """INSERT INTO payments (user_id, tariff_id, amount, method)
               VALUES (?, ?, ?, 'payme') RETURNING id""",
            (call.from_user.id, tariff_id, tariff["price"])
        ) as cur:
            payment_id = (await cur.fetchone())[0]
        await db.commit()

    import base64, json
    amount_tiyin = tariff["price"] * 100
    params = json.dumps({
        "m": PAYME_MERCHANT_ID,
        "ac.payment_id": str(payment_id),
        "a": amount_tiyin,
        "l": lang
    })
    encoded = base64.b64encode(params.encode()).decode()
    payme_url = f"https://checkout.paycom.uz/{encoded}"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Payme orqali to'lash", url=payme_url)],
        [InlineKeyboardButton(text="✅ To'lovni tekshirish", callback_data=f"verify_payme_{payment_id}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="show_premium")],
    ])

    text = txt(
        f"💳 <b>Payme orqali to'lov</b>\n\n"
        f"💰 Summa: <b>{tariff['price']:,} so'm</b>\n"
        f"🔑 To'lov ID: <code>{payment_id}</code>\n\n"
        f"Tugmani bosib to'lovni amalga oshiring,\n"
        f"so'ng «✅ To'lovni tekshirish» tugmasini bosing.",
        f"💳 <b>Оплата через Payme</b>\n\n"
        f"💰 Сумма: <b>{tariff['price']:,} сум</b>\n"
        f"🔑 ID платежа: <code>{payment_id}</code>\n\n"
        f"Нажмите кнопку для оплаты,\n"
        f"затем нажмите «✅ Проверить оплату».",
        lang
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("verify_payme_"))
async def verify_payme(call: CallbackQuery):
    payment_id = int(call.data.split("_")[2])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with await get_db() as db:
        async with db.execute(
            "SELECT * FROM payments WHERE id = ? AND user_id = ?",
            (payment_id, call.from_user.id)
        ) as cur:
            row = await cur.fetchone()
            payment = dict(zip([d[0] for d in cur.description], row))

    if payment["status"] == "paid":
        await call.answer(txt("✅ Allaqachon faollashgan!", "✅ Уже активировано!", lang), show_alert=True)
        return

    text = txt(
        f"⏳ Payme to'lovingiz tekshirilmoqda...\n🔑 ID: <code>{payment_id}</code>",
        f"⏳ Платёж Payme проверяется...\n🔑 ID: <code>{payment_id}</code>",
        lang
    )
    await call.message.edit_text(text, parse_mode="HTML")

    for admin_id in ADMINS:
        try:
            await call.bot.send_message(
                admin_id,
                f"💳 <b>Payme to'lov tekshiruvi</b>\n\n"
                f"👤 {call.from_user.full_name} (<code>{call.from_user.id}</code>)\n"
                f"💰 {payment['amount']:,} so'm\n"
                f"🔑 Payment ID: {payment_id}",
                reply_markup=admin_payment_kb(payment_id, call.from_user.id),
                parse_mode="HTML"
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════
#  💳 KARTA (MANUAL) TO'LOV
# ════════════════════════════════════════════════════════
@router.callback_query(F.data.startswith("pay_card_"))
async def pay_card(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split("_")[2])
    user = await get_user(call.from_user.id)
    lang = user["lang"]

    async with await get_db() as db:
        async with db.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()
            tariff = dict(zip([d[0] for d in cur.description], row))

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
        f"💰 Summa: <b>{tariff['price']:,} so'm</b>\n\n"
        f"Quyidagi kartaga o'tkazing:\n"
        f"<code>8600 1234 5678 9012</code>\n"
        f"👤 Abdullayev Sardor\n\n"
        f"To'lovdan so'ng chek (screenshot) yuboring:",
        f"💳 <b>Оплата картой</b>\n\n"
        f"💰 Сумма: <b>{tariff['price']:,} сум</b>\n\n"
        f"Переведите на карту:\n"
        f"<code>8600 1234 5678 9012</code>\n"
        f"👤 Abdullayev Sardor\n\n"
        f"После оплаты отправьте чек (скриншот):",
        lang
    )
    await call.message.edit_text(text, parse_mode="HTML")


@router.message(CardPayState.waiting_receipt)
async def card_receipt_received(message: Message, state: FSMContext):
    data = await state.get_data()
    payment_id = data["payment_id"]
    user = await get_user(message.from_user.id)
    lang = user["lang"]

    if not (message.photo or message.document):
        text = txt("🖼 Iltimos chek rasmini yuboring!", "🖼 Пожалуйста отправьте скриншот чека!", lang)
        await message.answer(text)
        return

    await state.clear()

    # Adminlarga chekni yuborish
    caption = (
        f"💳 <b>Karta to'lov cheki</b>\n\n"
        f"👤 {message.from_user.full_name} (<code>{message.from_user.id}</code>)\n"
        f"🔑 Payment ID: {payment_id}"
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
    _, _, payment_id, user_id = call.data.split("_")
    payment_id, user_id = int(payment_id), int(user_id)

    async with await get_db() as db:
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

    # Foydalanuvchiga xabar
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

    await call.message.edit_caption(
        caption=f"✅ To'lov tasdiqlandi! Premium {new_until} gacha.",
    ) if call.message.caption else await call.message.edit_text(
        f"✅ To'lov tasdiqlandi! Premium {new_until} gacha."
    )


@router.callback_query(F.data.startswith("reject_pay_"))
async def reject_payment(call: CallbackQuery):
    _, _, payment_id, user_id = call.data.split("_")
    payment_id, user_id = int(payment_id), int(user_id)

    async with await get_db() as db:
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

    await call.message.edit_text("❌ To'lov rad etildi.") if not call.message.caption \
        else await call.message.edit_caption(caption="❌ To'lov rad etildi.")


# ════════════════════════════════════════════════════════
#  🎫 PROMOKOD
# ════════════════════════════════════════════════════════
@router.message(Command("promo"))
async def promo_start(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"]
    text = txt(
        "🎫 Promokodingizni kiriting:",
        "🎫 Введите ваш промокод:",
        lang
    )
    await message.answer(text)
    await state.set_state(PromoState.waiting_code)

@router.message(PromoState.waiting_code)
async def promo_check(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user["lang"]
    code = message.text.strip().upper()

    async with await get_db() as db:
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

        # Promokod ishlatilganmi?
        async with db.execute(
            "SELECT 1 FROM user_tasks WHERE user_id = ? AND task_id = ?",
            (message.from_user.id, promo["id"] * -1)
        ) as cur:
            used = await cur.fetchone()

        if used:
            await state.clear()
            await message.answer(txt("❌ Bu promokodni allaqachon ishlatgansiz!", "❌ Вы уже использовали этот промокод!", lang))
            return

        # Promokod qo'llash
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

        # Ishlatilganlar ro'yxatiga qo'shish
        await db.execute(
            "INSERT OR IGNORE INTO user_tasks (user_id, task_id) VALUES (?, ?)",
            (message.from_user.id, promo["id"] * -1)
        )
        # uses_left kamaytirish
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
async def send_premium_reminders(bot):
    """3 kun va 1 kun qolganda eslatma yuborish"""
    async with await get_db() as db:
        for days_left in [3, 1]:
            target_date = (datetime.now() + timedelta(days=days_left)).strftime("%Y-%m-%d")
            async with db.execute(
                """SELECT tg_id, lang, premium_until FROM users
                   WHERE is_premium = 1 AND premium_until = ? AND notify = 1""",
                (target_date,)
            ) as cur:
                users = await cur.fetchall()

        for (tg_id, lang, until) in users:
            text = txt(
                f"⚠️ <b>Premium eslatma</b>\n\n"
                f"Sizning Premium obunangiz <b>{days_left} kun</b> ichida tugaydi!\n"
                f"📅 Muddat: {until}\n\n"
                f"Uzaytirish uchun /premium yozing.",
                f"⚠️ <b>Напоминание о Premium</b>\n\n"
                f"Ваша Premium подписка истекает через <b>{days_left} дня</b>!\n"
                f"📅 До: {until}\n\n"
                f"Для продления напишите /premium.",
                lang
            )
            try:
                await bot.send_message(tg_id, text, parse_mode="HTML")
            except Exception:
                pass


async def deactivate_expired_premium():
    """Muddati tugagan premiumlarni o'chirish"""
    today = datetime.now().strftime("%Y-%m-%d")
    async with await get_db() as db:
        await db.execute(
            """UPDATE users SET is_premium = 0, premium_until = NULL
               WHERE is_premium = 1 AND premium_until < ?""",
            (today,)
        )
        await db.commit()
