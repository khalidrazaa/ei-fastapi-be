from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query import lead as lead_query
from app.schemas.lead import LeadStatus, LeadUpdate


class LeadPersistenceError(Exception):
    pass


async def list_leads(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    search: str | None = None,
    status: LeadStatus | None = None,
    source: str | None = None,
):
    try:
        return await lead_query.list_leads(
            db,
            page=page,
            size=size,
            search=search.strip() if search else None,
            status=status.value if status else None,
            source=source.strip() if source else None,
        )
    except SQLAlchemyError:
        raise LeadPersistenceError() from None


async def get_lead(db: AsyncSession, lead_id: int):
    try:
        lead = await lead_query.get_lead(db, lead_id)
    except SQLAlchemyError:
        raise LeadPersistenceError() from None
    if lead is None:
        raise LookupError("Lead not found.")
    return lead


async def update_lead(db: AsyncSession, lead_id: int, payload: LeadUpdate):
    lead = await get_lead(db, lead_id)
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes:
        changes["status"] = changes["status"].value
    try:
        return await lead_query.update_lead(db, lead, changes)
    except SQLAlchemyError:
        raise LeadPersistenceError() from None
