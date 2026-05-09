from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.host_site import HostSite


async def get_host_site_by_id(
    db: AsyncSession,
    host_site_id: int,
) -> HostSite | None:
    result = await db.execute(select(HostSite).where(HostSite.id == host_site_id))
    return result.scalar_one_or_none()


async def get_host_site_by_host(
    db: AsyncSession,
    host: str,
) -> HostSite | None:
    result = await db.execute(select(HostSite).where(HostSite.host == host))
    return result.scalar_one_or_none()


async def list_host_sites(
    db: AsyncSession,
    *,
    active_only: bool = False,
) -> list[HostSite]:
    query = select(HostSite).order_by(HostSite.created_at.desc(), HostSite.id.desc())
    if active_only:
        query = query.where(HostSite.is_active.is_(True))

    result = await db.execute(query)
    return list(result.scalars().all())


async def create_host_site(
    db: AsyncSession,
    *,
    host: str,
    is_active: bool = True,
) -> HostSite:
    host_site = HostSite(host=host, is_active=is_active)
    db.add(host_site)
    await db.commit()
    await db.refresh(host_site)
    return host_site


async def update_host_site(
    db: AsyncSession,
    host_site: HostSite,
    *,
    host: str | None = None,
    is_active: bool | None = None,
) -> HostSite:
    if host is not None:
        host_site.host = host
    if is_active is not None:
        host_site.is_active = is_active

    await db.commit()
    await db.refresh(host_site)
    return host_site


async def delete_host_site(
    db: AsyncSession,
    host_site: HostSite,
) -> None:
    await db.delete(host_site)
    await db.commit()
