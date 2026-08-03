# app/schemas/niche.py
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import List, Optional

class NicheBase(BaseModel):
    name: str
    display_name: str
    region_code: str = "US"
    scan_mode: str = "most_popular"
    is_active: bool = True


class NicheCreate(NicheBase):
    keywords: List[str] = []


class NicheUpdate(BaseModel):
    display_name: Optional[str] = None
    region_code: Optional[str] = None
    scan_mode: Optional[str] = None
    is_active: Optional[bool] = None

class NicheKeywordOut(BaseModel):
    id: int
    keyword: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class NicheOut(NicheBase):
    id: int
    last_scanned_at: Optional[datetime]
    created_at: datetime
    keywords: List[NicheKeywordOut] = Field(default_factory=list)
    class Config:
        from_attributes = True


NicheOut.model_rebuild()