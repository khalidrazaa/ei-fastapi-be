import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.query import host_site as host_site_query
from app.db.query import public_api_key as public_api_key_query


def normalize_host(value: str) -> str:
    normalized = str(value or "").strip().lower()

    if normalized.startswith("http://"):
        normalized = normalized[7:]
    elif normalized.startswith("https://"):
        normalized = normalized[8:]

    normalized = normalized.split("/", 1)[0].strip().strip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]

    if not normalized:
        raise ValueError("Host site is required.")

    if " " in normalized:
        raise ValueError("Host site cannot contain spaces.")

    return normalized


def _normalize_name(value: str) -> str:
    normalized = str(value or "").strip()
    if len(normalized) < 2:
        raise ValueError("Name must be at least 2 characters.")
    if len(normalized) > 120:
        raise ValueError("Name must be at most 120 characters.")
    return normalized


def hash_public_api_key(raw_key: str) -> str:
    secret = settings.SECRET_KEY.encode("utf-8")
    payload = raw_key.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _build_api_key_prefix(raw_key: str) -> str:
    return raw_key[:12]


def _build_api_key_value() -> str:
    token = secrets.token_urlsafe(42)
    return f"ei_pk_{token}"


def _serialize_public_api_key(api_key: object, host: str) -> dict:
    return {
        "id": api_key.id,
        "host_site_id": api_key.host_site_id,
        "host": host,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "is_active": api_key.is_active,
        "created_at": api_key.created_at,
        "revoked_at": api_key.revoked_at,
        "last_used_at": api_key.last_used_at,
    }


async def get_public_api_keys(
    db: AsyncSession,
    *,
    active_only: bool = False,
    host: str | None = None,
) -> list[dict]:
    host_site_id: int | None = None
    if host is not None:
        normalized_host = normalize_host(host)
        host_site = await host_site_query.get_host_site_by_host(db, normalized_host)
        if host_site is None:
            return []
        host_site_id = host_site.id

    rows = await public_api_key_query.list_public_api_keys(
        db,
        host_site_id=host_site_id,
        active_only=active_only,
    )
    return [_serialize_public_api_key(api_key, host_site.host) for api_key, host_site in rows]


async def generate_public_api_key(
    db: AsyncSession,
    *,
    host: str,
    name: str = "Public App Key",
    deactivate_old_keys: bool = False,
) -> dict:
    normalized_host = normalize_host(host)
    normalized_name = _normalize_name(name)

    host_site = await host_site_query.get_host_site_by_host(db, normalized_host)
    if host_site is None:
        raise LookupError("Host site not found. Create it first in host-site settings.")
    if not host_site.is_active:
        raise ValueError("Host site is inactive. Activate it before generating keys.")

    while True:
        raw_key = _build_api_key_value()
        key_hash = hash_public_api_key(raw_key)
        existing = await public_api_key_query.get_public_api_key_by_hash(db, key_hash)
        if existing is None:
            break

    created = await public_api_key_query.create_public_api_key(
        db,
        host_site_id=host_site.id,
        name=normalized_name,
        key_prefix=_build_api_key_prefix(raw_key),
        key_hash=key_hash,
    )

    if deactivate_old_keys:
        key_rows = await public_api_key_query.list_public_api_keys(
            db,
            host_site_id=host_site.id,
            active_only=True,
        )
        now = datetime.now(timezone.utc)
        for api_key, _ in key_rows:
            if api_key.id == created.id:
                continue
            await public_api_key_query.revoke_public_api_key(
                db,
                api_key,
                revoked_at=now,
            )

    response_payload = _serialize_public_api_key(created, host_site.host)
    response_payload["api_key"] = raw_key
    return response_payload


async def revoke_public_api_key(
    db: AsyncSession,
    api_key_id: int,
) -> dict:
    api_key = await public_api_key_query.get_public_api_key_by_id(db, api_key_id)
    if api_key is None:
        raise LookupError("Public API key not found.")

    host_site = await host_site_query.get_host_site_by_id(db, api_key.host_site_id)
    if host_site is None:
        raise LookupError("Host site not found.")

    if not api_key.is_active:
        return _serialize_public_api_key(api_key, host_site.host)

    revoked = await public_api_key_query.revoke_public_api_key(
        db,
        api_key,
        revoked_at=datetime.now(timezone.utc),
    )
    return _serialize_public_api_key(revoked, host_site.host)


async def validate_public_api_key(
    db: AsyncSession,
    *,
    host: str,
    raw_key: str,
) -> bool:
    normalized_host = normalize_host(host)
    normalized_key = str(raw_key or "").strip()
    if not normalized_key:
        return False

    key_hash = hash_public_api_key(normalized_key)
    match = await public_api_key_query.get_active_public_api_key_by_host_and_hash(
        db,
        host=normalized_host,
        key_hash=key_hash,
    )
    return match is not None
