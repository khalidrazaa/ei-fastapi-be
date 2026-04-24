from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field


def _hours_since(value: datetime) -> float:
    delta = datetime.now(timezone.utc) - value
    return max(delta.total_seconds() / 3600, 0.0)


class TrendVideoBase(BaseModel):
    keyword_id: Optional[int] = None
    youtube_video_id: str
    youtube_channel_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    channel_title: str
    channel_custom_url: Optional[str] = None
    channel_description: Optional[str] = None
    channel_country: Optional[str] = None
    view_count: int
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    subscriber_count: Optional[int] = None
    channel_view_count: Optional[int] = None
    channel_video_count: Optional[int] = None
    hidden_subscriber_count: Optional[bool] = None
    published_at: datetime
    channel_published_at: Optional[datetime] = None
    virality_score: float
    speed_score: Optional[float] = None
    breakout_score: Optional[float] = None
    engagement_score: Optional[float] = None
    freshness_score: Optional[float] = None
    confidence_score: Optional[float] = None
    trend_stage: Optional[str] = None
    thumbnail_url: str
    channel_thumbnail_url: Optional[str] = None
    category_id: Optional[str] = None
    category_title: str
    transcript_text: Optional[str] = Field(default=None, exclude=True)
    transcript_language_code: Optional[str] = None
    transcript_language: Optional[str] = None
    transcript_source: Optional[str] = None
    transcript_error: Optional[str] = None
    transcript_fetched_at: Optional[datetime] = None
    source: Optional[str] = None
    region_code: Optional[str] = None


class TrendVideoCreate(TrendVideoBase):
    video_payload: Optional[dict[str, Any]] = None
    channel_payload: Optional[dict[str, Any]] = None


class TrendVideoOut(TrendVideoBase):
    id: int
    scanned_at: datetime

    @computed_field
    @property
    def youtube_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.youtube_video_id}"

    @computed_field
    @property
    def age_hours(self) -> float:
        return round(_hours_since(self.published_at), 2)

    @computed_field
    @property
    def views_per_hour(self) -> float:
        return round(self.view_count / max(self.age_hours, 1.0), 2)

    @computed_field
    @property
    def likes_per_1k_views(self) -> float:
        likes = self.like_count or 0
        return round((likes * 1000) / max(self.view_count, 1), 2)

    @computed_field
    @property
    def comments_per_1k_views(self) -> float:
        comments = self.comment_count or 0
        return round((comments * 1000) / max(self.view_count, 1), 2)

    @computed_field
    @property
    def channel_avg_views(self) -> float:
        if not self.channel_view_count or not self.channel_video_count:
            return 0.0
        return round(self.channel_view_count / max(self.channel_video_count, 1), 2)

    @computed_field
    @property
    def views_vs_channel_average(self) -> float:
        return round(self.view_count / max(self.channel_avg_views, 1.0), 2)

    @computed_field
    @property
    def views_vs_subscribers(self) -> Optional[float]:
        if self.hidden_subscriber_count or not self.subscriber_count:
            return None
        return round(self.view_count / max(self.subscriber_count, 1), 2)

    @computed_field
    @property
    def has_transcript(self) -> bool:
        return bool(getattr(self, "transcript_text", None))

    @computed_field
    @property
    def transcript_excerpt(self) -> Optional[str]:
        transcript = getattr(self, "transcript_text", None)
        if not transcript:
            return None

        normalized = " ".join(transcript.split())
        if len(normalized) <= 220:
            return normalized

        return f"{normalized[:217]}..."

    class Config:
        from_attributes = True


class TranscriptContentOut(BaseModel):
    id: int
    title: str
    youtube_video_id: str
    transcript_text: str
    transcript_language: Optional[str] = None
    transcript_source: Optional[str] = None
    transcript_fetched_at: Optional[datetime] = None


class TranscriptContentUpdateIn(BaseModel):
    transcript_text: str
