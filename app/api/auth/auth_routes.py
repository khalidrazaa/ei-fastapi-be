from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.auth import LoginResponse, OTPRequest, OTPVerifyRequest
from app.services.auth_service import send_otp_service, verify_otp_service
from app.utils.cookies import clear_access_cookie, set_access_cookie

router = APIRouter()


@router.post("/send-otp")
async def send_otp(payload: OTPRequest, db: AsyncSession = Depends(get_db)):
    return await send_otp_service(payload.email, db)


@router.post("/verify-otp", response_model=LoginResponse)
async def verify_otp(
    payload: OTPVerifyRequest, request: Request, response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await verify_otp_service(payload.email, payload.otp, db)

    set_access_cookie(response, result["access_token"], request)

    return {
        "status": True,
        "token_type": "bearer",
        "message": "OTP verified successfully",
    }


@router.post("/logout")
async def logout(response: Response):
    clear_access_cookie(response)
    return {"status": True, "message": "Logged out successfully"}
