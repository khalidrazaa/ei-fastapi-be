# app/scheduler/jobs.py

from app.db.session import SessionLocal
from app.db.query.niche import get_all_niches
from app.db.query.trend_video import get_recent_titles
from app.db.query.discovered_trend import upsert_trend

from app.services.scanner.niche_scanner import NicheScanner
from app.services.analyzer.trend_analyzer import TrendAnalyzer

from app.clients.youtube_client import YouTubeClient
from app.core.config import settings


# ------------------------------------------------
# JOB 1 — Scan niches (existing)
# ------------------------------------------------
async def scan_all_niches():

    async with SessionLocal() as db:

        niches = await get_all_niches(db)

        if not niches:
            print("No niches found to scan")
            return

        youtube_client = YouTubeClient(settings.YOUTUBE_API_KEY)

        scanner = NicheScanner(
            db_session=db,
            youtube_client=youtube_client,
        )

        for niche in niches:

            try:
                print(f"Scanning niche: {niche.name}")

                await scanner.scan_niche(niche.id)

            except Exception as e:
                print(f"Niche scan failed {niche.id}: {str(e)}")


# ------------------------------------------------
# JOB 2 — Discover trends from titles
# ------------------------------------------------
async def discover_trends():

    async with SessionLocal() as db:
        videos = await get_recent_titles(db)

        analyzer = TrendAnalyzer()

        trends = analyzer.analyze(videos)
        saved = 0

        for trend in trends:
            await upsert_trend(db, trend)
            saved += 1

        print(f"Discovered {len(trends)} trends, saved {saved}")