from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DraftPromptBase(BaseModel):
    name: str
    prompt: str
    is_active: bool = True


class DraftPromptCreate(DraftPromptBase):
    pass


class DraftPromptUpdate(BaseModel):
    name: Optional[str] = None
    prompt: Optional[str] = None
    is_active: Optional[bool] = None


class DraftPromptResponse(DraftPromptBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
