# app/scheduler/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler.jobs import scan_all_niches, discover_trends


scheduler = AsyncIOScheduler()


def start_scheduler():
    """
    Start APScheduler and register jobs
    """

    scheduler.add_job(
        scan_all_niches,
        trigger=IntervalTrigger(hours=3),  # run every 3 hours
        # trigger=IntervalTrigger(minutes=1),  # run every 3 minutes (for testing, change to hours=3),
        id="scan_all_niches",
        replace_existing=True,
    )

    scheduler.add_job(
        discover_trends,
        trigger=IntervalTrigger(hours=6),
        # trigger=IntervalTrigger(minutes=2),
        id="discover_trends",
        replace_existing=True
    )

    scheduler.start()

    print("✅ Scheduler started successfully.")