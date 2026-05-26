# 🎬 AfsonaTvBot

Aiogram 3.x asosidagi Telegram kino boti.

## 🚀 Ishga tushirish

### 1. Talablar
- Python 3.11+
- Telegram Bot tokeni (@BotFather)

### 2. O'rnatish
```bash
git clone https://github.com/yourname/AfsonaTvBot.git
cd AfsonaTvBot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Sozlash
```bash
cp .env.example .env
# .env faylini oching va qiymatlarni to'ldiring:
# BOT_TOKEN, ADMINS, CHANNEL_PUBLIC, CHANNEL_PRIVATE
```

### 4. Ishga tushirish
```bash
python run.py
```

## 📁 Fayl tuzilmasi

```
bot/
├── handlers/
│   ├── admin.py               — /admin buyrug'i (asosiy router)
│   ├── admin_content_add.py   — Film/serial qo'shish (FSM)
│   ├── admin_content_list.py  — Kino ro'yxati, tahrirlash
│   ├── admin_broadcast.py     — Statistika, broadcast, eksport
│   ├── admin_users.py         — Foydalanuvchilar boshqaruvi
│   ├── admin_settings.py      — Sozlamalar, tariflar
│   ├── user.py                — /start, profil, qidiruv
│   ├── movie.py               — Kino ko'rish
│   ├── premium.py             — Premium va to'lovlar
│   ├── gamification.py        — Ball tizimi, turnir
│   └── ...
├── database/
│   ├── db.py                  — DB ulanishi (WAL + FK)
│   ├── models.py              — Jadval sxemalari
│   └── migrations.py          — Migratsiyalar
├── middlewares/
│   ├── auth.py                — Autentifikatsiya, ban
│   └── subscription.py        — Majburiy kanal obunasi
├── utils/
│   ├── channels.py            — Kanal tekshiruvi
│   ├── scheduler.py           — APScheduler vazifalari
│   └── helpers.py             — Yordamchi funksiyalar
└── main.py                    — Bot ishga tushirish
```

## ⚠️ Xavfsizlik

- `.env` faylini **hech qachon** GitHub ga yuklamang
- Faqat `.env.example` ni commit qiling
- Admin ID larini `.env` da saqlang
