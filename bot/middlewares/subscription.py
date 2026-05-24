"""
SubscriptionMiddleware — to'liq himoyalangan versiya
"""

from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)


class SubscriptionMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery,
        data: dict
    ) -> Any:
        # /start ga tekshirmaymiz
        if isinstance(event, Message):
            text = event.text or ""
            if text.startswith("/start"):
                return await handler(event, data)

        # check_subscription callback ga tekshirmaymiz (cheksiz loop bo'lmasin)
        if isinstance(event, CallbackQuery):
            if event.data == "check_subscription":
                return await handler(event, data)

        try:
            from bot.utils.channels import check_user_subscriptions
            bot  = data["bot"]
            user = event.from_user
            not_subscribed = await check_user_subscriptions(bot, user.id)
        except Exception:
            # Xato bo'lsa — tekshirishsiz o'tkazib yuboramiz
            return await handler(event, data)

        if not not_subscribed:
            return await handler(event, data)

        lang = data.get("lang", "uz")
        await _send_subscribe_message(event, not_subscribed, lang)


async def _send_subscribe_message(
    event: Message | CallbackQuery,
    channels: list[dict],
    lang: str
):
    lines = "\n".join(
        f"📢 <a href='{ch['link']}'>{ch['title']}</a>"
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

    kb_buttons = [
        [InlineKeyboardButton(text=f"📢 {ch['title']}", url=ch["link"])]
        for ch in channels
    ]
    kb_buttons.append([
        InlineKeyboardButton(text=btn_label, callback_data="check_subscription")
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    try:
        if isinstance(event, Message):
            await event.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            await event.answer()
            await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
