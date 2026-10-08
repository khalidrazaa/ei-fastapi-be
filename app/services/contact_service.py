from collections import deque
from math import ceil
from threading import Lock
from time import monotonic

from app.schemas.contact import ContactRequest
from app.utils.email import (
    ContactEmailConfigurationError as ContactEmailConfigurationError,
    ContactEmailProviderError as ContactEmailProviderError,
    ContactEmailTimeoutError as ContactEmailTimeoutError,
    send_contact_email,
)


class ContactHostError(Exception):
    pass


class ContactRateLimitError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Contact submission limit reached.")


class _ContactRateLimiter:
    """Small process-local cap; shared limits require a proxy or shared store."""

    def __init__(self, *, window_seconds: int = 60, max_attempts: int = 20):
        self.window_seconds = window_seconds
        self.max_attempts = max_attempts
        self._attempts: deque[float] = deque()
        self._emails: dict[str, float] = {}
        self._lock = Lock()

    def take(self, email: str) -> None:
        email_key = email.casefold()
        with self._lock:
            now = monotonic()
            cutoff = now - self.window_seconds
            while self._attempts and self._attempts[0] <= cutoff:
                self._attempts.popleft()
            self._emails = {
                key: timestamp
                for key, timestamp in self._emails.items()
                if timestamp > cutoff
            }
            previous = self._emails.get(email_key)
            if previous is not None:
                raise ContactRateLimitError(
                    max(1, ceil(previous + self.window_seconds - now))
                )
            if len(self._attempts) >= self.max_attempts:
                raise ContactRateLimitError(
                    max(1, ceil(self._attempts[0] + self.window_seconds - now))
                )
            self._emails[email_key] = now
            self._attempts.append(now)


_rate_limiter = _ContactRateLimiter()


async def send_contact_message(payload: ContactRequest, host_site: str) -> None:
    if host_site != "explainit.tech":
        raise ContactHostError("Contact is only available for explainit.tech.")
    _rate_limiter.take(str(payload.email))
    await send_contact_email(
        name=payload.name, email=str(payload.email), message=payload.message,
        phone=payload.phone,
    )
