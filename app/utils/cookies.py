from fastapi import Request, Response

from app.core import security

ACCESS_TOKEN_NAME = "access_token"


def set_access_cookie(response: Response, token: str, request: Request):
    local_http = (
        request.url.scheme == "http"
        and request.url.hostname in {"localhost", "127.0.0.1", "::1"}
    )
    response.set_cookie(
        key=ACCESS_TOKEN_NAME,
        value=token,
        httponly=True,
        secure=not local_http,
        samesite="lax",
        max_age=security.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def clear_access_cookie(response: Response):
    response.delete_cookie(ACCESS_TOKEN_NAME)
