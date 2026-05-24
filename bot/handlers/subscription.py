"""
Obuna tekshirish handler
─────────────────────────
"✅ Obuna bo'ldim" tugmasi bosilganda qayta tekshiradi.
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery
from bot.utils.channels import check_user_subscriptions
from bot.keyboards.user_kb import main_menu
from bot.database.db import get_db

router = Router()


async def _get_lang(user_id: int) -> str:
    async with get_db() as db:
        async with db.execute(
            "SELECT lang FROM users WHERE tg_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else "uz"


@router.callback_query(F.data == "check_subscription")
async def check_subscription(call: CallbackQuery):
    lang = await _get_lang(call.from_user.id)
    not_subscribed = await check_user_subscriptions(call.bot, call.from_user.id)

    if not_subscribed:
        # Hali obuna bo'lmagan
        msg = (
            "❌ Siz hali barcha kanallarga obuna bo'lmadingiz!"
            if lang == "uz" else
            "❌ Вы ещё не подписались на все каналы!"
        )
        await call.answer(msg, show_alert=True)
        return

    # Obuna bo'ldi — xush kelibsiz
    await call.message.delete()
    welcome = (
        "✅ <b>Rahmat! Botdan foydalanishingiz mumkin.</b> 🎬"
        if lang == "uz" else
        "✅ <b>Спасибо! Теперь вы можете пользоваться ботом.</b> 🎬"
    )
    await call.message.answer(welcome, reply_markup=main_menu(lang), parse_mode="HTML")
    await call.answer()
