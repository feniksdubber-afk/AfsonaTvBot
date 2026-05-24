"""
SubscriptionMiddleware
──────────────────────
Har bir Message va CallbackQuery da:
1. Required channels bormi? (agar bo'sh — tekshirish yo'q)
2. Foydalanuvchi obuna bo'lganmi?
3. Obuna bo'lmasa — kanal tugmalari bilan to'xtatadi.

/start komandasiga tekshirish qo'llanmaydi (ref link ishlashi uchun).
"""

from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from bot.utils.channels import check_user_subscriptions


class SubscriptionMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery,
        data: dict
    ) -> Any:
        user = event.from_user
        bot  = data["bot"]

        # /start ga tekshirmaymiz
        if isinstance(event, Message):
            text = event.text or ""
            if text.startswith("/start"):
                return await handler(event, data)

        # Obuna tekshirish
        not_subscribed = await check_user_subscriptions(bot, user.id)

        if not not_subscribed:
            # Hammaga obuna — davom etish
            return await handler(event, data)

        # ── Obuna bo'lmagan kanallar uchun xabar ────────────────────
        lang = data.get("lang", "uz")  # AuthMiddleware dan keladi
        await _send_subscribe_message(event, not_subscribed, lang)
        return  # handlerni chaqirmaymiz

    # ─────────────────────────────────────────────────────────────────

async def _send_subscribe_message(
    event: Message | CallbackQuery,
    channels: list[dict],
    lang: str
):
    lines = "\n".join(
        f"{'📢'} <a href='{ch['link']}'>{ch['title']}</a>"
        for ch in channels
    )

    if lang == "ru":
        text = (
            "📢 <b>Для использования бота подпишитесь на каналы:</b>\n\n"
            f"{lines}\n\n"
            "✅ После подписки нажмите кнопку ниже."
        )
        btn_label = "✅ Я подписался"
    else:
        text = (
            "📢 <b>Botdan foydalanish uchun kanallarga obuna bo'ling:</b>\n\n"
            f"{lines}\n\n"
            "✅ Obuna bo'lgach, quyidagi tugmani bosing."
        )
        btn_label = "✅ Obuna bo'ldim"

    # Kanal tugmalari
    kb_buttons = [
        [InlineKeyboardButton(text=f"📢 {ch['title']}", url=ch["link"])]
        for ch in channels
    ]
    kb_buttons.append([
        InlineKeyboardButton(text=btn_label, callback_data="check_subscription")
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer()
        await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
