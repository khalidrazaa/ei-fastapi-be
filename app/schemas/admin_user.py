from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Annotated
from datetime import date

GenderStr = Annotated[
    str,
    Field(
        pattern="^(male|female|other)$",
        description="Allowed values: male, female, other",
    ),
]


class AdminUserCreate(BaseModel):
    email: EmailStr
    phone: Annotated[str, Field(min_length=10, max_length=15)]
    full_name: str
    gender: GenderStr
    dob: date
    is_active: bool = False

    model_config = ConfigDict(from_attributes=True)
