# app/services/youtube_scan_service.py

from datetime import datetime, timedelta, timezone
from math import log1p
from typing import Dict, List
import asyncio
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.youtube_client import YouTubeClient
from app.db.query.niche import get_keyword_by_id, get_keywords_by_niche, get_niche_by_id
from app.db.query.trend_video import create_or_update


class YouTubeScanService:
    SEARCH_ORDERS = ("viewCount", "relevance", "date")
    SEARCH_RESULTS_PER_ORDER = 15
    SEARCH_LOOKBACK_HOURS = 72

    def __init__(
        self,
        db_session: AsyncSession,
        youtube_client: YouTubeClient,
    ):
        self.db = db_session
        self.youtube = youtube_client

    async def scan_youtube_niche(self, niche_id: int) -> int:
        keywords = await get_keywords_by_niche(
            db=self.db,
            niche_id=niche_id,
        )

        if not keywords:
            raise ValueError("No keywords found for this niche")

        total_videos_saved = 0

        for keyword in keywords:
            try:
                total_videos_saved += await self.scan_keyword(keyword.id)
            except Exception as exc:
                print(f"Keyword failed {keyword.id}: {exc}")

        return total_videos_saved

    async def scan_keyword(self, keyword_id: int) -> int:
        """
        Scan breakout videos for a specific keyword.
        Returns number of processed videos.
        """

        keyword = await get_keyword_by_id(self.db, keyword_id)
        if not keyword:
            return 0

        niche = await get_niche_by_id(self.db, keyword.niche_id)
        region_code = niche.region_code if niche and niche.region_code else "US"
        published_after = (
            datetime.now(timezone.utc) - timedelta(hours=self.SEARCH_LOOKBACK_HOURS)
        ).isoformat()

        search_responses = await asyncio.gather(
            *[
                self.youtube.search_videos(
                    query=keyword.keyword,
                    max_results=self.SEARCH_RESULTS_PER_ORDER,
                    published_after=published_after,
                    order=order,
                    region_code=region_code,
                )
                for order in self.SEARCH_ORDERS
            ]
        )

        video_ids = self._merge_video_ids(search_responses)
        if not video_ids:
            return 0

        video_details, category_data = await asyncio.gather(
            self.youtube.get_video_details(video_ids),
            self.youtube.get_video_categories(region_code),
        )

        items = video_details.get("items", [])
        if not items:
            return 0

        category_map = self._map_video_categories(category_data)
        channel_ids = list({item["snippet"]["channelId"] for item in items})
        channel_data = await self.youtube.get_channel_details(channel_ids)
        subscriber_map = self._map_channel_subscribers(channel_data)

        processed = 0

        for video in items:
            channel_id = video["snippet"]["channelId"]
            subs = subscriber_map.get(channel_id, 1)
            score = self._calculate_velocity(video, subs)

            if not self._is_promising_video(video, score):
                continue

            category_id = video.get("snippet", {}).get("categoryId")
            category_title = category_map.get(category_id, "Unknown")

            await create_or_update(
                db=self.db,
                keyword_id=keyword_id,
                video_data=video,
                score=score,
                category_title=category_title,
            )

            processed += 1

        return processed

    def _extract_video_ids(self, data: dict) -> List[str]:
        items = data.get("items", [])
        video_ids: List[str] = []

        for item in items:
            video_id = item.get("id")

            if isinstance(video_id, dict):
                video_id = video_id.get("videoId")

            if isinstance(video_id, str):
                video_ids.append(video_id)

        return video_ids

    def _merge_video_ids(self, responses: List[dict]) -> List[str]:
        seen = set()
        merged: List[str] = []

        for response in responses:
            for video_id in self._extract_video_ids(response):
                if video_id in seen:
                    continue
                seen.add(video_id)
                merged.append(video_id)

        return merged

    def _map_channel_subscribers(self, channel_data: dict) -> Dict[str, int]:
        mapping: Dict[str, int] = {}

        for item in channel_data.get("items", []):
            channel_id = item["id"]
            stats = item.get("statistics", {})
            mapping[channel_id] = int(stats.get("subscriberCount", 1))

        return mapping

    def _map_video_categories(self, category_data: dict) -> Dict[str, str]:
        mapping: Dict[str, str] = {}

        for item in category_data.get("items", []):
            category_id = item.get("id")
            title = item.get("snippet", {}).get("title")
            if category_id and title:
                mapping[category_id] = title

        return mapping

    def _calculate_velocity(self, video: dict, subs: int) -> float:
        """
        Blend fast growth, comments, engagement, and creator size fairly.
        """
        stats = video.get("statistics", {})
        snippet = video.get("snippet", {})

        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))
        published_at = snippet.get("publishedAt")

        if not published_at:
            return 0.0

        published_dt = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )
        hours = max(
            (datetime.now(timezone.utc) - published_dt).total_seconds() / 3600,
            1,
        )
        subs = max(subs, 1)

        views_per_hour = views / hours
        likes_per_hour = likes / hours
        comments_per_hour = comments / hours
        engagement_rate = (likes + comments * 3) / max(views, 1)
        breakout_ratio = (views + comments * 20) / max(subs ** 0.6, 25)

        score = (
            log1p(views_per_hour) * 0.5
            + log1p(comments_per_hour * 12) * 0.3
            + log1p(likes_per_hour) * 0.1
            + log1p(breakout_ratio) * 0.1
            + min(engagement_rate, 0.25) * 10
        )

        return round(score, 4)

    def _is_promising_video(self, video: dict, score: float) -> bool:
        stats = video.get("statistics", {})
        snippet = video.get("snippet", {})

        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))
        published_at = snippet.get("publishedAt")

        if not published_at:
            return False

        published_dt = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )
        hours = max(
            (datetime.now(timezone.utc) - published_dt).total_seconds() / 3600,
            1,
        )

        if views >= 5000 or comments >= 40:
            return True

        if hours <= 6 and views >= 800 and (comments >= 8 or likes >= 60):
            return True

        return score >= 4.5

    def _extract_keywords(self, title: str):
        title = title.lower()
        words = re.findall(r"\b[a-zA-Z]{3,}\b", title)

        return [
            " ".join(words[i : i + 2])
            for i in range(len(words) - 1)
        ]

    async def scan_popular(self, region_code: str, max_results: int = 2):
        """
        Scan popular videos for a region.
        Returns number of processed videos.
        """

        category_data, trending_data = await asyncio.gather(
            self.youtube.get_video_categories(region_code),
            self.youtube.get_trending_videos(
                region_code=region_code,
                max_results=max_results,
            ),
        )

        video_ids = self._extract_video_ids(trending_data)
        if not video_ids:
            return 0

        video_details = await self.youtube.get_video_details(video_ids)
        items = video_details.get("items", [])
        if not items:
            return 0

        category_map = self._map_video_categories(category_data)
        channel_ids = list({item["snippet"]["channelId"] for item in items})
        channel_data = await self.youtube.get_channel_details(channel_ids)
        subscriber_map = self._map_channel_subscribers(channel_data)

        processed = 0

        for video in items:
            channel_id = video["snippet"]["channelId"]
            subs = subscriber_map.get(channel_id, 1)
            score = self._calculate_velocity(video, subs)
            category_id = video.get("snippet", {}).get("categoryId")
            category_title = category_map.get(category_id, "Unknown")

            await create_or_update(
                db=self.db,
                keyword_id=None,
                video_data=video,
                score=score,
                category_title=category_title,
                region_code=region_code,
                source="POPULAR",
            )

            processed += 1

        return processed
