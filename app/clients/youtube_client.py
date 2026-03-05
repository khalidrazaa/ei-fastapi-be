import httpx
from typing import List, Dict, Any


class YouTubeClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search_videos(
        self,
        query: str,
        max_results: int = 10,
        published_after: str | None = None,
        order: str = "viewCount",
    ) -> Dict[str, Any]:
        """
        Search videos by keyword
        """
        url = f"{self.BASE_URL}/search"

        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "order": order,
            "key": self.api_key,
        }

        if published_after:
            params["publishedAfter"] = published_after

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def get_video_details(
        self,
        video_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Get statistics + snippet for videos
        """
        url = f"{self.BASE_URL}/videos"

        params = {
            "part": "statistics,snippet",
            "id": ",".join(video_ids),
            "key": self.api_key,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def get_channel_details(
        self,
        channel_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Get subscriber stats for channels
        """
        url = f"{self.BASE_URL}/channels"

        params = {
            "part": "statistics",
            "id": ",".join(channel_ids),
            "key": self.api_key,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()