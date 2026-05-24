from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kino qo'shish"), KeyboardButton(text="✏️ Kontentni tahrirlash")],
            [KeyboardButton(text="📋 Kinolar ro'yxati"), KeyboardButton(text="📢 Broadcast")],
            [KeyboardButton(text="👥 Foydalanuvchilar"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="🔧 Sozlamalar"),    KeyboardButton(text="📨 Kino so'rovlar")],
            [KeyboardButton(text="🏠 Bosh menyu")],
        ],
        resize_keyboard=True
    )

def content_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎞 Film", callback_data="add_type_film"),
            InlineKeyboardButton(text="📺 Serial", callback_data="add_type_series")
        ],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_admin_fsm")]
    ])

def is_premium_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Ha (Premium)", callback_data="premium_yes"),
            InlineKeyboardButton(text="⚪ Yo'q (Tekin)", callback_data="premium_no")
        ]
    ])

def series_control_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Keyingi faslga o'tish", callback_data="series_next_season")],
        [InlineKeyboardButton(text="✅ Yuklashni yakunlash", callback_data="series_finish")]
    ])

def cancel_fsm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Jarayonni bekor qilish", callback_data="cancel_admin_fsm")]
    ])

def movie_manage_kb(movie_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_movie_{movie_id}"),
            InlineKeyboardButton(text="🗑 O'chirish",  callback_data=f"del_movie_{movie_id}"),
        ],
        [
            InlineKeyboardButton(text="🔒 Faolsizlantirish", callback_data=f"deactivate_{movie_id}"),
            InlineKeyboardButton(text="✅ Faollashtirish",   callback_data=f"activate_{movie_id}"),
        ],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_movies")],
    ])

def edit_movie_kb(movie_id: int) -> InlineKeyboardMarkup:
    fields = [
        ("📝 Nomi",       f"efield_{movie_id}_title"),
        ("🌐 Nomi (RU)",  f"efield_{movie_id}_title_ru"),
        ("📄 Tavsif",     f"efield_{movie_id}_description"),
        ("🎭 Janr",       f"efield_{movie_id}_genre"),
        ("📅 Yil",        f"efield_{movie_id}_year"),
        ("🌍 Mamlakat",   f"efield_{movie_id}_country"),
        ("🖼 Poster",     f"efield_{movie_id}_poster"),
        ("🎬 Video",      f"efield_{movie_id}_file"),
        ("⭐ Premium",    f"efield_{movie_id}_premium"),
    ]
    buttons = [[InlineKeyboardButton(text=t, callback_data=c)] for t, c in fields]
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"admin_movie_{movie_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_kb(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha",    callback_data=yes_cb),
        InlineKeyboardButton(text="❌ Yo'q", callback_data=no_cb),
    ]])

def user_manage_kb(user_id: int, is_banned: int) -> InlineKeyboardMarkup:
    ban_text  = "✅ Unban" if is_banned else "🚫 Ban"
    ban_cb    = f"unban_{user_id}" if is_banned else f"ban_{user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ban_text, callback_data=ban_cb)],
        [InlineKeyboardButton(text="⭐ Premium berish", callback_data=f"give_premium_{user_id}")],
        [InlineKeyboardButton(text="💬 Xabar yuborish", callback_data=f"msg_user_{user_id}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_users")],
    ])

def requests_kb(req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Qabul",   callback_data=f"req_accept_{req_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"req_reject_{req_id}"),
    ]])
