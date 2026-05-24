"""
config.py
─────────
.env faylidan barcha sozlamalarni o'qiydi.

DIQQAT:
  - BOT_TOKEN bo'sh bo'lsa — bot ishga tushmaydi (ValueError)
  - CHANNEL_PRIVATE int ga aylantiriladi (Telegram API talab qiladi)
  - ADMINS vergul bilan ajratilgan ID lar ro'yxati
"""

from dotenv import load_dotenv
import os
import sys

load_dotenv()

# ── Majburiy sozlamalar ───────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    sys.exit(
        "❌ XATO: BOT_TOKEN o'rnatilmagan!\n"
        ".env faylida BOT_TOKEN=<tokeningiz> ni to'ldiring."
    )

# ── Adminlar ro'yxati ─────────────────────────────────────────────
_admins_raw = os.getenv("ADMINS", "")
ADMINS: list[int] = [
    int(a.strip()) for a in _admins_raw.split(",") if a.strip().lstrip("-").isdigit()
]
if not ADMINS:
    sys.exit(
        "❌ XATO: ADMINS o'rnatilmagan!\n"
        ".env faylida ADMINS=<telegram_id> ni to'ldiring."
    )

# ── Kanallar ─────────────────────────────────────────────────────
CHANNEL_PUBLIC: str = os.getenv("CHANNEL_PUBLIC", "")

# CHANNEL_PRIVATE Telegram API da int sifatida kerak
_ch_private_raw = os.getenv("CHANNEL_PRIVATE", "0")
try:
    CHANNEL_PRIVATE: int = int(_ch_private_raw)
except ValueError:
    CHANNEL_PRIVATE = 0

# ── Ma'lumotlar bazasi ────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "data/kinobot.db")

# ── To'lov tizimlari (ixtiyoriy) ─────────────────────────────────
CLICK_SERVICE_ID:  str = os.getenv("CLICK_SERVICE_ID",  "")
CLICK_MERCHANT_ID: str = os.getenv("CLICK_MERCHANT_ID", "")
CLICK_SECRET_KEY:  str = os.getenv("CLICK_SECRET_KEY",  "")

PAYME_MERCHANT_ID: str = os.getenv("PAYME_MERCHANT_ID", "")
PAYME_SECRET_KEY:  str = os.getenv("PAYME_SECRET_KEY",  "")
