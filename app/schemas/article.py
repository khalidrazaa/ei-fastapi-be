from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Shared properties
class ArticleBase(BaseModel):
    title: str
    seo_title: Optional[str] = None
    slug: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    status: str = "draft"
    content: Optional[str] = None
    excerpt: Optional[str] = None
    reading_time: Optional[int] = None
    featured_image_url: Optional[str] = None
    image_alt_text: Optional[str] = None
    language: Optional[str] = "en"
    host_site: str = "explainit.tech"
    is_featured: bool = False
    drafted_at: Optional[datetime] = None
    meta_description: Optional[str] = None
    canonical_url: Optional[str] = None
    schema_type: Optional[str] = "Article"
    open_graph_title: Optional[str] = None
    open_graph_description: Optional[str] = None
    open_graph_image: Optional[str] = None

    @field_validator("tags", "keywords", mode="before")
    @classmethod
    def default_empty_lists(cls, value):
        return value or []

    @field_validator("status", mode="before")
    @classmethod
    def default_status(cls, value):
        return value or "draft"

    @field_validator("host_site", mode="before")
    @classmethod
    def default_host_site(cls, value):
        return value or "explainit.tech"

    @field_validator("language", mode="before")
    @classmethod
    def default_language(cls, value):
        return value or "en"

    @field_validator("schema_type", mode="before")
    @classmethod
    def default_schema_type(cls, value):
        return value or "Article"


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
    tags: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    status: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    reading_time: Optional[int] = None
    featured_image_url: Optional[str] = None
    image_alt_text: Optional[str] = None
    language: Optional[str] = None
    host_site: Optional[str] = None
    is_featured: Optional[bool] = None
    drafted_at: Optional[datetime] = None
    meta_description: Optional[str] = None
    canonical_url: Optional[str] = None
    schema_type: Optional[str] = None
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


class ArticleDraftGenerateRequest(BaseModel):
    provider: Literal["gemini", "chatgpt"] = "gemini"
    prompt: Optional[str] = None
    additional_context: Optional[str] = None
