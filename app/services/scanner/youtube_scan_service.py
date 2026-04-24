# app/services/youtube_scan_service.py

import asyncio
import re
from datetime import datetime, timedelta, timezone
from math import log1p
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.youtube_client import YouTubeClient
from app.db.query.niche import get_keyword_by_id, get_keywords_by_niche, get_niche_by_id
from app.db.query.trend_video import create_or_update


class YouTubeScanService:
    SEARCH_ORDERS = ("viewCount", "relevance", "date")
    SEARCH_RESULTS_PER_ORDER = 20
    SEARCH_LOOKBACK_HOURS = 120

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
        Scan videos for a specific keyword and persist all fetched candidates
        with richer trend analytics so early winners are not discarded.
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
        channel_map = self._map_channels_by_id(channel_data)

        processed = 0

        for video in items:
            channel_id = video["snippet"]["channelId"]
            channel = channel_map.get(channel_id)
            analytics = self._calculate_trend_metrics(video, channel)
            category_id = video.get("snippet", {}).get("categoryId")
            category_title = category_map.get(category_id, "Unknown")

            await create_or_update(
                db=self.db,
                keyword_id=keyword_id,
                video_data=video,
                channel_data=channel,
                score=analytics["virality_score"],
                analytics=analytics,
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

    def _map_channels_by_id(self, channel_data: dict) -> Dict[str, dict]:
        mapping: Dict[str, dict] = {}

        for item in channel_data.get("items", []):
            channel_id = item.get("id")
            if channel_id:
                mapping[channel_id] = item

        return mapping

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            if value in (None, ""):
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _extract_subscriber_count(self, channel_data: dict | None) -> int:
        if not channel_data:
            return 1

        stats = channel_data.get("statistics", {})
        return max(self._safe_int(stats.get("subscriberCount"), 1), 1)

    def _map_video_categories(self, category_data: dict) -> Dict[str, str]:
        mapping: Dict[str, str] = {}

        for item in category_data.get("items", []):
            category_id = item.get("id")
            title = item.get("snippet", {}).get("title")
            if category_id and title:
                mapping[category_id] = title

        return mapping

    def _hours_since_published(self, published_at: str | None) -> float | None:
        if not published_at:
            return None

        published_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        return max(
            (datetime.now(timezone.utc) - published_dt).total_seconds() / 3600,
            1.0,
        )

    def _score_log_ratio(self, value: float, strong_at: float) -> float:
        value = max(value, 0.0)
        strong_at = max(strong_at, 1e-6)
        return round(
            min(log1p(value) / log1p(strong_at), 1.0) * 10,
            4,
        )

    def _freshness_score(self, age_hours: float) -> float:
        if age_hours <= 6:
            return 10.0
        if age_hours <= 12:
            return 9.0
        if age_hours <= 24:
            return 8.0
        if age_hours <= 48:
            return 6.5
        if age_hours <= 72:
            return 5.0
        return 3.0

    def _speed_score(self, views_per_hour: float, age_hours: float) -> float:
        if age_hours <= 6:
            strong_at = 1500.0
        elif age_hours <= 24:
            strong_at = 800.0
        elif age_hours <= 72:
            strong_at = 400.0
        else:
            strong_at = 250.0

        return self._score_log_ratio(views_per_hour, strong_at)

    def _engagement_score(self, likes_per_1k: float, comments_per_1k: float) -> float:
        like_score = self._score_log_ratio(likes_per_1k, 60.0)
        comment_score = self._score_log_ratio(comments_per_1k, 15.0)
        return round(
            min((like_score * 0.45) + (comment_score * 0.55), 10.0),
            4,
        )

    def _breakout_score(
        self,
        *,
        views: int,
        subscriber_count: int | None,
        channel_view_count: int,
        channel_video_count: int,
        hidden_subscriber_count: bool,
    ) -> float:
        channel_avg_views = 0.0
        if channel_video_count > 0 and channel_view_count > 0:
            channel_avg_views = channel_view_count / channel_video_count

        baseline_ratio = views / max(channel_avg_views, 100.0)
        baseline_score = self._score_log_ratio(baseline_ratio, 4.0)

        subscriber_score = 0.0
        if not hidden_subscriber_count and subscriber_count:
            views_vs_subs = views / max(subscriber_count, 1)
            subscriber_score = self._score_log_ratio(views_vs_subs, 1.0)

        if subscriber_score and baseline_score:
            combined = (baseline_score * 0.7) + (subscriber_score * 0.3)
        else:
            combined = max(baseline_score, subscriber_score)

        return round(min(combined, 10.0), 4)

    def _confidence_score(
        self,
        *,
        views: int,
        likes: int,
        comments: int,
        subscriber_count: int | None,
        channel_view_count: int,
        channel_video_count: int,
        hidden_subscriber_count: bool,
    ) -> float:
        stats_present = [
            views > 0,
            likes > 0,
            comments >= 0,
            channel_view_count > 0,
            channel_video_count > 0,
            hidden_subscriber_count or bool(subscriber_count),
        ]
        coverage_score = (sum(stats_present) / len(stats_present)) * 10

        sample_score = (
            self._score_log_ratio(views, 5000.0) * 0.55
            + self._score_log_ratio(likes, 250.0) * 0.2
            + self._score_log_ratio(comments, 50.0) * 0.25
        )

        return round(
            min((coverage_score * 0.35) + (sample_score * 0.65), 10.0),
            4,
        )

    def _classify_trend_stage(
        self,
        *,
        age_hours: float,
        virality_score: float,
        speed_score: float,
        breakout_score: float,
        engagement_score: float,
    ) -> str:
        if virality_score >= 8.5 or (speed_score >= 8.0 and breakout_score >= 7.0):
            return "trending"

        if age_hours <= 48 and breakout_score >= 6.5 and (
            speed_score >= 5.0 or engagement_score >= 5.0
        ):
            return "breakout"

        if age_hours <= 12 and (speed_score >= 4.5 or breakout_score >= 4.5):
            return "emerging"

        if age_hours > 24 and virality_score >= 6.0:
            return "sustained_demand"

        return "watchlist"

    def _calculate_trend_metrics(
        self,
        video: dict,
        channel_data: dict | None,
    ) -> dict[str, float | str]:
        stats = video.get("statistics", {})
        snippet = video.get("snippet", {})
        channel_stats = (channel_data or {}).get("statistics", {})

        views = self._safe_int(stats.get("viewCount"))
        likes = self._safe_int(stats.get("likeCount"))
        comments = self._safe_int(stats.get("commentCount"))
        age_hours = self._hours_since_published(snippet.get("publishedAt")) or 1.0

        subscriber_count = self._safe_int(channel_stats.get("subscriberCount"), 0) or None
        channel_view_count = self._safe_int(channel_stats.get("viewCount"))
        channel_video_count = self._safe_int(channel_stats.get("videoCount"))
        hidden_subscriber_count = bool(channel_stats.get("hiddenSubscriberCount", False))

        views_per_hour = views / max(age_hours, 1.0)
        likes_per_1k = (likes * 1000) / max(views, 1)
        comments_per_1k = (comments * 1000) / max(views, 1)

        speed_score = self._speed_score(views_per_hour, age_hours)
        breakout_score = self._breakout_score(
            views=views,
            subscriber_count=subscriber_count,
            channel_view_count=channel_view_count,
            channel_video_count=channel_video_count,
            hidden_subscriber_count=hidden_subscriber_count,
        )
        engagement_score = self._engagement_score(likes_per_1k, comments_per_1k)
        freshness_score = self._freshness_score(age_hours)
        confidence_score = self._confidence_score(
            views=views,
            likes=likes,
            comments=comments,
            subscriber_count=subscriber_count,
            channel_view_count=channel_view_count,
            channel_video_count=channel_video_count,
            hidden_subscriber_count=hidden_subscriber_count,
        )

        virality_score = round(
            (speed_score * 0.35)
            + (breakout_score * 0.30)
            + (engagement_score * 0.20)
            + (freshness_score * 0.10)
            + (confidence_score * 0.05),
            4,
        )

        trend_stage = self._classify_trend_stage(
            age_hours=age_hours,
            virality_score=virality_score,
            speed_score=speed_score,
            breakout_score=breakout_score,
            engagement_score=engagement_score,
        )

        return {
            "virality_score": virality_score,
            "speed_score": speed_score,
            "breakout_score": breakout_score,
            "engagement_score": engagement_score,
            "freshness_score": freshness_score,
            "confidence_score": confidence_score,
            "trend_stage": trend_stage,
        }

    def _extract_keywords(self, title: str):
        title = title.lower()
        words = re.findall(r"\b[a-zA-Z]{3,}\b", title)

        return [
            " ".join(words[i : i + 2])
            for i in range(len(words) - 1)
        ]

    async def scan_popular(self, region_code: str, max_results: int = 10):
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
        channel_map = self._map_channels_by_id(channel_data)

        processed = 0

        for video in items:
            channel_id = video["snippet"]["channelId"]
            channel = channel_map.get(channel_id)
            analytics = self._calculate_trend_metrics(video, channel)
            category_id = video.get("snippet", {}).get("categoryId")
            category_title = category_map.get(category_id, "Unknown")

            await create_or_update(
                db=self.db,
                keyword_id=None,
                video_data=video,
                channel_data=channel,
                score=analytics["virality_score"],
                analytics=analytics,
                category_title=category_title,
                region_code=region_code,
                source="POPULAR",
            )

            processed += 1

        return processed
