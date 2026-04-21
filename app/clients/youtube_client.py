import httpx
from typing import List, Dict, Any


class YouTubeClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3"
    MAX_IDS_PER_REQUEST = 50

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _chunk_ids(self, ids: List[str]) -> List[List[str]]:
        cleaned_ids = [item for item in ids if item]
        return [
            cleaned_ids[index : index + self.MAX_IDS_PER_REQUEST]
            for index in range(0, len(cleaned_ids), self.MAX_IDS_PER_REQUEST)
        ]

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
        Get detailed metadata for videos.
        """
        url = f"{self.BASE_URL}/videos"
        items: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=30) as client:
            for chunk in self._chunk_ids(video_ids):
                params = {
                    "part": "statistics,snippet,contentDetails,status",
                    "id": ",".join(chunk),
                    "key": self.api_key,
                }

                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
                items.extend(payload.get("items", []))

        return {"items": items}

    async def get_channel_details(
        self,
        channel_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Get channel metadata and stats.
        """
        url = f"{self.BASE_URL}/channels"
        items: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=30) as client:
            for chunk in self._chunk_ids(channel_ids):
                params = {
                    "part": "snippet,statistics",
                    "id": ",".join(chunk),
                    "key": self.api_key,
                }

                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
                items.extend(payload.get("items", []))

        return {"items": items}

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
