from pydantic import BaseModel
from typing import List


class YouTubeVideoOut(BaseModel):
    youtube_video_id: str
    title: str
    channel_title: str
    published_at: str

    class Config:
        from_attributes = True


class YouTubeScanResponse(BaseModel):
    keyword_id: int
    videos_saved: int
    videos: List[YouTubeVideoOut]