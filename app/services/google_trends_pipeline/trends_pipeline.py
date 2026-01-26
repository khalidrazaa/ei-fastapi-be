from sqlalchemy import select, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from app.db.models.trends import TrendItem, VolumePoint, TrendStatus
from app.services.gemini_service import GeminiClient
import warnings

from app.services.google_trends_pipeline import TrendsScraper
import datetime
from datetime import datetime

class TrendsPipeline:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.scraper = TrendsScraper()
        self.parser = TrendsCSVParser()
        self.repo = TrendsRepository(db)
        self.volume_repo = VolumeRepository(db)
        self.categorizer = TrendsCategorizer()

    async def run(
        self,
        geo: str = "IN",
        hours: str = "168",
        sts: str = "",
    ):
        # 1. Scrape
        csv_bytes = await self.scraper.fetch_trending_csv_bytes(
            geo=geo,
            hours=hours,
            sts=sts,
        )

        # 2. Parse
        df = self.parser.parse(csv_bytes)

        # 3. Persist + categorize
        result = await self.process(df)

        return {
            "status": True,
            "geo": geo,
            "hours": hours,
            **result,
        }

    async def process(self, df):
        trend_map = {}
    
        for _, row in df.iterrows():
            trend = await self.repo.upsert_trend(row)
            trend_map[trend.trend] = trend

        await self.db.commit()

        ts_now = datetime.utcnow()
        volume_rows = [
            {"trend_id": t.id, "ts": ts_now, "value": t.search_volume}
            for t in trend_map.values()
        ]

        await self.volume_repo.upsert_points(volume_rows)
        await self.db.commit()

        categorized = await self.categorizer.categorize(list(trend_map.values()))
        await self.db.commit()

        return {
            "processed_rows": len(df),
            "categorized_count": categorized,
        }
