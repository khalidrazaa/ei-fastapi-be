import re
from urllib.parse import urlsplit, urlunsplit

import phonenumbers
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ContactRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    email: EmailStr = Field(max_length=254)
    message: str = Field(min_length=1, max_length=5000)
    phone: str | None = None
    subject: str | None = Field(default=None, max_length=200)
    landing_page: str | None = Field(default=None, max_length=2048)
    referrer: str | None = Field(default=None, max_length=2048)
    utm_source: str | None = Field(default=None, max_length=200)
    utm_medium: str | None = Field(default=None, max_length=200)
    utm_campaign: str | None = Field(default=None, max_length=200)
    utm_term: str | None = Field(default=None, max_length=200)
    utm_content: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=200)

    @field_validator("website")
    @classmethod
    def validate_honeypot(cls, value: str | None) -> str | None:
        if value:
            raise ValueError("Unable to accept this submission.")
        return None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Message contains unsupported characters.")
        return value

    @field_validator(
        "subject", "utm_source", "utm_medium", "utm_campaign", "utm_term",
        "utm_content", "landing_page", "referrer",
    )
    @classmethod
    def validate_metadata(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Source information must be a single line.")
        return value.strip() or None

    @field_validator("landing_page", "referrer")
    @classmethod
    def sanitize_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or "\\" in value or any(c.isspace() for c in value)
        ):
            raise ValueError("Source URL must be an HTTP(S) URL without credentials.")
        try:
            parsed.port
        except ValueError:
            raise ValueError("Source URL has an invalid port.") from None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

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
        if re.fullmatch(r"\+[1-9][0-9]{0,14}", normalized) is None:
            raise ValueError("Phone must contain at most 15 international digits.")
        try:
            number = phonenumbers.parse(normalized, None)
        except phonenumbers.NumberParseException:
            raise ValueError("Enter a valid international phone number.") from None
        if not phonenumbers.is_valid_number(number):
            raise ValueError("Enter a valid international phone number.")
        canonical = phonenumbers.format_number(
            number, phonenumbers.PhoneNumberFormat.E164
        )
        if re.fullmatch(r"\+[1-9][0-9]{0,14}", canonical) is None:
            raise ValueError("Phone must contain at most 15 international digits.")
        return canonical


class ContactResponse(BaseModel):
    status: bool
    message: str
