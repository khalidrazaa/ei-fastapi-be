from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PublicApiKeyGenerateRequest(BaseModel):
    host: str = Field(..., min_length=3, max_length=180)
    name: str = Field(default="Public App Key", min_length=2, max_length=120)
    deactivate_old_keys: bool = False

    @field_validator("host", "name", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Value is required.")
        return normalized


class PublicApiKeyResponse(BaseModel):
    id: int
    host_site_id: int
    host: str
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PublicApiKeyGenerateResponse(PublicApiKeyResponse):
    api_key: str
