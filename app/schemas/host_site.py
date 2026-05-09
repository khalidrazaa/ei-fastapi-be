from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class HostSiteBase(BaseModel):
    host: str
    is_active: bool = True


class HostSiteCreate(HostSiteBase):
    pass


class HostSiteUpdate(BaseModel):
    host: Optional[str] = None
    is_active: Optional[bool] = None


class HostSiteResponse(HostSiteBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
