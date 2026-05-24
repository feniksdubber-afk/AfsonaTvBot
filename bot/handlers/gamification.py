"""
E qism — Gamification (ball tizimi, vazifalar, liderlar taxtasi, turnir)
========================================================================
Faylni  bot/handlers/gamification.py  ga nusxalang.
main.py da:
    from bot.handlers import gamification
    dp.include_router(gamification.router)
models.py ga qo'shing: (pastda alohida SQL berilgan)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMINS
from bot.database.db import get_db

router = Router()

# ═══════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ═══════════════════════════════════════════════════════════════════

def txt(uz: str, ru: str, lang: str) -> str:
    return uz if lang == "uz" else ru

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

async def get_user(tg_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE tg_id = ?", (tg_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
    return None

async def get_user_lang(tg_id: int) -> str:
    u = await get_user(tg_id)
    return u["lang"] if u else "uz"

# ─── Ball qo'shish (istalgan joydan chaqirib ishlatiladi) ───────────
async def add_points(user_id: int, amount: int, reason: str = "") -> int:
    """
    Foydalanuvchiga ball qo'shadi va yangi balansni qaytaradi.
    Shuningdek point_log jadvaliga yozadi.
    """
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE tg_id = ?",
            (amount, user_id)
        )
        await db.execute(
            "INSERT INTO point_log (user_id, amount, reason) VALUES (?, ?, ?)",
            (user_id, amount, reason)
        )
        await db.commit()
        async with db.execute(
            "SELECT balance FROM users WHERE tg_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def get_active_tournament() -> dict | None:
    """Hozirda faol turnirni qaytaradi."""
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM tournaments
               WHERE status = 'active'
                 AND start_at <= ?
                 AND end_at   >= ?
               LIMIT 1""",
            (now, now)
        ) as cur:
            row = await cur.fetchone()
            if row:
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
    return None

async def tournament_add_points(user_id: int, amount: int):
    """Faol turnirda foydalanuvchi ballini oshiradi."""
    t = await get_active_tournament()
    if not t:
        return
    async with get_db() as db:
        # Mavjudligini tekshirish
        async with db.execute(
            "SELECT id, points FROM tournament_participants WHERE tournament_id=? AND user_id=?",
            (t["id"], user_id)
        ) as cur:
            row = await cur.fetchone()
        if row:
            await db.execute(
                "UPDATE tournament_participants SET points = points + ? WHERE id = ?",
                (amount, row[0])
            )
        else:
            await db.execute(
                "INSERT INTO tournament_participants (tournament_id, user_id, points) VALUES (?,?,?)",
                (t["id"], user_id, amount)
            )
        await db.commit()

