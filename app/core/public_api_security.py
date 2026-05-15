import hmac
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.services.public_api_key import normalize_host, validate_public_api_key


@lru_cache(maxsize=1)
def _public_key_map() -> dict[str, str]:
    raw_value = (settings.PUBLIC_APP_KEYS or "").strip()
    key_map: dict[str, str] = {}
    if not raw_value:
        return key_map

    for pair in raw_value.split(","):
        cleaned_pair = pair.strip()
        if not cleaned_pair:
            continue

        separator = ":" if ":" in cleaned_pair else "="
        if separator not in cleaned_pair:
            continue

        host_part, key_part = cleaned_pair.split(separator, 1)
        try:
            host = normalize_host(host_part)
        except ValueError:
            continue
        key = key_part.strip()
        if host and key:
            key_map[host] = key

    return key_map


async def verify_public_app_access(
    host_site: str = Query(..., min_length=3, max_length=120),
    x_public_app_key: str | None = Header(default=None, alias="X-Public-App-Key"),
    db: AsyncSession = Depends(get_db),
) -> str:
    try:
        normalized_host = normalize_host(host_site)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    if not x_public_app_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing public app key.",
        )

    if await validate_public_api_key(
        db,
        host=normalized_host,
        raw_key=x_public_app_key,
    ):
        return normalized_host

    # Optional fallback to env map for backward compatibility.
    key_map = _public_key_map()
    expected_key = key_map.get(normalized_host)
    if expected_key and hmac.compare_digest(x_public_app_key.strip(), expected_key):
        return normalized_host

    if key_map and normalized_host not in key_map:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Host site is not allowed for this API.",
        )

    if not key_map:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active public API key configured for this host site.",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid public app key.",
    )
