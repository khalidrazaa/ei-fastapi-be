# app/scheduler/jobs.py

from app.db.session import SessionLocal
from app.db.query.niche import get_all_niches
from app.db.query.trend_video import get_recent_titles,get_recent_videos
from app.db.query.discovered_trend import upsert_trend

from app.services.scanner.niche_scanner import NicheScanner
from app.services.analyzer.trend_analyzer import TrendAnalyzer
from app.services.scanner.youtube_scan_service import YouTubeScanService

from app.clients.youtube_client import YouTubeClient
from app.core.config import settings

from app.services.analyzer.idea_generator import IdeaGenerator
from app.db.query.idea_generated import create_trend_idea


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
    """
    Analyze recent videos, detect trending phrases,
    store trends, and generate content ideas.
    """

    generator = IdeaGenerator()
    analyzer = TrendAnalyzer()

    async with SessionLocal() as db:

        # 1️⃣ Get recent videos
        videos = await get_recent_videos(db)

        if not videos:
            print("⚠️ No recent videos found for trend discovery")
            return

        print(f"🔎 Analyzing {len(videos)} videos for trends")

        # 2️⃣ Analyze trends
        trends = analyzer.analyze(videos)

        if not trends:
            print("⚠️ No trends detected")
            return

        saved = 0

        for trend in trends:
            phrase = trend["phrase"]

            # 3️⃣ Save / upsert trend
            trend_id = await upsert_trend(db, trend)

            # 4️⃣ Generate ideas
            ideas = generator.generate(phrase, count=3)

            # 5️⃣ Save ideas
            for idea in ideas:
                await create_trend_idea(
                    db=db,
                    trend_id=trend_id,
                    title=idea["title"],
                    score=idea["score"]
                )

            saved += 1

        print(f"✅ Discovered {len(trends)} trends, saved {saved}")


# ------------------------------------------------
# JOB 3 — Scan popular videos by region
# ------------------------------------------------
async def scan_popular_videos():
    """
    Fetch most popular videos by region and store them.
    This becomes the primary discovery pipeline.
    """

    #REGIONS = ["US", "IN", "CA", "AU", "GB"]
    REGIONS = ["US"]

    youtube_client = YouTubeClient(settings.YOUTUBE_API_KEY)

    async with SessionLocal() as db:

        scanner = YouTubeScanService(
            db_session=db,
            youtube_client=youtube_client,
        )

        total_processed = 0

        for region in REGIONS:
            try:                
                count = await scanner.scan_popular(region)
                total_processed += count

            except Exception as e:
                print(f"❌ Region failed {region}: {str(e)}")

        # single commit after all regions
        await db.commit()

        print(f"✅ Popular videos scan complete. Total processed: {total_processed}")