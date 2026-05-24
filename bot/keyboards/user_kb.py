from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def main_menu(lang: str = "uz") -> ReplyKeyboardMarkup:
    texts = {
        "uz": ["🎬 Kinolar", "⭐ Premium", "👤 Profil", "🔍 Qidirish", "📋 So'rov", "📞 Support"],
        "ru": ["🎬 Фильмы", "⭐ Премиум", "👤 Профиль", "🔍 Поиск", "📋 Запрос", "📞 Поддержка"]
    }
    t = texts.get(lang, texts["uz"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t[0]), KeyboardButton(text=t[1])],
            [KeyboardButton(text=t[2]), KeyboardButton(text=t[3])],
            [KeyboardButton(text=t[4]), KeyboardButton(text=t[5])],
        ],
        resize_keyboard=True
    )

def profile_kb(lang: str = "uz") -> InlineKeyboardMarkup:
    if lang == "uz":
        buttons = [
            [InlineKeyboardButton(text="❤️ Sevimlilar", callback_data="favorites"),
             InlineKeyboardButton(text="📜 Tarix", callback_data="history")],
            [InlineKeyboardButton(text="🌐 Til: O'zbek 🇺🇿", callback_data="change_lang")],
            [InlineKeyboardButton(text="🔔 Bildirishnoma", callback_data="notifications"),
             InlineKeyboardButton(text="🌙 Tungi rejim", callback_data="night_mode")],
            [InlineKeyboardButton(text="👥 Referral", callback_data="referral")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="❤️ Избранное", callback_data="favorites"),
             InlineKeyboardButton(text="📜 История", callback_data="history")],
            [InlineKeyboardButton(text="🌐 Язык: Русский 🇷🇺", callback_data="change_lang")],
            [InlineKeyboardButton(text="🔔 Уведомления", callback_data="notifications"),
             InlineKeyboardButton(text="🌙 Ночной режим", callback_data="night_mode")],
            [InlineKeyboardButton(text="👥 Реферал", callback_data="referral")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="set_lang_uz"),
         InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru")]
    ])

def notify_kb(notify: int, lang: str = "uz") -> InlineKeyboardMarkup:
    status = "✅ Yoqilgan" if notify else "❌ O'chirilgan"
    status_ru = "✅ Включено" if notify else "❌ Выключено"
    label = status if lang == "uz" else status_ru
    toggle = "🔕 O'chirish" if notify else "🔔 Yoqish"
    toggle_ru = "🔕 Выключить" if notify else "🔔 Включить"
    toggle_label = toggle if lang == "uz" else toggle_ru
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Holat: {label}", callback_data="noop")],
        [InlineKeyboardButton(text=toggle_label, callback_data="toggle_notify")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_profile")],
    ])

def back_kb(cb: str = "back_profile") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data=cb)]
    ])
