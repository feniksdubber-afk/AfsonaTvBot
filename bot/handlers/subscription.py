"""
SubscriptionMiddleware — to'liq himoyalangan versiya

Tuzatilgan:
  - InlineQuery ham tekshiriladi (oldin tekshirilmagan edi)
  - from_user None bo'lsa (kanal post) — xavfsiz o'tkazib yuboriladi
  - check_subscription va /start — har doim o'tkazib yuboriladi
"""

from typing import Any, Callable

from aiogram import BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery, InlineQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)


class SubscriptionMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery | InlineQuery,
        data: dict,
    ) -> Any:
        # from_user yo'q bo'lsa (kanal post va h.k.) — o'tkazib yuboramiz
        if event.from_user is None:
            return await handler(event, data)

        # /start ga tekshirmaymiz (kanal obuna sahifasidan qaytish uchun)
        if isinstance(event, Message):
            text = event.text or ""
            if text.startswith("/start"):
                return await handler(event, data)

        # check_subscription callback — cheksiz loop bo'lmasin
        if isinstance(event, CallbackQuery):
            if event.data == "check_subscription":
                return await handler(event, data)

        # InlineQuery — obuna tekshirishni o'tkazib yuboramiz
        # (inline natijalarni bloklab bo'lmaydi, faqat xabar yuboriladi)
        if isinstance(event, InlineQuery):
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
    lang: str,
) -> None:
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
