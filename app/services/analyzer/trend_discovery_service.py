from app.services.analyzer.ngram_analyzer import NgramAnalyzer
from app.db.query.trend_video import get_recent_titles
from sqlalchemy.ext.asyncio import AsyncSession


class TrendDiscoveryService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.analyzer = NgramAnalyzer()

    async def discover_phrases(self):

        titles = await get_recent_titles(self.db)

        phrases = self.analyzer.get_top_phrases(titles)

        return phrases