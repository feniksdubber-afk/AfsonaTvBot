from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ==================== REPLIES (ASOSIY MENYULAR) ====================

def main_menu(lang: str = "uz") -> ReplyKeyboardMarkup:
    texts = {
        "uz": ["🍿 Tomosha qilish", "⭐ Premium", "👤 Profil", "🔍 Qidirish", "📋 So'rov", "📞 Support"],
        "ru": ["🍿 Смотреть", "⭐ Премиум", "👤 Профиль", "🔍 Поиск", "📋 Запрос", "📞 Поддержка"]
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

# ==================== INLINES (PROFIL & SOZLAMALAR) ====================

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

# ==================== INLINES (KINO & INTERAKTIV) ====================

def movie_kb(movie_id: int, is_favorite: bool, lang: str = "uz") -> InlineKeyboardMarkup:
    fav_text = (
        ("❤️ Sevimlilardan olib tashlash" if is_favorite else "🤍 Sevimlilarga qo'shish")
        if lang == "uz" else
        ("❤️ Убрать из избранного" if is_favorite else "🤍 Добавить в избранное")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Reyting", callback_data=f"rate_{movie_id}"),
            InlineKeyboardButton(text="💬 Izohlar", callback_data=f"comments_{movie_id}"),
        ],
        [InlineKeyboardButton(text=fav_text, callback_data=f"fav_{movie_id}")],
        [
            InlineKeyboardButton(text="📤 Ulashish", callback_data=f"share_{movie_id}"),
            InlineKeyboardButton(text="🎬 O'xshash", callback_data=f"similar_{movie_id}"),
        ],
    ])

def rating_kb(movie_id: int) -> InlineKeyboardMarkup:
    stars = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
    buttons = [
        [InlineKeyboardButton(text=s, callback_data=f"setrate_{movie_id}_{i+1}")]
        for i, s in enumerate(stars)
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"back_movie_{movie_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def comments_kb(movie_id: int, comments: list, lang: str = "uz") -> InlineKeyboardMarkup:
    buttons = []
    for c in comments:
        buttons.append([
            InlineKeyboardButton(text=f"👍 {c['likes']}", callback_data=f"like_{c['id']}"),
            InlineKeyboardButton(text=f"👎 {c['dislikes']}", callback_data=f"dislike_{c['id']}"),
        ])
    add_text = "✏️ Izoh qoldirish" if lang == "uz" else "✏️ Написать комментарий"
    buttons.append([InlineKeyboardButton(text=add_text, callback_data=f"addcomment_{movie_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"back_movie_{movie_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def series_nav_kb(code_base: str, season: int, episode: int,
                  has_next: bool, has_prev: bool) -> InlineKeyboardMarkup:
    buttons = []
    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton(
            text="⬅️ Oldingi", callback_data=f"ep_{code_base}_{season}_{episode-1}"
        ))
    if has_next:
        nav.append(InlineKeyboardButton(
            text="Keyingi ➡️", callback_data=f"ep_{code_base}_{season}_{episode+1}"
        ))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==================== INLINES (PREMIUM & TO'LOVLAR) ====================

def premium_tariffs_kb(tariffs: list, lang: str = "uz") -> InlineKeyboardMarkup:
    buttons = []
    for t in tariffs:
        label = f"⭐ {t['name']} — {t['price']:,} so'm ({t['duration']} kun)"
        # Tarif tanlash — to'g'ridan-to'g'ri karta to'loviga o'tadi
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"buy_tariff_{t['id']}")])
    cancel = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    buttons.append([InlineKeyboardButton(text=cancel, callback_data="cancel_premium")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def payment_method_kb(tariff_id: int, lang: str = "uz") -> InlineKeyboardMarkup:
    # Faqat karta (manual) to'lov — Click/Payme o'chirilgan
    pay_text = "💳 Karta orqali to'lash" if lang == "uz" else "💳 Оплатить картой"
    back_text = "◀️ Orqaga" if lang == "uz" else "◀️ Назад"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=pay_text, callback_data=f"buy_tariff_{tariff_id}")],
        [InlineKeyboardButton(text=back_text, callback_data="show_premium")],
    ])

def payment_confirm_kb(payment_id: int, lang: str = "uz") -> InlineKeyboardMarkup:
    check = "✅ Chekni yubordim" if lang == "uz" else "✅ Я отправил чек"
    cancel = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=check,  callback_data=f"check_sent_{payment_id}")],
        [InlineKeyboardButton(text=cancel, callback_data=f"cancel_payment_{payment_id}")],
    ])

def admin_payment_kb(payment_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_pay_{payment_id}_{user_id}"),
        InlineKeyboardButton(text="❌ Rad etish",  callback_data=f"reject_pay_{payment_id}_{user_id}"),
    ]])

def cancel_kb(lang: str = "uz") -> InlineKeyboardMarkup:
    """Support va So'rov uchun bekor qilish tugmasi."""
    text = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data="cancel_input")]
    ])


def content_menu_kb(lang: str = "uz") -> InlineKeyboardMarkup:
    """Tomosha qilish menyusi — Film yoki Serial tanlash."""
    if lang == "uz":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎬 Filmlar", callback_data="browse_movies_0"),
                InlineKeyboardButton(text="📺 Seriallar", callback_data="browse_series_0"),
            ],
            [InlineKeyboardButton(text="🔥 Eng mashhurlar", callback_data="browse_top")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎬 Фильмы", callback_data="browse_movies_0"),
                InlineKeyboardButton(text="📺 Сериалы", callback_data="browse_series_0"),
            ],
            [InlineKeyboardButton(text="🔥 Самые популярные", callback_data="browse_top")],
        ])


def movie_view_kb(movie_id: int, code: str, is_fav: bool,
                  lang: str = "uz") -> InlineKeyboardMarkup:
    """Kino ko'rsatilganda chiqadigan tugmalar."""
    fav_text = (
        ("❤️ Sevimlilardan olib tashlash" if is_fav else "🤍 Sevimlilarga qo'shish")
        if lang == "uz" else
        ("❤️ Убрать из избранного" if is_fav else "🤍 Добавить в избранное")
    )
    watch_text = "▶️ Tomosha qilish" if lang == "uz" else "▶️ Смотреть"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=watch_text,
            url=f"https://t.me/{{bot_username}}?start=movie_{code}"
        )],
        [InlineKeyboardButton(text=fav_text, callback_data=f"fav_toggle_{movie_id}")],
    ])

def series_view_kb(series_id: int, code: str, is_fav: bool,
                   lang: str = "uz") -> InlineKeyboardMarkup:
    """Serial ko'rsatilganda chiqadigan tugmalar."""
    fav_text = (
        ("❤️ Sevimlilardan olib tashlash" if is_fav else "🤍 Sevimlilarga qo'shish")
        if lang == "uz" else
        ("❤️ Убрать из избранного" if is_fav else "🤍 Добавить в избранное")
    )
    watch_text = "▶️ Tomosha qilish" if lang == "uz" else "▶️ Смотреть"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=watch_text,
            callback_data=f"watch_series_{series_id}"
        )],
        [InlineKeyboardButton(text=fav_text, callback_data=f"fav_series_{series_id}")],
    ])

