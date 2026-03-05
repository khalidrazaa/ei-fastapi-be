from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TrendVideoBase(BaseModel):
    keyword_id: int   # ✅ FIXED
    youtube_video_id: str
    title: str
    channel_title: str
    view_count: int
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    published_at: datetime
    virality_score: float


class TrendVideoCreate(TrendVideoBase):
    pass


class TrendVideoOut(TrendVideoBase):
    id: int
    scanned_at: datetime

    class Config:
        from_attributes = True