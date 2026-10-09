"""Validate the existing OTP access token before exposing private admin data."""

from urllib.parse import urlsplit

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.db.models.admin_user import AdminUser
from app.db.query.admin_user import get_admin_user_by_email

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _normalize_origin(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            return None
        host = parsed.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        port = parsed.port
        default_port = 443 if parsed.scheme == "https" else 80
        suffix = f":{port}" if port is not None and port != default_port else ""
        return f"{parsed.scheme}://{host}{suffix}"
    except ValueError:
        return None


def _validate_cookie_origin(origin: str | None, request_origin: str) -> None:
    normalized = _normalize_origin(origin)
    allowed = {
        item
        for value in settings.CORS_ORIGINS.split(",")
        if (item := _normalize_origin(value)) is not None
    }
    same_origin = _normalize_origin(request_origin)
    if same_origin:
        allowed.add(same_origin)
    if normalized is None or normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )


async def authenticate_admin(
    db: AsyncSession,
    access_token: str | None,
    *,
    cookie_authenticated: bool,
    method: str,
    origin: str | None,
    request_origin: str,
) -> AdminUser:
    if not access_token:
        raise _unauthorized()
    try:
        claims = jwt.decode(
            access_token,
            security.SECRET_KEY,
            algorithms=[security.ALGORITHM],
            options={"require_exp": True, "require_sub": True},
        )
    except (JWTError, TypeError, ValueError) as exc:
        raise _unauthorized() from exc

    email = claims.get("sub")
    if not isinstance(email, str) or not email.strip():
        raise _unauthorized()
    if cookie_authenticated and method.upper() not in _SAFE_METHODS:
        _validate_cookie_origin(origin, request_origin)

    try:
        admin = await get_admin_user_by_email(db, email)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is temporarily unavailable.",
            headers={"Cache-Control": "no-store"},
        ) from None
    if admin is None or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return admin
