from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.handlers.premium import send_premium_reminders, deactivate_expired_premium

def setup_scheduler(bot):
    scheduler = AsyncIOScheduler()

    # Har kuni soat 10:00 da eslatma
    scheduler.add_job(
        send_premium_reminders,
        trigger="cron", hour=10, minute=0,
        args=[bot]
    )
    # Har kuni yarim tunda muddati tugaganlarni o'chirish
    scheduler.add_job(
        deactivate_expired_premium,
        trigger="cron", hour=0, minute=5
    )

    scheduler.start()
    return scheduler
