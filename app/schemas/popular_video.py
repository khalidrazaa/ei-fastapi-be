from datetime import datetime
from typing import Optional

from pydantic import BaseModel, computed_field


class PopularVideoOut(BaseModel):
    id: int
    keyword_id: Optional[int] = None
    youtube_video_id: str
    title: str
    channel_title: str
    view_count: int
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    published_at: datetime
    scanned_at: datetime
    virality_score: float
    thumbnail_url: str
    source: str
    region_code: Optional[str] = None

    @computed_field
    @property
    def youtube_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.youtube_video_id}"

    class Config:
        from_attributes = True
