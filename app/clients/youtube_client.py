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
        region_code: str | None = None,
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
        if region_code:
            params["regionCode"] = region_code

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

    async def get_video_categories(
        self,
        region_code: str = "US",
    ) -> Dict[str, Any]:
        """
        Get localized video categories for a region.
        """
        url = f"{self.BASE_URL}/videoCategories"

        params = {
            "part": "snippet",
            "regionCode": region_code,
            "key": self.api_key,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()


    async def get_trending_videos(
        self,
        region_code: str,
        max_results: int = 5,
    ) -> dict:
        """
        Fetch most popular (trending) videos for a region.
        Uses YouTube 'videos' endpoint with chart=mostPopular.
        """
    
        url = f"{self.BASE_URL}/videos"
    
        params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": max_results,
            "key": self.api_key,
        }
    
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