# ─── Vazifa bajarilishini qayd etish ────────────────────────────────
async def complete_task(user_id: int, task_id: int) -> tuple[bool, int]:
    """
    Vazifani bajargan deb belgilaydi.
    (yangi_mi, ball) qaytaradi.
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT 1 FROM user_tasks WHERE user_id=? AND task_id=?",
            (user_id, task_id)
        ) as cur:
            if await cur.fetchone():
                return False, 0

        async with db.execute(
            "SELECT reward FROM tasks WHERE id=? AND is_active=1",
            (task_id,)
        ) as cur:
            task_row = await cur.fetchone()
        if not task_row:
            return False, 0

        reward = task_row[0]
        await db.execute(
            "INSERT INTO user_tasks (user_id, task_id) VALUES (?,?)",
            (user_id, task_id)
        )
        await db.commit()

    new_balance = await add_points(user_id, reward, reason=f"task_{task_id}")
    await tournament_add_points(user_id, reward)
    return True, reward


# ═══════════════════════════════════════════════════════════════════
#  KLAVIATURALAR
# ═══════════════════════════════════════════════════════════════════

def gamification_menu_kb(lang: str) -> InlineKeyboardMarkup:
    uz = [
        ("🏆 Liderlar taxtasi", "leaderboard"),
        ("📋 Vazifalar",         "tasks_list"),
        ("🎯 Turnir",            "tournament_info"),
        ("💰 Balansim",          "my_points"),
    ]
    ru = [
        ("🏆 Таблица лидеров", "leaderboard"),
        ("📋 Задания",         "tasks_list"),
        ("🎯 Турнир",          "tournament_info"),
        ("💰 Мои баллы",       "my_points"),
    ]
    labels = uz if lang == "uz" else ru
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=cb)]
        for label, cb in labels
    ])

def back_to_game_kb(lang: str) -> InlineKeyboardMarkup:
    label = "◀️ Orqaga" if lang == "uz" else "◀️ Назад"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data="gamification_menu")]
    ])

def tasks_kb(tasks: list, done_ids: set, lang: str) -> InlineKeyboardMarkup:
    buttons = []
    for t in tasks:
        done = t["id"] in done_ids
        mark = "✅ " if done else ""
        label = f"{mark}{t['title']} (+{t['reward']} ball)"
        cb = f"task_done_{t['id']}" if not done else "noop"
        buttons.append([InlineKeyboardButton(text=label, callback_data=cb)])
    back = "◀️ Orqaga" if lang == "uz" else "◀️ Назад"
    buttons.append([InlineKeyboardButton(text=back, callback_data="gamification_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def leaderboard_scope_kb(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        rows = [
            [("📅 Haftalik", "lb_weekly"), ("📅 Oylik", "lb_monthly")],
            [("🏅 Umumiy", "lb_alltime")],
            [("◀️ Orqaga", "gamification_menu")],
        ]
    else:
        rows = [
            [("📅 Недельный", "lb_weekly"), ("📅 Месячный", "lb_monthly")],
            [("🏅 За всё время", "lb_alltime")],
            [("◀️ Назад", "gamification_menu")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
        for row in rows
    ])

def admin_tournament_kb(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        buttons = [
            [InlineKeyboardButton(text="➕ Yangi turnir", callback_data="tournament_create")],
            [InlineKeyboardButton(text="🔚 Turnirni yakunlash", callback_data="tournament_end")],
            [InlineKeyboardButton(text="◀️ Orqaga", callback_data="gamification_menu")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="➕ Новый турнир", callback_data="tournament_create")],
            [InlineKeyboardButton(text="🔚 Завершить турнир", callback_data="tournament_end")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="gamification_menu")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ═══════════════════════════════════════════════════════════════════
#  FSM
# ═══════════════════════════════════════════════════════════════════

class TaskAdminState(StatesGroup):
    title       = State()
    description = State()
    reward      = State()
    task_type   = State()   # watch / referral / rate / manual
    target_url  = State()

class TournamentState(StatesGroup):
    title        = State()
    description  = State()
    duration     = State()   # kunlar
    prize_pool   = State()
    top_n_prizes = State()   # masalan "1000,500,200"


# ═══════════════════════════════════════════════════════════════════
#  ASOSIY MENYULAR
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("game"))
@router.message(F.text.in_({"🎮 O'yinlar", "🎮 Игры", "🏆 Gamification"}))
async def gamification_home(message: Message):
    lang = await get_user_lang(message.from_user.id)
    await message.answer(
        txt(
            "🎮 <b>Gamification</b>\n\n"
            "Ball to'plang, vazifalarni bajaring,\n"
            "liderlar taxtasida birinchi o'ringa chiqing!",
            "🎮 <b>Геймификация</b>\n\n"
            "Набирайте баллы, выполняйте задания,\n"
            "займите первое место в таблице лидеров!",
            lang
        ),
        reply_markup=gamification_menu_kb(lang),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "gamification_menu")
async def cb_gamification_menu(call: CallbackQuery):
    lang = await get_user_lang(call.from_user.id)
    await call.message.edit_text(
        txt(
            "🎮 <b>Gamification</b>\n\n"
            "Ball to'plang, vazifalarni bajaring,\n"
            "liderlar taxtasida birinchi o'ringa chiqing!",
            "🎮 <b>Геймификация</b>\n\n"
            "Набирайте баллы, выполняйте задания,\n"
            "займите первое место в таблице лидеров!",
            lang
        ),
        reply_markup=gamification_menu_kb(lang),
        parse_mode="HTML"
    )
    await call.answer()


# ═══════════════════════════════════════════════════════════════════
#  BALANS
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_points")
async def cb_my_points(call: CallbackQuery):
    lang = await get_user_lang(call.from_user.id)
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer("Xatolik", show_alert=True)
        return

    # So'nggi 5 ta log
    logs = []
    async with get_db() as db:
        async with db.execute(
            "SELECT amount, reason, created_at FROM point_log "
            "WHERE user_id=? ORDER BY id DESC LIMIT 5",
            (call.from_user.id,)
        ) as cur:
            rows = await cur.fetchall()
            for row in rows:
                logs.append(row)

    log_text = ""
    for amount, reason, created_at in logs:
        sign = "+" if amount >= 0 else ""
        date = created_at[:10] if created_at else ""
        log_text += f"\n  {sign}{amount} — {reason} ({date})"

    msg = txt(
        f"💰 <b>Sizning ballingiz</b>\n\n"
        f"🏅 Jami ball: <b>{user['balance']}</b>\n"
        f"\n📜 <b>Oxirgi operatsiyalar:</b>{log_text or chr(10) + '  (bo'sh)'}",

        f"💰 <b>Ваши баллы</b>\n\n"
        f"🏅 Всего баллов: <b>{user['balance']}</b>\n"
        f"\n📜 <b>Последние операции:</b>{log_text or chr(10) + '  (пусто)'}",
        lang
    )
    await call.message.edit_text(msg, reply_markup=back_to_game_kb(lang), parse_mode="HTML")
    await call.answer()


# ═══════════════════════════════════════════════════════════════════
#  LIDERLAR TAXTASI
# ═══════════════════════════════════════════════════════════════════

async def _leaderboard_text(scope: str, user_id: int, lang: str) -> str:
    """scope: weekly | monthly | alltime"""
    now = datetime.utcnow()

    if scope == "weekly":
        since = (now - timedelta(days=7)).isoformat()
        title_uz = "📅 Haftalik liderlar taxtasi"
        title_ru = "📅 Еженедельный рейтинг"
        query = """
            SELECT u.tg_id, u.full_name, SUM(p.amount) as pts
            FROM point_log p
            JOIN users u ON u.tg_id = p.user_id
            WHERE p.created_at >= ?
            GROUP BY p.user_id ORDER BY pts DESC LIMIT 10
        """
        args = (since,)
    elif scope == "monthly":
        since = (now - timedelta(days=30)).isoformat()
        title_uz = "📅 Oylik liderlar taxtasi"
        title_ru = "📅 Месячный рейтинг"
        query = """
            SELECT u.tg_id, u.full_name, SUM(p.amount) as pts
            FROM point_log p
            JOIN users u ON u.tg_id = p.user_id
            WHERE p.created_at >= ?
            GROUP BY p.user_id ORDER BY pts DESC LIMIT 10
        """
        args = (since,)
    else:  # alltime
        title_uz = "🏅 Umumiy liderlar taxtasi"
        title_ru = "🏅 Общий рейтинг"
        query = """
            SELECT tg_id, full_name, balance as pts
            FROM users ORDER BY balance DESC LIMIT 10
        """
        args = ()

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7

    async with get_db() as db:
        async with db.execute(query, args) as cur:
            rows = await cur.fetchall()

    if not rows:
        return txt(
            f"{title_uz}\n\n<i>Hali ma'lumot yo'q</i>",
            f"{title_ru}\n\n<i>Данных пока нет</i>",
            lang
        )

    lines = []
    my_rank = None
    for i, (tg_id, full_name, pts) in enumerate(rows):
        medal = medals[i]
        name = full_name or "Noma'lum"
        line = f"{medal} {i+1}. {name} — <b>{pts}</b> ball"
        lines.append(line)
        if tg_id == user_id:
            my_rank = i + 1

    # Agar foydalanuvchi top-10 da emas bo'lsa, uning o'rnini topish
    if my_rank is None:
        if scope == "alltime":
            rank_q = "SELECT COUNT(*)+1 FROM users WHERE balance > (SELECT balance FROM users WHERE tg_id=?)"
        else:
            rank_q = None  # murakkab, oson yo'l bilan skip

        if rank_q:
            async with get_db() as db:
                async with db.execute(rank_q, (user_id,)) as cur:
                    r = await cur.fetchone()
                    if r:
                        my_rank = r[0]

    rank_info = ""
    if my_rank:
        rank_info = txt(
            f"\n\n👤 Sizning o'rningiz: <b>#{my_rank}</b>",
            f"\n\n👤 Ваше место: <b>#{my_rank}</b>",
            lang
        )

    header = title_uz if lang == "uz" else title_ru
    return f"{header}\n\n" + "\n".join(lines) + rank_info


@router.callback_query(F.data == "leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    lang = await get_user_lang(call.from_user.id)
    await call.message.edit_text(
        txt("📊 Qaysi davrni ko'rmoqchisiz?",
            "📊 За какой период?", lang),
        reply_markup=leaderboard_scope_kb(lang)
    )
    await call.answer()

@router.callback_query(F.data.in_({"lb_weekly", "lb_monthly", "lb_alltime"}))
async def cb_leaderboard_scope(call: CallbackQuery):
    lang = await get_user_lang(call.from_user.id)
    scope = call.data.split("_", 1)[1]  # weekly / monthly / alltime
    text = await _leaderboard_text(scope, call.from_user.id, lang)

    refresh = txt("🔄 Yangilash", "🔄 Обновить", lang)
    back    = txt("◀️ Orqaga",   "◀️ Назад",    lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=refresh, callback_data=call.data)],
        [InlineKeyboardButton(text=back,    callback_data="leaderboard")],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


# ═══════════════════════════════════════════════════════════════════
#  VAZIFALAR
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "tasks_list")
async def cb_tasks_list(call: CallbackQuery):
    lang = await get_user_lang(call.from_user.id)
    uid  = call.from_user.id

    async with get_db() as db:
        async with db.execute(
            "SELECT id, title, description, reward, type, target_url "
            "FROM tasks WHERE is_active=1 ORDER BY id"
        ) as cur:
            tasks = [dict(zip([d[0] for d in cur.description], row))
                     async for row in cur]

        async with db.execute(
            "SELECT task_id FROM user_tasks WHERE user_id=?", (uid,)
        ) as cur:
            done_ids = {row[0] async for row in cur}

    if not tasks:
        await call.message.edit_text(
            txt("📋 Hozircha vazifalar yo'q.", "📋 Заданий пока нет.", lang),
            reply_markup=back_to_game_kb(lang)
        )
        await call.answer()
        return

    done  = sum(1 for t in tasks if t["id"] in done_ids)
    total = len(tasks)

    header = txt(
        f"📋 <b>Vazifalar</b>  ({done}/{total} bajarildi)\n\n",
        f"📋 <b>Задания</b>  ({done}/{total} выполнено)\n\n",
        lang
    )
    lines = []
    for t in tasks:
        mark = "✅" if t["id"] in done_ids else "⬜"
        desc_uz = t["description"] or ""
        lines.append(f"{mark} <b>{t['title']}</b> (+{t['reward']} ball)\n   <i>{desc_uz}</i>")

    text = header + "\n".join(lines)
    await call.message.edit_text(
        text,
        reply_markup=tasks_kb(tasks, done_ids, lang),
        parse_mode="HTML"
    )
    await call.answer()

@router.callback_query(F.data.startswith("task_done_"))
async def cb_task_done(call: CallbackQuery):
    lang    = await get_user_lang(call.from_user.id)
    task_id = int(call.data.split("_")[-1])

    new, reward = await complete_task(call.from_user.id, task_id)
    if new:
        await call.answer(
            txt(f"✅ Vazifa bajarildi! +{reward} ball", f"✅ Задание выполнено! +{reward} баллов", lang),
            show_alert=True
        )
        # Ro'yxatni yangilash
        await cb_tasks_list(call)
    else:
        await call.answer(
            txt("Bu vazifa allaqachon bajarilgan.", "Это задание уже выполнено.", lang),
            show_alert=True
        )


# ═══════════════════════════════════════════════════════════════════
#  TURNIR
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "tournament_info")
async def cb_tournament_info(call: CallbackQuery):
    lang = await get_user_lang(call.from_user.id)
    t    = await get_active_tournament()

    if not t:
        await call.message.edit_text(
            txt(
                "🎯 <b>Turnir</b>\n\nHozirda faol turnir yo'q.\n"
                "Tez kunda yangi turnir bo'ladi!",
                "🎯 <b>Турнир</b>\n\nАктивного турнира нет.\n"
                "Скоро будет новый турнир!",
                lang
            ),
            reply_markup=back_to_game_kb(lang),
            parse_mode="HTML"
        )
        await call.answer()
        return

    # Turnir qatnashchilari TOP-5
    async with get_db() as db:
        async with db.execute(
            """SELECT u.full_name, tp.points
               FROM tournament_participants tp
               JOIN users u ON u.tg_id = tp.user_id
               WHERE tp.tournament_id = ?
               ORDER BY tp.points DESC LIMIT 5""",
            (t["id"],)
        ) as cur:
            top = await cur.fetchall()

        async with db.execute(
            "SELECT points FROM tournament_participants WHERE tournament_id=? AND user_id=?",
            (t["id"], call.from_user.id)
        ) as cur:
            my_row = await cur.fetchone()

    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    top_lines = "\n".join(
        f"{medals[i]} {row[0] or '?'} — <b>{row[1]}</b>"
        for i, row in enumerate(top)
    ) or txt("  (hali ishtirokchilar yo'q)", "  (пока нет участников)", lang)

    my_pts   = my_row[0] if my_row else 0
    end_date = t["end_at"][:10] if t.get("end_at") else "?"

    prizes_uz = t.get("prizes") or "—"
    prizes_ru = t.get("prizes") or "—"

    text = txt(
        f"🎯 <b>{t['title']}</b>\n\n"
        f"📝 {t.get('description') or ''}\n\n"
        f"📅 Tugash sanasi: <b>{end_date}</b>\n"
        f"🎁 Mukofotlar: {prizes_uz}\n\n"
        f"🏆 <b>TOP-5:</b>\n{top_lines}\n\n"
        f"👤 Sizning ballingiz: <b>{my_pts}</b>",

        f"🎯 <b>{t['title']}</b>\n\n"
        f"📝 {t.get('description') or ''}\n\n"
        f"📅 Окончание: <b>{end_date}</b>\n"
        f"🎁 Призы: {prizes_ru}\n\n"
        f"🏆 <b>TOP-5:</b>\n{top_lines}\n\n"
        f"👤 Ваши баллы: <b>{my_pts}</b>",
        lang
    )

    refresh = txt("🔄 Yangilash", "🔄 Обновить", lang)
    back    = txt("◀️ Orqaga",   "◀️ Назад",    lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=refresh, callback_data="tournament_info")],
        [InlineKeyboardButton(text=back,    callback_data="gamification_menu")],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


# ═══════════════════════════════════════════════════════════════════
#  ADMIN: VAZIFALAR BOSHQARUVI
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("admin_tasks"))
async def admin_tasks_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with get_db() as db:
        async with db.execute(
            "SELECT id, title, reward, type, is_active FROM tasks ORDER BY id DESC LIMIT 20"
        ) as cur:
            tasks = await cur.fetchall()

    if not tasks:
        await message.answer("📋 Hali vazifalar yo'q.\n/add_task — yangi vazifa qo'shish")
        return

    lines = []
    for t_id, title, reward, t_type, is_active in tasks:
        status = "✅" if is_active else "❌"
        lines.append(f"{status} [{t_id}] {title} (+{reward} ball) [{t_type}]")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi vazifa", callback_data="task_add_new")],
        *[
            [
                InlineKeyboardButton(text=f"✏️ {t[1][:20]}", callback_data=f"task_edit_{t[0]}"),
                InlineKeyboardButton(
                    text="🔴 O'chir" if t[4] else "🟢 Yoq",
                    callback_data=f"task_toggle_{t[0]}"
                )
            ]
            for t in tasks
        ]
    ])
    await message.answer(
        "<b>📋 Vazifalar boshqaruvi</b>\n\n" + "\n".join(lines),
        reply_markup=kb, parse_mode="HTML"
    )

@router.callback_query(F.data == "task_add_new")
async def cb_task_add_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(TaskAdminState.title)
    await call.message.answer("➕ Yangi vazifa\n\nVazifa nomini kiriting:")
    await call.answer()

@router.message(TaskAdminState.title)
async def task_state_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(TaskAdminState.description)
    await message.answer("📝 Tavsif kiriting (user ko'radi):")

@router.message(TaskAdminState.description)
async def task_state_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(TaskAdminState.reward)
    await message.answer("💰 Necha ball mukofot? (raqam kiriting):")

@router.message(TaskAdminState.reward)
async def task_state_reward(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❗ Faqat raqam kiriting:")
        return
    await state.update_data(reward=int(message.text))
    await state.set_state(TaskAdminState.task_type)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Kino ko'rish",  callback_data="ttype_watch")],
        [InlineKeyboardButton(text="👥 Referral",       callback_data="ttype_referral")],
        [InlineKeyboardButton(text="⭐ Reyting berish", callback_data="ttype_rate")],
        [InlineKeyboardButton(text="🔗 URL (havola)",   callback_data="ttype_url")],
        [InlineKeyboardButton(text="🤝 Qo'lda (manual)", callback_data="ttype_manual")],
    ])
    await message.answer("📌 Vazifa turini tanlang:", reply_markup=kb)

@router.callback_query(F.data.startswith("ttype_"))
async def task_state_type_cb(call: CallbackQuery, state: FSMContext):
    t_type = call.data.split("_", 1)[1]
    await state.update_data(task_type=t_type)
    if t_type == "url":
        await state.set_state(TaskAdminState.target_url)
        await call.message.answer("🔗 Havola kiriting (https://...):")
    else:
        await state.update_data(target_url="")
        await _save_task(call.message, state)
    await call.answer()

@router.message(TaskAdminState.target_url)
async def task_state_url(message: Message, state: FSMContext):
    await state.update_data(target_url=message.text)
    await _save_task(message, state)

async def _save_task(message: Message, state: FSMContext):
    data = await state.get_data()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO tasks (title, description, reward, type, target_url) VALUES (?,?,?,?,?)",
            (data["title"], data["description"], data["reward"],
             data["task_type"], data.get("target_url", ""))
        )
        await db.commit()
    await state.clear()
    await message.answer(
        f"✅ Vazifa qo'shildi!\n"
        f"  📌 Nomi: {data['title']}\n"
        f"  💰 Ball: {data['reward']}\n"
        f"  🔧 Tur: {data['task_type']}"
    )

@router.callback_query(F.data.startswith("task_toggle_"))
async def cb_task_toggle(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    task_id = int(call.data.split("_")[-1])
    async with get_db() as db:
        await db.execute(
            "UPDATE tasks SET is_active = 1 - is_active WHERE id=?", (task_id,)
        )
        await db.commit()
    await call.answer("✅ Holat o'zgartirildi", show_alert=False)
    await admin_tasks_cmd(call.message)

@router.callback_query(F.data.startswith("task_edit_"))
async def cb_task_edit(call: CallbackQuery):
    """Vazifani o'chirish (sodda variant)."""
    if not is_admin(call.from_user.id):
        return
    task_id = int(call.data.split("_")[-1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🗑 O'chirish",
            callback_data=f"task_delete_{task_id}"
        )],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="noop")],
    ])
    await call.message.answer(f"[{task_id}] Vazifani o'chirish:", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.startswith("task_delete_"))
