# app/services/youtube_scan_service.py

from datetime import datetime, timedelta, timezone
from typing import List, Dict
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.clients.youtube_client import YouTubeClient
from app.db.query.niche import get_keywords_by_niche, get_keyword_by_id
from app.db.query.trend_video import create_or_update
from app.schemas import niche
import re


class YouTubeScanService:
    def __init__(
        self,
        db_session: AsyncSession,
        youtube_client: YouTubeClient,
    ):
        self.db = db_session
        self.youtube = youtube_client

    # ---------------------------------------------------
    # PUBLIC METHODS
    # ---------------------------------------------------

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
                result = await self.scan_keyword(keyword.id)
                total_videos_saved += result
            except Exception as e:
                print(f"Keyword failed {keyword.id}: {str(e)}")
        
        return total_videos_saved

    async def scan_keyword(self, keyword_id: int) -> int:
        """
        Scan breakout videos for a specific keyword.
        Returns number of processed videos.
        """

        keyword = await get_keyword_by_id(self.db, keyword_id)
        if not keyword:
            return 0

        # Last 24 hours filter
        yesterday = (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).isoformat()

        # 1️⃣ Search videos
        search_data = await self.youtube.search_videos(
            query=keyword.keyword,
            max_results=10,
            published_after=yesterday,
            order="viewCount",
        )

        video_ids = self._extract_video_ids(search_data)
        if not video_ids:
            return 0

        # 2️⃣ Fetch full video details
        video_details = await self.youtube.get_video_details(video_ids)

        items = video_details.get("items", [])
        if not items:
            return 0

        # 3️⃣ Collect channel IDs
        channel_ids = list(
            {item["snippet"]["channelId"] for item in items}
        )

        channel_data = await self.youtube.get_channel_details(channel_ids)
        subscriber_map = self._map_channel_subscribers(channel_data)

        # 4️⃣ Process & store
        processed = 0

        for video in items:
            channel_id = video["snippet"]["channelId"]
            subs = subscriber_map.get(channel_id, 1)

            score = self._calculate_velocity(video, subs)

            await create_or_update(
                db=self.db,
                keyword_id=keyword_id,
                video_data=video,
                score=score,
            )

            processed += 1

        return processed

    # ---------------------------------------------------
    # INTERNAL METHODS
    # ---------------------------------------------------

    def _extract_video_ids(self, search_data: dict) -> List[str]:
        items = search_data.get("items", [])
        return [
            item["id"]["videoId"]
            for item in items
            if "videoId" in item.get("id", {})
        ]

    def _map_channel_subscribers(self, channel_data: dict) -> Dict[str, int]:
        """
        Create mapping: channel_id -> subscriber_count
        """
        mapping = {}

        for item in channel_data.get("items", []):
            channel_id = item["id"]
            stats = item.get("statistics", {})
            subs = int(stats.get("subscriberCount", 1))
            mapping[channel_id] = subs

        return mapping

    def _calculate_velocity(self, video: dict, subs: int) -> float:
        """
        Viral Velocity = views / subscribers
        """
        #stats = video.get("statistics", {})
        #views = int(stats.get("viewCount", 0))

        #if subs <= 0:
        #    return 0.0

        #return round(views / subs, 2)

        stats = video.get("statistics", {})
        snippet = video.get("snippet", {})

        views = int(stats.get("viewCount", 0))
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

        if subs <= 0:
            subs = 1

        velocity = (views / hours) / subs

        return round(velocity, 4)  
    
    def _extract_keywords(self, title: str):
        """
        Simple keyword extraction from video titles
        """
        title = title.lower()

        words = re.findall(r"\b[a-zA-Z]{3,}\b", title)

        phrases = [
            " ".join(words[i:i+2])
            for i in range(len(words)-1)
        ]

        return phrases
    
    # ---------------------------------------------------
    # TRENDING SCAN (REGION BASED)
    # ---------------------------------------------------
    async def scan_trending(self, region_code: str) -> int:
        """
        Scan trending videos for a region.
        Returns number of processed videos.
        """

        # 1️⃣ Fetch trending videos
        trending_data = await self.youtube.get_trending_videos(
            region_code=region_code,
            max_results=25,
        )

        video_ids = self._extract_video_ids(trending_data)
        if not video_ids:
            return 0

        # 2️⃣ Fetch full video details
        video_details = await self.youtube.get_video_details(video_ids)

        items = video_details.get("items", [])
        if not items:
            return 0

        # 3️⃣ Collect channel IDs
        channel_ids = list(
            {item["snippet"]["channelId"] for item in items}
        )

        channel_data = await self.youtube.get_channel_details(channel_ids)
        subscriber_map = self._map_channel_subscribers(channel_data)

        # 4️⃣ Process & store
        processed = 0

        for video in items:
            channel_id = video["snippet"]["channelId"]
            subs = subscriber_map.get(channel_id, 1)

            score = self._calculate_velocity(video, subs)

            # 🔑 No keyword_id here → pass None or special flag
            await create_or_update(
                db=self.db,
                keyword_id=None,  # important difference
                video_data=video,
                score=score,
                region_code=region_code,
                source="POPULAR",
            )

            processed += 1

        return processed