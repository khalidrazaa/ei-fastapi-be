from typing import List

from pydantic import BaseModel, Field


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


class YouTubeRegionOut(BaseModel):
    code: str
    name: str


class PopularScanSettingsBase(BaseModel):
    region_codes: List[str] = Field(default_factory=list)
    max_results: int = Field(default=10, ge=1, le=50)


class PopularScanSettingsOut(PopularScanSettingsBase):
    available_regions: List[YouTubeRegionOut] = Field(default_factory=list)


class PopularScanSettingsUpdate(PopularScanSettingsBase):
    pass


class PopularScanRunResponse(BaseModel):
    status: str
    regions: List[str]
    max_results: int
    total_processed: int
