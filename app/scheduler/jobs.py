# app/scheduler/jobs.py

from app.clients.youtube_client import YouTubeClient
from app.core.config import settings
from app.db.query.discovered_trend import upsert_trend
from app.db.query.idea_generated import create_trend_idea
from app.db.query.niche import get_all_niches
from app.db.query.trend_video import get_recent_videos
from app.db.session import SessionLocal
from app.services.analyzer.idea_generator import IdeaGenerator
from app.services.analyzer.trend_analyzer import TrendAnalyzer
from app.services.popular_scan_settings import (
    get_or_create_popular_scan_settings,
    normalize_max_results,
    normalize_region_codes,
)
from app.services.scanner.niche_scanner import NicheScanner
from app.services.scanner.youtube_scan_service import YouTubeScanService


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
            except Exception as exc:
                print(f"Niche scan failed {niche.id}: {str(exc)}")


async def discover_trends():
    """
    Analyze recent videos, detect trending phrases,
    store trends, and generate content ideas.
    """

    generator = IdeaGenerator()
    analyzer = TrendAnalyzer()

    async with SessionLocal() as db:
        videos = await get_recent_videos(db)

        if not videos:
            print("No recent videos found for trend discovery")
            return

        print(f"Analyzing {len(videos)} videos for trends")

        trends = analyzer.analyze(videos)
        if not trends:
            print("No trends detected")
            return

        saved = 0

        for trend in trends:
            phrase = trend["phrase"]
            trend_id = await upsert_trend(db, trend)
            ideas = generator.generate(phrase, count=3)

            for idea in ideas:
                await create_trend_idea(
                    db=db,
                    trend_id=trend_id,
                    title=idea["title"],
                    score=idea["score"],
                )

            saved += 1

        print(f"Discovered {len(trends)} trends, saved {saved}")


async def scan_popular_videos(
    region_codes: list[str] | None = None,
    max_results: int | None = None,
):
    """
    Fetch most popular videos by region and store them.
    """

    youtube_client = YouTubeClient(settings.YOUTUBE_API_KEY)

    async with SessionLocal() as db:
        stored_settings = await get_or_create_popular_scan_settings(db)
        resolved_regions = (
            normalize_region_codes(region_codes)
            or list(stored_settings["region_codes"])
        )
        resolved_max_results = normalize_max_results(
            max_results or int(stored_settings["max_results"])
        )

        scanner = YouTubeScanService(
            db_session=db,
            youtube_client=youtube_client,
        )

        total_processed = 0

        for region in resolved_regions:
            try:
                count = await scanner.scan_popular(
                    region,
                    max_results=resolved_max_results,
                )
                total_processed += count
            except Exception as exc:
                print(f"Region failed {region}: {str(exc)}")

        await db.commit()

        print(f"Popular videos scan complete. Total processed: {total_processed}")

        return {
            "status": "done",
            "regions": resolved_regions,
            "max_results": resolved_max_results,
            "total_processed": total_processed,
        }
