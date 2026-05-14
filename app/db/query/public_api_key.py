from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.host_site import HostSite
from app.db.models.public_api_key import PublicApiKey


async def list_public_api_keys(
    db: AsyncSession,
    *,
    host_site_id: int | None = None,
    active_only: bool = False,
) -> list[tuple[PublicApiKey, HostSite]]:
    query = (
        select(PublicApiKey, HostSite)
        .join(HostSite, PublicApiKey.host_site_id == HostSite.id)
        .order_by(PublicApiKey.created_at.desc(), PublicApiKey.id.desc())
    )

    if host_site_id is not None:
        query = query.where(PublicApiKey.host_site_id == host_site_id)

    if active_only:
        query = query.where(PublicApiKey.is_active.is_(True))

    result = await db.execute(query)
    return list(result.all())


async def get_public_api_key_by_id(
    db: AsyncSession,
    api_key_id: int,
) -> PublicApiKey | None:
    result = await db.execute(select(PublicApiKey).where(PublicApiKey.id == api_key_id))
    return result.scalar_one_or_none()


async def get_public_api_key_by_hash(
    db: AsyncSession,
    key_hash: str,
) -> PublicApiKey | None:
    result = await db.execute(
        select(PublicApiKey).where(PublicApiKey.key_hash == key_hash)
    )
    return result.scalar_one_or_none()


async def create_public_api_key(
    db: AsyncSession,
    *,
    host_site_id: int,
    name: str,
    key_prefix: str,
    key_hash: str,
) -> PublicApiKey:
    api_key = PublicApiKey(
        host_site_id=host_site_id,
        name=name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        is_active=True,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key


async def revoke_public_api_key(
    db: AsyncSession,
    api_key: PublicApiKey,
    *,
    revoked_at: datetime,
) -> PublicApiKey:
    api_key.is_active = False
    api_key.revoked_at = revoked_at
    await db.commit()
    await db.refresh(api_key)
    return api_key


async def get_active_public_api_key_by_host_and_hash(
    db: AsyncSession,
    *,
    host: str,
    key_hash: str,
) -> PublicApiKey | None:
    query = (
        select(PublicApiKey)
        .join(HostSite, PublicApiKey.host_site_id == HostSite.id)
        .where(HostSite.host == host)
        .where(HostSite.is_active.is_(True))
        .where(PublicApiKey.is_active.is_(True))
        .where(PublicApiKey.key_hash == key_hash)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()