async def cb_task_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    task_id = int(call.data.split("_")[-1])
    async with get_db() as db:
        await db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        await db.execute("DELETE FROM user_tasks WHERE task_id=?", (task_id,))
        await db.commit()
    await call.answer("🗑 Vazifa o'chirildi", show_alert=True)
    await admin_tasks_cmd(call.message)


# ═══════════════════════════════════════════════════════════════════
#  ADMIN: TURNIR BOSHQARUVI
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("admin_tournament"))
async def admin_tournament_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    lang = await get_user_lang(message.from_user.id)
    t = await get_active_tournament()
    if t:
        end_date = t["end_at"][:10] if t.get("end_at") else "?"
        text = (
            f"🎯 <b>Faol turnir mavjud</b>\n\n"
            f"📌 {t['title']}\n"
            f"📅 Tugash: {end_date}\n\n"
            "Yangi turnir yaratish uchun avval mavjudni yakunlang."
        )
    else:
        text = "🎯 Hozirda faol turnir yo'q.\nYangi turnir yarating."

    await message.answer(text, reply_markup=admin_tournament_kb(lang), parse_mode="HTML")

@router.callback_query(F.data == "tournament_create")
async def cb_tournament_create(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    t = await get_active_tournament()
    if t:
        await call.answer("❗ Avval mavjud turnirni yakunlang!", show_alert=True)
        return
    await state.set_state(TournamentState.title)
    await call.message.answer("🎯 Yangi turnir\n\nTurnir nomini kiriting:")
    await call.answer()

@router.message(TournamentState.title)
async def tourn_state_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(TournamentState.description)
    await message.answer("📝 Turnir tavsifini kiriting:")

@router.message(TournamentState.description)
async def tourn_state_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(TournamentState.duration)
    await message.answer("📅 Necha kun davom etadi? (masalan: 7):")

@router.message(TournamentState.duration)
async def tourn_state_duration(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❗ Faqat raqam (kun soni):")
        return
    await state.update_data(duration=int(message.text))
    await state.set_state(TournamentState.prize_pool)
    await message.answer("🎁 Mukofotlar haqida matn kiriting (masalan: 1-o'rin 100 000 so'm):")

@router.message(TournamentState.prize_pool)
async def tourn_state_prizes(message: Message, state: FSMContext):
    await state.update_data(prizes=message.text)
    await state.set_state(TournamentState.top_n_prizes)
    await message.answer(
        "🏆 Necha kishi sovg'a oladi? (masalan: 3):\n"
        "(Bu raqam avtomatik ball hisoblash uchun ishlatiladi)"
    )

@router.message(TournamentState.top_n_prizes)
async def tourn_state_top_n(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❗ Faqat raqam:")
        return

    data = await state.get_data()
    start_at = datetime.utcnow()
    end_at   = start_at + timedelta(days=data["duration"])

    async with get_db() as db:
        await db.execute(
            """INSERT INTO tournaments
               (title, description, prizes, top_n, status, start_at, end_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                data["title"],
                data["description"],
                data.get("prizes", ""),
                int(message.text),
                "active",
                start_at.isoformat(),
                end_at.isoformat()
            )
        )
        await db.commit()

    await state.clear()
    await message.answer(
        f"✅ Turnir yaratildi!\n"
        f"  📌 {data['title']}\n"
        f"  📅 {start_at.strftime('%d.%m.%Y')} — {end_at.strftime('%d.%m.%Y')}\n"
        f"  🎁 {data.get('prizes', '')}"
    )

@router.callback_query(F.data == "tournament_end")
async def cb_tournament_end(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    t = await get_active_tournament()
    if not t:
        await call.answer("Faol turnir yo'q.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha, yakunla",  callback_data=f"tourn_confirm_end_{t['id']}")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="noop")],
    ])
    await call.message.answer(
        f"❗ Turnirni yakunlashni tasdiqlaysizmi?\n📌 {t['title']}",
        reply_markup=kb
    )
    await call.answer()

@router.callback_query(F.data.startswith("tourn_confirm_end_"))
async def cb_tournament_confirm_end(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    t_id = int(call.data.split("_")[-1])

    # TOP-3 ni chiqarish va statusni o'zgartirish
    async with get_db() as db:
        async with db.execute(
            """SELECT u.tg_id, u.full_name, tp.points
               FROM tournament_participants tp
               JOIN users u ON u.tg_id = tp.user_id
               WHERE tp.tournament_id = ?
               ORDER BY tp.points DESC LIMIT 3""",
            (t_id,)
        ) as cur:
            winners = await cur.fetchall()

        await db.execute(
            "UPDATE tournaments SET status='finished' WHERE id=?", (t_id,)
        )
        await db.commit()

    medals = ["🥇", "🥈", "🥉"]
    lines  = "\n".join(
        f"{medals[i]} {row[1] or '?'} — {row[2]} ball"
        for i, row in enumerate(winners)
    ) or "Qatnashuvchilar yo'q"

    await call.message.answer(
        f"🏁 Turnir yakunlandi!\n\n🏆 <b>G'oliblar:</b>\n{lines}",
        parse_mode="HTML"
    )
    await call.answer()


# ═══════════════════════════════════════════════════════════════════
#  ICHKI INTEGRASIYA — Boshqa handlerlar chaqiradigan funksiyalar
# ═══════════════════════════════════════════════════════════════════
#
#  movie.py da kino ko'rganda:
#      from bot.handlers.gamification import add_points, complete_task, tournament_add_points
#      await add_points(user_id, 10, reason="watch_movie")
#      await tournament_add_points(user_id, 10)
#      # Agar "watch" tipidagi vazifa bo'lsa:
#      tasks = await db.execute("SELECT id FROM tasks WHERE type='watch' AND is_active=1")
#      for row in tasks: await complete_task(user_id, row[0])
#
#  user.py referral qismida:
#      await add_points(inviter_id, 50, reason="referral")
#      await tournament_add_points(inviter_id, 50)
#
#  movie.py reyting berish (setrate_) callbackda:
#      await add_points(user_id, 5, reason="rate_movie")
#
# ═══════════════════════════════════════════════════════════════════
