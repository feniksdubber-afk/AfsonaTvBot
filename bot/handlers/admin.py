"""
admin.py
────────
Admin panel — asosiy entry point.

[SPLIT] Katta admin.py (1292 qator) kichik modullarga bo'lindi:
  - admin_content_add.py  — film/serial qo'shish FSM flowi
  - admin_content_list.py — kinolar ro'yxati, tahrirlash, faollashtirish
  - admin_broadcast.py    — statistika, broadcast, CSV eksport, so'rovlar
  - admin_users.py        — foydalanuvchilar boshqaruvi
  - admin_settings.py     — sozlamalar: karta, tariflar, OMDb key

Bu fayl /admin buyrug'ini qayta ishlaydi va barcha sub-routerlarni birlashtiradi.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards.admin_kb import admin_menu
from bot.utils.helpers import is_admin

# ── Sub-routerlar ──────────────────────────────────────────────────────
from bot.handlers.admin_content_add  import router as content_add_router
from bot.handlers.admin_content_list import router as content_list_router
from bot.handlers.admin_broadcast    import router as broadcast_router
from bot.handlers.admin_users        import router as users_router
from bot.handlers.admin_settings     import router as settings_router

router = Router()

# Sub-routerlarni asosiy routerga ulash
router.include_router(content_add_router)
router.include_router(content_list_router)
router.include_router(broadcast_router)
router.include_router(users_router)
router.include_router(settings_router)


# ── /admin BUYRUG'I ────────────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Admin Panel</b>", reply_markup=admin_menu(), parse_mode="HTML")
