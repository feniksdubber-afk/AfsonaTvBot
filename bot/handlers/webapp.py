"""
webapp.py
─────────
Telegram Mini App integratsiyasi:

  /webapp       — foydalanuvchiga WebApp tugmasi yuboradi
  contact share — foydalanuvchi telefon raqamini botga yuborganda
                  tg_id → telefon juftligini API serverga ro'yxatdan o'tkazadi

OTP yuborish:
  API server (/api/auth/send-otp) o'zi BOT_TOKEN orqali Telegram ga
  xabar yuboradi — bu handler faqat telefon ro'yxatdan o'tkazish uchun.

Muhit o'zgaruvchilari (.env):
  WEBAPP_URL       — sayt URL (masalan: https://abc.replit.app)
  WEBAPP_API_URL   — API server URL (masalan: https://abc.replit.app/api)
"""

import logging
import os

import aiohttp
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from bot.utils.helpers import get_user

logger = logging.getLogger(__name__)
router = Router()

WEBAPP_URL     = os.getenv("WEBAPP_URL", "").rstrip("/")
WEBAPP_API_URL = os.getenv("WEBAPP_API_URL", "").rstrip("/")


def _webapp_kb(lang: str = "uz") -> ReplyKeyboardMarkup:
    """WebApp ochish tugmasi + Telefon ulashish tugmasi."""
    if not WEBAPP_URL:
        return ReplyKeyboardRemove()

    open_text   = "🎬 AFSONA ni ochish"   if lang == "uz" else "🎬 Открыть AFSONA"
    phone_text  = "📱 Telefon raqamni ulashish" if lang == "uz" else "📱 Поделиться номером"

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text=open_text,
                web_app=WebAppInfo(url=WEBAPP_URL)
            )],
            [KeyboardButton(
                text=phone_text,
                request_contact=True
            )],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


@router.message(Command("webapp"))
async def cmd_webapp(message: Message):
    """
    /webapp — foydalanuvchiga Mini App ochish tugmasini yuboradi.
    Telefon raqamini ulashish taklifi ham qo'shiladi (OTP uchun kerak).
    """
    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    if not WEBAPP_URL:
        await message.answer(
            "⚠️ WEBAPP_URL sozlanmagan. Bot admini bilan bog'laning."
            if lang == "uz" else
            "⚠️ WEBAPP_URL не настроен. Обратитесь к администратору бота."
        )
        return

    text = (
        "🎬 <b>AFSONA</b> — kino platformasi!\n\n"
        "Quyidagi tugma orqali saytni oching.\n\n"
        "📱 <b>Birinchi marta kirishda:</b>\n"
        "«Telefon raqamni ulashish» tugmasini bosing — "
        "shu raqam orqali saytga kirasiz."
        if lang == "uz" else
        "🎬 <b>AFSONA</b> — платформа кино!\n\n"
        "Откройте сайт по кнопке ниже.\n\n"
        "📱 <b>При первом входе:</b>\n"
        "Нажмите «Поделиться номером телефона» — "
        "через него вы войдёте на сайт."
    )

    await message.answer(
        text,
        reply_markup=_webapp_kb(lang),
        parse_mode="HTML",
    )


@router.message(F.contact)
async def handle_contact(message: Message):
    """
    Foydalanuvchi o'z telefon raqamini yuborsa:
      1. Raqamni tozalaymiz (faqat raqamlar qoladi)
      2. API serverga POST /api/auth/register-phone yuboramiz
      3. Foydalanuvchiga tasdiqlash xabari yuboramiz
    """
    contact = message.contact

    if contact.user_id != message.from_user.id:
        return

    raw_phone = contact.phone_number or ""
    phone = "".join(filter(str.isdigit, raw_phone))
    if not phone.startswith("998") and len(phone) == 9:
        phone = "998" + phone

    user = await get_user(message.from_user.id)
    lang = user["lang"] if user else "uz"

    if not WEBAPP_API_URL:
        logger.warning("WEBAPP_API_URL sozlanmagan — telefon ro'yxatdan o'tkazilmadi.")
        await message.answer(
            "⚠️ Tizim xatosi. Keyinroq urinib ko'ring."
            if lang == "uz" else
            "⚠️ Системная ошибка. Попробуйте позже.",
            reply_markup=_webapp_kb(lang),
        )
        return

    registered = False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{WEBAPP_API_URL}/auth/register-phone",
                json={"phone": phone, "tg_id": message.from_user.id},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    registered = True
                else:
                    body = await resp.text()
                    logger.error(
                        "register-phone failed: status=%s body=%s", resp.status, body
                    )
    except Exception as exc:
        logger.error("register-phone request error: %s", exc)

    if registered:
        text = (
            f"✅ <b>Telefon raqam saqlandi!</b>\n\n"
            f"📱 Raqam: <code>+{phone}</code>\n\n"
            f"Endi «🎬 AFSONA ni ochish» tugmasini bosing va "
            f"saytda ushbu raqam bilan kiring — OTP kodi shu chatga keladi."
            if lang == "uz" else
            f"✅ <b>Номер телефона сохранён!</b>\n\n"
            f"📱 Номер: <code>+{phone}</code>\n\n"
            f"Теперь нажмите «🎬 Открыть AFSONA» и войдите на сайт "
            f"с этим номером — OTP-код придёт в этот чат."
        )
    else:
        text = (
            "⚠️ Raqamni saqlashda xato yuz berdi. Iltimos keyinroq urinib ko'ring."
            if lang == "uz" else
            "⚠️ Не удалось сохранить номер. Пожалуйста, попробуйте позже."
        )

    await message.answer(
        text,
        reply_markup=_webapp_kb(lang),
        parse_mode="HTML",
    )
