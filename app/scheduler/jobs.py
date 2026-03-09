# app/scheduler/jobs.py

from app.db.session import SessionLocal
from app.db.query.niche import get_all_niches

from app.services.scanner.niche_scanner import NicheScanner
from app.clients.youtube_client import YouTubeClient
from app.core.config import settings


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