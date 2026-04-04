# app/scheduler/scheduler.py

from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger, timedelta

from app.scheduler.jobs import scan_all_niches, discover_trends, scan_popular_videos
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def start_scheduler():
    """
    Start APScheduler and register jobs
    """

    scheduler.add_job(
        scan_all_niches,
        trigger=IntervalTrigger(hours=6),  # run every 6 hours
        #trigger=IntervalTrigger(minutes=1),  # run every 3 minutes (for testing, change to hours=3),
        next_run_time= datetime.now() + timedelta(minutes=10),
        id="scan_all_niches",
        replace_existing=True,
    )

    scheduler.add_job(
        discover_trends,
        trigger=IntervalTrigger(hours=12),
        # trigger=IntervalTrigger(minutes=2),
        next_run_time= datetime.now() + timedelta(minutes=5),
        id="discover_trends",
        replace_existing=True
    )

    scheduler.add_job(
        scan_popular_videos,
        trigger=IntervalTrigger(hours=5),
        # trigger=IntervalTrigger(minutes=2),
        next_run_time= datetime.now() + timedelta(minutes=15),
        id="scan_popular_videos",
        replace_existing=True
    )

    scheduler.start()

    logger.info("Scheduler started successfully.")
    print("✅ Scheduler started successfully.")