# app/schemas/niche.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Optional

# --- Keyword Schemas ---

class NicheKeywordBase(BaseModel):
    keyword: str

class NicheKeywordCreate(NicheKeywordBase):
    pass

class NicheKeyword(NicheKeywordBase):
    id: int
    niche_id: int
    created_at: datetime
    
    # Allows Pydantic to read data from SQLAlchemy objects
    model_config = ConfigDict(from_attributes=True)


# --- Niche Schemas ---

class NicheBase(BaseModel):
    name: str          # e.g., "tech_ai"
    display_name: str  # e.g., "Tech & AI"

class NicheCreate(NicheBase):
    """Schema for creating a new niche"""
    pass

class Niche(NicheBase):
    """Schema for returning niche info (no keywords)"""
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class NicheWithKeywords(Niche):
    """Schema for returning niche info WITH its list of keywords"""
    keywords: List[NicheKeyword] = []

    model_config = ConfigDict(from_attributes=True)