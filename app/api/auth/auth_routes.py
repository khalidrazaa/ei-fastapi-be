from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.auth import OTPRequest, OTPVerifyRequest, LoginResponse
from app.services.auth_service import send_otp_service, verify_otp_service
from app.utils.cookies import clear_access_cookie

router = APIRouter()


@router.post("/send-otp")
async def send_otp(payload: OTPRequest, db: AsyncSession = Depends(get_db)):
    print(f"Attempting to send OTP to {payload.email}")
    return await send_otp_service(payload.email, db)


@router.post("/verify-otp", response_model=LoginResponse)
async def verify_otp(
    payload: OTPVerifyRequest, response: Response, db: AsyncSession = Depends(get_db)
):
    print(f"Attempting to verify OTP for {payload.email}")
    result = await verify_otp_service(payload.email, payload.otp, db)

    response.set_cookie(
        key="access_token",
        value=result["access_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24,
    )

    return {
        "status": True,
        "token_type": "bearer",
        "message": "OTP verified successfully",
    }


@router.post("/logout")
async def logout(response: Response):
    clear_access_cookie(response)
    return {"status": True, "message": "Logged out successfully"}
