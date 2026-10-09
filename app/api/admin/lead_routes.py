from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_security import require_admin
from app.db.session import get_db
from app.schemas.lead import LeadPage, LeadResponse, LeadStatus, LeadUpdate
from app.services import lead_service

router = APIRouter(dependencies=[Depends(require_admin)])


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def persistence_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The lead service is temporarily unavailable.",
        headers={"Cache-Control": "no-store"},
    )


@router.get("", response_model=LeadPage)
async def list_leads_route(
    response: Response,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    status: LeadStatus | None = None,
    source: str | None = Query(default=None, max_length=200),
    db: AsyncSession = Depends(get_db),
):
    private_response(response)
    try:
        return await lead_service.list_leads(
            db, page=page, size=size, search=search, status=status, source=source,
        )
    except lead_service.LeadPersistenceError:
        raise persistence_error() from None


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead_route(
    response: Response,
    lead_id: int = Path(ge=1),
    db: AsyncSession = Depends(get_db),
):
    private_response(response)
    try:
        return await lead_service.get_lead(db, lead_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except lead_service.LeadPersistenceError:
        raise persistence_error() from None


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead_route(
    payload: LeadUpdate,
    response: Response,
    lead_id: int = Path(ge=1),
    db: AsyncSession = Depends(get_db),
):
    private_response(response)
    try:
        return await lead_service.update_lead(db, lead_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except lead_service.LeadPersistenceError:
        raise persistence_error() from None
