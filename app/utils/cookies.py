from fastapi import Response

ACCESS_TOKEN_NAME = "access_token"


def set_access_cookie(response: Response, token: str):
    response.set_cookie(
        key=ACCESS_TOKEN_NAME,
        value=token,
        httponly=True,
        secure=True,  # ✅ enable HTTPS only in prod
        samesite="lax",
        max_age=60 * 60 * 24,  # 1 day
    )


def clear_access_cookie(response: Response):
    response.delete_cookie(ACCESS_TOKEN_NAME)
