from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_security import require_admin
from app.db.session import get_db
from app.schemas.admin_user import AdminUserCreate
from app.services.admin_service import create_admin_service

router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("/create", status_code=201)
async def create_admin(payload: AdminUserCreate, db: AsyncSession = Depends(get_db)):
    admin = await create_admin_service(payload, db)
    print("admin", admin)
    return {"message": "Admin created successfully", "admin_id": admin.id}
