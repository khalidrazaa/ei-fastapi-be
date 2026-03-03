# app/services/youtube_service.py
from googleapiclient.discovery import build
from app.core.config import settings
from datetime import datetime, timedelta, timezone

class YouTubeService:
    def __init__(self):
        self.youtube = build('youtube', 'v3', developerKey=settings.YOUTUBE_API_KEY)

    async def find_breakout_videos(self, keywords: list[str], max_results: int = 5):
        """
        Finds videos that are performing significantly better than the channel's average.
        """
        # 1. Calculate the 'last 24 hours' timestamp in RFC 3339 format
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        
        all_candidates = []

        # 2. Search for videos per keyword (Cost: 100 units per search)
        for query in keywords:
            search_request = self.youtube.search().list(
                part="id,snippet",
                q=query,
                type="video",
                publishedAfter=yesterday,
                order="viewCount",
                maxResults=max_results
            )
            search_response = search_request.execute()

            video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
            if not video_ids:
                continue

            # 3. Get detailed stats for these videos (Cost: 1 unit)
            video_stats_req = self.youtube.videos().list(
                part="statistics,snippet",
                id=",".join(video_ids)
            )
            video_stats = video_stats_req.execute()

            for video in video_stats.get('items', []):
                channel_id = video['snippet']['channelId']
                views = int(video['statistics'].get('viewCount', 0))

                # 4. Get Channel Stats to calculate 'Viral Velocity' (Cost: 1 unit)
                channel_req = self.youtube.channels().list(
                    part="statistics",
                    id=channel_id
                )
                channel_res = channel_req.execute()
                
                if not channel_res['items']:
                    continue
                    
                subs = int(channel_res['items'][0]['statistics'].get('subscriberCount', 1)) # Default 1 to avoid div by zero
                
                # Viral Velocity = Views / Subscribers (A crude but effective breakout metric)
                velocity = round(views / subs if subs > 0 else 0, 2)

                all_candidates.append({
                    "title": video['snippet']['title'],
                    "video_id": video['id'],
                    "channel": video['snippet']['channelTitle'],
                    "views": views,
                    "subs": subs,
                    "velocity": velocity,
                    "thumbnail": video['snippet']['thumbnails']['high']['url']
                })

        # Sort by velocity descending
        return sorted(all_candidates, key=lambda x: x['velocity'], reverse=True)