from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TrendVideoBase(BaseModel):
    niche_id: int
    youtube_video_id: str
    title: str
    channel_title: str
    view_count: int
    like_count: Optional[int] = 0
    comment_count: Optional[int] = 0
    published_at: datetime
    virality_score: float


class TrendVideoCreate(TrendVideoBase):
    pass


class TrendVideoOut(TrendVideoBase):
    id: int
    scanned_at: datetime

    class Config:
        from_attributes = True