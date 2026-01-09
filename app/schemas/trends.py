from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class VolumePoint(BaseModel):
    ts: datetime = Field(default_factory=datetime.utcnow)
    value: int


class TrendItem(BaseModel):
    trend: str = Field(..., description="The trending keyword/topic")
    search_volume: int = Field(default=0)
    volume_history: List[VolumePoint] = Field(default_factory=list)

    started: Optional[datetime] = None
    ended: Optional[datetime] = None

    trend_breakdown: Optional[str] = None
    explore_link: Optional[str] = None

    is_growing: bool = False
    category: Optional[str] = None
    subcategory: Optional[str] = None

    status: Literal["Open", "Processed", "Ignored"] = "Open"
    draft_id: Optional[str] = None

    last_updated: datetime = Field(default_factory=datetime.utcnow)