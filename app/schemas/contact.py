import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ContactRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    email: EmailStr = Field(max_length=254)
    message: str = Field(min_length=1, max_length=5000)
    phone: str | None = None

    @field_validator("name", "email", "message", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Value must be a string.")
        return value.strip()

    @field_validator("name")
    @classmethod
    def validate_reply_to_name(cls, value: str) -> str:
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError("Name must be a single line.")
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Phone must be a string or null.")
        if len(value) > 40:
            raise ValueError("Phone must be at most 40 characters.")
        if re.fullmatch(r"[+0-9 ()-]*", value) is None:
            raise ValueError("Phone contains unsupported characters.")
        trimmed = value.strip()
        if not trimmed:
            return None
        if not trimmed.startswith("+"):
            raise ValueError("Phone must include a leading + and country code.")
        normalized = re.sub(r"[ ()-]", "", trimmed)
        if re.fullmatch(r"\+[1-9][0-9]{6,14}", normalized) is None:
            raise ValueError("Phone must contain 7 to 15 international digits.")
        return normalized


class ContactResponse(BaseModel):
    status: bool
    message: str
