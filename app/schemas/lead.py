from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LeadStatus(str, Enum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    proposal = "proposal"
    won = "won"
    lost = "lost"
    spam = "spam"


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str | None
    subject: str | None
    message: str
    host_site: str
    landing_page: str | None
    referrer: str | None
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    utm_term: str | None
    utm_content: str | None
    status: LeadStatus
    internal_notes: str
    submitted_at: datetime
    updated_at: datetime


class LeadPage(BaseModel):
    items: list[LeadResponse]
    total: int
    page: int
    size: int
    total_pages: int
    has_next: bool
    has_previous: bool


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LeadStatus | None = None
    internal_notes: str | None = Field(default=None, max_length=10000, strict=True)

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide a status or internal notes.")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        if self.internal_notes and "\x00" in self.internal_notes:
            raise ValueError("Notes contain unsupported characters.")
        return self
