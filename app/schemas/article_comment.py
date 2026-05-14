from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ArticleCommentCreate(BaseModel):
    author_name: str = Field(..., min_length=2, max_length=80)
    content: str = Field(..., min_length=2, max_length=2000)

    @field_validator("author_name", "content", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Value cannot be empty.")
        return normalized


class ArticleCommentResponse(BaseModel):
    id: int
    article_id: int
    host_site: str
    author_name: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
