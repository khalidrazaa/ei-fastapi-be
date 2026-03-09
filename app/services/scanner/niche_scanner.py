from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scanner.youtube_scan_service import YouTubeScanService
from app.clients.youtube_client import YouTubeClient

from app.db.query.niche import update_last_scanned


class NicheScanner:

    def __init__(
        self,
        db_session: AsyncSession,
        youtube_client: YouTubeClient,
    ):
        self.db = db_session

        self.youtube_service = YouTubeScanService(
            db_session=db_session,
            youtube_client=youtube_client,
        )

    async def scan_niche(self, niche_id: int):

        total_signals = 0

        # scan youtube
        youtube_signals = await self.youtube_service.scan_youtube_niche(
            niche_id
        )

        total_signals += youtube_signals

        # future sources
        # google
        # reddit

        await update_last_scanned(
            db=self.db,
            niche_id=niche_id,
            scanned_at=datetime.now(timezone.utc),
        )

        return total_signals