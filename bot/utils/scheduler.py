"""
scheduler.py
────────────
APScheduler yordamida fon vazifalari:

  1. Har kuni 10:00 — premium muddati tugashiga eslatma (3 kun va 1 kun qolsa)
  2. Har kuni 00:05 — muddati tugagan premiumlarni avtomatik o'chirish

Ishlatish (main.py da):
    from bot.utils.scheduler import setup_scheduler
    setup_scheduler(bot)
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

logger = logging.getLogger(__name__)


def _job_listener(event) -> None:
    """Scheduler job natijalari uchun log yozadi."""
    if event.exception:
        logger.error(
            "❌ Scheduler vazifasi xato bilan tugadi [%s]: %s",
            event.job_id, event.exception
        )
    else:
        logger.debug("✅ Scheduler vazifasi bajarildi [%s]", event.job_id)


def setup_scheduler(bot) -> AsyncIOScheduler:
    """
    Schedulerni sozlab ishga tushiradi.

    Args:
        bot: Aiogram Bot obyekti (xabar yuborish uchun)

    Returns:
        Ishga tushirilgan AsyncIOScheduler obyekti
    """
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")

    # ── 1. Premium eslatma — har kuni 10:00 (Toshkent vaqti) ─────────
    # send_premium_reminders(bot) → bot parametri args orqali uzatiladi
    scheduler.add_job(
        func=_run_premium_reminders,
        trigger="cron",
        hour=10,
        minute=0,
        args=[bot],
        id="premium_reminders",
        replace_existing=True,
        misfire_grace_time=600,   # 10 daqiqa kechiksa ham ishlatadi
    )

    # ── 2. Muddati tugagan premiumlarni o'chirish — har kuni 00:05 ────
    # deactivate_expired_premium(bot) → bot ham kerak (foydalanuvchiga xabar uchun)
    scheduler.add_job(
        func=_run_deactivate_expired,
        trigger="cron",
        hour=0,
        minute=5,
        args=[bot],
        id="deactivate_expired_premium",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Job natijalarini log qilish uchun listener
    scheduler.add_listener(_job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)

    scheduler.start()
    logger.info("✅ Scheduler ishga tushdi (timezone: Asia/Tashkent).")
    return scheduler


async def _run_premium_reminders(bot) -> None:
    """
    send_premium_reminders ni xavfsiz chaqiruvchi wrapper.
    Xato bo'lsa log yozadi va davom etadi.
    """
    try:
        from bot.handlers.premium import send_premium_reminders
        await send_premium_reminders(bot)
    except Exception as exc:
        logger.exception("send_premium_reminders xatosi: %s", exc)


async def _run_deactivate_expired(bot) -> None:
    """
    deactivate_expired_premium ni xavfsiz chaqiruvchi wrapper.
    """
    try:
        from bot.handlers.premium import deactivate_expired_premium
        await deactivate_expired_premium(bot)
    except Exception as exc:
        logger.exception("deactivate_expired_premium xatosi: %s", exc)
