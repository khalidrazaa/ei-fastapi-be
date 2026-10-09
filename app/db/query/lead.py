from contextlib import asynccontextmanager
from datetime import timedelta

from sqlalchemy import DateTime, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.lead import Lead
from app.db.pagination import paginate_query

# One short transaction lock preserves the existing global 20/minute contact cap
# across API processes. No provider I/O occurs while holding this lock.
CONTACT_LOCK_ID = 739102841


@asynccontextmanager
async def submission_transaction(db: AsyncSession):
    try:
        yield
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def get_submission_window(db: AsyncSession, email: str, window_seconds: int):
    await db.execute(select(func.pg_advisory_xact_lock(CONTACT_LOCK_ID)))
    now = (
        await db.execute(select(func.clock_timestamp(type_=DateTime(timezone=True))))
    ).scalar_one()
    cutoff = now - timedelta(seconds=window_seconds)
    recent = Lead.submitted_at > cutoff
    result = await db.execute(
        select(func.count(Lead.id), func.min(Lead.submitted_at)).where(recent)
    )
    count, oldest = result.one()
    previous = (
        await db.execute(
            select(func.max(Lead.submitted_at)).where(
                recent, func.lower(Lead.email) == func.lower(email)
            )
        )
    ).scalar_one()
    return now, count, oldest, previous


async def add_lead(db: AsyncSession, values: dict) -> Lead:
    lead = Lead(**values)
    db.add(lead)
    await db.flush()
    return lead


async def list_leads(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    search: str | None = None,
    status: str | None = None,
    source: str | None = None,
):
    query = select(Lead)
    if status:
        query = query.where(Lead.status == status)
    if source:
        query = query.where(Lead.utm_source == source)
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(
            or_(
                *(
                    column.ilike(pattern, escape="\\")
                    for column in (
                        Lead.name,
                        Lead.email,
                        Lead.phone,
                        Lead.subject,
                        Lead.message,
                    )
                )
            )
        )
    query = query.order_by(Lead.submitted_at.desc(), Lead.id.desc())
    return await paginate_query(db, query, page, size)


async def get_lead(db: AsyncSession, lead_id: int) -> Lead | None:
    return (
        await db.execute(select(Lead).where(Lead.id == lead_id))
    ).scalar_one_or_none()


async def update_lead(db: AsyncSession, lead: Lead, changes: dict) -> Lead:
    for field, value in changes.items():
        setattr(lead, field, value)
    await db.commit()
    await db.refresh(lead)
    return lead
