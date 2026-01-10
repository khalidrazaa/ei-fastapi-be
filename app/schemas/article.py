from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# Shared properties
class ArticleBase(BaseModel):
    title: str
    seo_title: Optional[str] = None
    slug: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = []
    status: Optional[str] = "draft"
    content: Optional[str] = None
    excerpt: Optional[str] = None
    reading_time: Optional[int] = None
    featured_image: Optional[str] = None
    image_alt: Optional[str] = None
    language: Optional[str] = None
    open_graph_title: Optional[str] = None
    open_graph_description: Optional[str] = None
    open_graph_image: Optional[str] = None


# For creating a new article
class ArticleCreate(ArticleBase):
    title: str
    slug: str
    content: str


# For updating an existing article
class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    seo_title: Optional[str] = None
    slug: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    reading_time: Optional[int] = None
    featured_image: Optional[str] = None
    image_alt: Optional[str] = None
    language: Optional[str] = None
    open_graph_title: Optional[str] = None
    open_graph_description: Optional[str] = None
    open_graph_image: Optional[str] = None


# Response schema (read from DB / return to client)
class ArticleResponse(ArticleBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
