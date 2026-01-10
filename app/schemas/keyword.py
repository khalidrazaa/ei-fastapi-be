from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime


class KeywordSuggestion(BaseModel):
    suggestion: str
    source: str


class KeywordRequest(BaseModel):
    keyword: str


# General DB create/read models (keep for CRUD endpoints if you use them)
class KeywordBase(BaseModel):
    keyword: str
    source: Optional[str] = None
    monthly_searches: Optional[int] = None
    cpc: Optional[float] = None
    seo_difficulty: Optional[float] = None
    suggestions: Optional[List[Dict[str, str]]] = Field(default_factory=list)


class KeywordCreate(KeywordBase):
    pass


class KeywordRead(KeywordBase):
    id: int
    processed: bool = False
    article_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Response used by /keywords API: returns the searched keyword + suggestions
class KeywordResponse(BaseModel):
    keyword: str
    suggestions: List[KeywordSuggestion] = Field(default_factory=list)
    # include optional metrics if you have them; keep them optional
    monthly_searches: Optional[int] = None
    cpc: Optional[float] = None
    seo_difficulty: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)
