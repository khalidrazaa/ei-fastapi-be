"""Authentication dependency for protected admin routes."""

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin_user import AdminUser
from app.db.session import get_db
from app.services.admin_auth_service import authenticate_admin
from app.utils.cookies import ACCESS_TOKEN_NAME


async def require_admin(
    request: Request, db: AsyncSession = Depends(get_db)
) -> AdminUser:
    authorization = request.headers.get("authorization")
    cookie_authenticated = authorization is None
    if authorization is not None:
        scheme, separator, value = authorization.partition(" ")
        token = (
            value.strip()
            if separator and scheme.lower() == "bearer"
            else None
        )
    else:
        token = request.cookies.get(ACCESS_TOKEN_NAME)

    return await authenticate_admin(
        db,
        token,
        cookie_authenticated=cookie_authenticated,
        method=request.method,
        origin=request.headers.get("origin"),
        request_origin=str(request.base_url),
    )
