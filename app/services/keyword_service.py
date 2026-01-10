import os
from typing import List, Dict, Optional
from datetime import datetime
import asyncio

import asyncio

from serpapi import GoogleSearch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.keyword import Keyword
from app.schemas.keyword import KeywordSuggestion, KeywordResponse

SERP_API_KEY = os.getenv("SERP_API_KEY")


class KeywordService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Generic SerpAPI fetch wrapper ---
    def _search(self, params: dict) -> dict:
        try:
            params["api_key"] = SERP_API_KEY
            search = GoogleSearch(params)
            return search.get_dict() or {}
        except Exception as e:
            print(f"SerpAPI error: {e}")
            return {}

    # --- Fetch methods ---
    async def fetch_google_autocomplete(self, keyword: str) -> List[str]:
        params = {
            "engine": "google_autocomplete",
            "q": keyword,
            "api_key": SERP_API_KEY,
        }
        data = self._search(params)
        suggestions = []

        print("google_auto_complete-data", data)
        for item in data.get("suggestions", []):
            if isinstance(item, dict):
                if "value" in item:
                    suggestions.append(item["value"])
                elif "suggestion" in item:
                    suggestions.append(item["suggestion"])
            elif isinstance(item, str):
                suggestions.append(item)
        return suggestions

    async def fetch_google_trends(self, keyword: str) -> float:
        params = {"engine": "google_trends", "q": keyword, "api_key": SERP_API_KEY}
        data = await self._search(params)

        print("google_trends-data", data)
        arr = data.get("interest_over_time", [])
        if not arr:
            return 0.0
        return float(arr[-1].get("value", 0) or 0)

    async def fetch_google_search_related(self, keyword: str) -> List[str]:
        params = {"engine": "google", "q": keyword, "api_key": SERP_API_KEY}
        data = self._search(params)
        print("google_search-data", data)

        related = data.get("related_searches") or []
        result = []
        for item in data.get("related_searches", []):
            if isinstance(item, dict):
                if "query" in item:
                    result.append(item["query"])
                elif "value" in item:
                    result.append(item["value"])
            elif isinstance(item, str):
                result.append(item)
        return result

    async def fetch_youtube(self, keyword: str) -> List[str]:
        params = {"engine": "youtube", "search_query": keyword, "api_key": SERP_API_KEY}
        data = self._search(params)

        print("youtube-data", data)
        titles = []
        for item in data.get("video_results", []):
            if isinstance(item, dict) and "title" in item:
                title.append(item["title"])
            elif isinstance(item, str):
                title.append(item)
        return titles

    async def fetch_news(self, keyword: str) -> List[str]:
        params = {"engine": "google_news", "q": keyword, "api_key": SERP_API_KEY}
        data = self._search(params)

        print("google_new-data", data)
        headlines = []
        for item in data.get("news_results", []):
            if isinstance(item, dict) and "title" in item:
                headlines.append(item["title"])
            elif isinstance(item, str):
                headlines.append(item)
        return headlines

    # --- DB functions ---
    async def _db_get_keyword(self, keyword: str) -> Optional[Keyword]:
        stmt = select(Keyword).where(Keyword.keyword == keyword)
        result = self.db.execute(stmt)
        return result.scalars().first()

    async def _db_create_keyword(
        self, keyword: str, source: str, suggestions: List[Dict[str, str]]
    ) -> Keyword:
        obj = Keyword(
            keyword=keyword,
            source=source,
            monthly_searches=None,
            cpc=None,
            seo_difficulty=None,
            suggestions=suggestions,
            processed=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    # --- Main function ---
    async def get_keyword_data(self, keyword: str) -> KeywordResponse:
        # 1) Check DB
        db_keyword = await self._db_get_keyword(keyword)
        if db_keyword:
            saved = db_keyword.suggestions or []
            suggestions = [
                KeywordSuggestion(
                    suggestion=item.get("suggestion"), source=item.get("source", "")
                )
                for item in saved
            ]
            return KeywordResponse(
                status="success",
                keyword=db_keyword.keyword,
                suggestions=suggestions,
                monthly_searches=db_keyword.monthly_searches,
                cpc=db_keyword.cpc,
                seo_difficulty=db_keyword.seo_difficulty,
            )

        # 2) Fetch from all sources concurrently
        auto, trend_score, related, youtube, news = await self._gather_sources(keyword)

        # Build unique list
        seen = set()
        suggestions_list: List[Dict[str, str]] = []

        def add_suggestions(items: List[str], src: str):
            for s in items or []:
                key = (s or "").strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    suggestions_list.append({"suggestion": s, "source": src})

        add_suggestions(auto, "google_autocomplete")
        add_suggestions(related, "google_related")
        add_suggestions(youtube, "youtube")
        add_suggestions(news, "news")

        # 3) Persist new keyword
        created = await self._db_create_keyword(keyword, "mixed", suggestions_list)

        # 4) Build response
        resp_suggestions = [item["suggestion"] for item in suggestions_list]

        return {
            "status": "success",
            "keyword": keyword,
            "suggestions": resp_suggestions,
            "monthly_searches": created.monthly_searches,
            "cpc": created.cpc,
            "seo_difficulty": created.seo_difficulty,
        }

    async def _gather_sources(self, keyword: str):
        """Run all source fetches concurrently."""
        tasks = [
            self.fetch_google_autocomplete(keyword),
            self.fetch_google_trends(keyword),
            self.fetch_google_search_related(keyword),
            self.fetch_youtube(keyword),
            self.fetch_news(keyword),
        ]
        return await asyncio.gather(*tasks, return_exceptions=False)
