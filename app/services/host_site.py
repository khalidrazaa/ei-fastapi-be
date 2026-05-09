from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query import host_site as host_site_query


DEFAULT_HOST_SITE = "explainit.tech"


def _normalize_host(value: str) -> str:
    normalized = str(value or "").strip().lower()

    if normalized.startswith("http://"):
        normalized = normalized[7:]
    elif normalized.startswith("https://"):
        normalized = normalized[8:]

    normalized = normalized.split("/", 1)[0].strip().strip(".")
    if not normalized:
        raise ValueError("Host site is required.")

    if " " in normalized:
        raise ValueError("Host site cannot contain spaces.")

    return normalized


async def _ensure_default_host_site(db: AsyncSession) -> None:
    existing = await host_site_query.get_host_site_by_host(db, DEFAULT_HOST_SITE)
    if existing is None:
        await host_site_query.create_host_site(
            db,
            host=DEFAULT_HOST_SITE,
            is_active=True,
        )


async def get_host_sites(
    db: AsyncSession,
    *,
    active_only: bool = False,
) -> object:
    await _ensure_default_host_site(db)
    return await host_site_query.list_host_sites(db, active_only=active_only)


async def create_host_site(
    db: AsyncSession,
    *,
    host: str,
    is_active: bool = True,
) -> object:
    normalized_host = _normalize_host(host)
    existing = await host_site_query.get_host_site_by_host(db, normalized_host)
    if existing is not None:
        raise ValueError("Host site already exists.")

    return await host_site_query.create_host_site(
        db,
        host=normalized_host,
        is_active=is_active,
    )


async def update_host_site(
    db: AsyncSession,
    host_site_id: int,
    *,
    host: str | None = None,
    is_active: bool | None = None,
) -> object:
    host_site = await host_site_query.get_host_site_by_id(db, host_site_id)
    if host_site is None:
        raise LookupError("Host site not found.")

    normalized_host: str | None = None
    if host is not None:
        normalized_host = _normalize_host(host)
        existing = await host_site_query.get_host_site_by_host(db, normalized_host)
        if existing is not None and existing.id != host_site.id:
            raise ValueError("Host site already exists.")

    if is_active is False and host_site.is_active:
        active_sites = await host_site_query.list_host_sites(db, active_only=True)
        if len(active_sites) <= 1:
            raise ValueError("At least one active host site must remain.")

    return await host_site_query.update_host_site(
        db,
        host_site,
        host=normalized_host,
        is_active=is_active,
    )


async def delete_host_site(
    db: AsyncSession,
    host_site_id: int,
) -> None:
    host_site = await host_site_query.get_host_site_by_id(db, host_site_id)
    if host_site is None:
        raise LookupError("Host site not found.")

    all_sites = await host_site_query.list_host_sites(db, active_only=False)
    if len(all_sites) <= 1:
        raise ValueError("At least one host site must remain.")

    if host_site.is_active:
        active_sites = await host_site_query.list_host_sites(db, active_only=True)
        if len(active_sites) <= 1:
            raise ValueError("At least one active host site must remain.")

    await host_site_query.delete_host_site(db, host_site)
