"""
scheduler.py
────────────
APScheduler yordamida fon vazifalari:

  1. Har kuni 10:00 — premium muddati tugashiga eslatma (3 kun va 1 kun qolsa)
  2. Har kuni 00:05 — muddati tugagan premiumlarni avtomatik o'chirish

TUZATILGAN:
  - setup_scheduler() endi schedulerni qaytaradi (main.py da yopish uchun)
  - main.py da finally blokida scheduler.shutdown() chaqirilishi kerak
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

logger = logging.getLogger(__name__)


def _job_listener(event) -> None:
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
    Returns: Ishga tushirilgan AsyncIOScheduler (main.py da yopish uchun saqlang)
    """
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")

    scheduler.add_job(
        func=_run_premium_reminders,
        trigger="cron",
        hour=10, minute=0,
        args=[bot],
        id="premium_reminders",
        replace_existing=True,
        misfire_grace_time=600,
    )

    scheduler.add_job(
        func=_run_deactivate_expired,
        trigger="cron",
        hour=0, minute=5,
        args=[bot],
        id="deactivate_expired_premium",
        replace_existing=True,
        misfire_grace_time=600,
    )

    scheduler.add_listener(_job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    scheduler.start()
    logger.info("✅ Scheduler ishga tushdi (timezone: Asia/Tashkent).")
    return scheduler


async def _run_premium_reminders(bot) -> None:
    try:
        from bot.handlers.premium import send_premium_reminders
        await send_premium_reminders(bot)
    except Exception as exc:
        logger.exception("send_premium_reminders xatosi: %s", exc)


async def _run_deactivate_expired(bot) -> None:
    try:
        from bot.handlers.premium import deactivate_expired_premium
        await deactivate_expired_premium(bot)
    except Exception as exc:
        logger.exception("deactivate_expired_premium xatosi: %s", exc)
