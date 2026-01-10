from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException

from app.db.models.admin_user import AdminUser
from app.schemas.admin_user import AdminUserCreate
from app.services.auth_service import send_otp_service

import datetime


async def create_admin_service(payload: AdminUserCreate, db: AsyncSession):
    result = await db.execute(select(AdminUser).where(AdminUser.email == payload.email))
    existing_admin = result.scalar_one_or_none()

    if existing_admin:
        raise HTTPException(status_code=400, detail="Admin already exists")

    admin = AdminUser(
        email=payload.email,
        phone=payload.phone,
        full_name=payload.full_name,
        gender=payload.gender,
        dob=payload.dob,
    )

    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    otp = await send_otp_service(admin.email, db)
    if otp["status"] == False:
        raise HTTPException(status_code=400, detail=otp["message"])

    return {admin: admin, "status": True, "message": "Admin created successfully"}
