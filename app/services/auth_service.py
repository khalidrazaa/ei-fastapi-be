from datetime import datetime, timedelta
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import NoResultFound
from app.db.models.admin_user import AdminUser
from app.db.models.email_otp import EmailOTP
from app.core.security import create_access_token
from app.utils.email import send_email_otp
from fastapi import HTTPException
import random


def generate_otp() -> str:
    return str(random.randint(100000, 999999))


async def send_otp_service(email: str, db: AsyncSession):

    print(f"Attempting to send OTP to {email}")
    try:
        result = await db.execute(select(AdminUser).where(AdminUser.email == email))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        otp = generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        # Check if OTP already exists
        result = await db.execute(select(EmailOTP).where(EmailOTP.email == email))
        existing = result.scalars().first()

        if existing:
            existing.otp = otp
            existing.expires_at = expires_at
        else:
            new_otp = EmailOTP(email=email, otp=otp, expires_at=expires_at)
            db.add(new_otp)

        try:
            await send_email_otp(email, otp)
        except Exception as e:
            await db.rollback()  # rollback DB changes if sending fails
            print(f"Error sending email: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        await db.commit()
        # await send_email_otp(email, otp)
        return {"status": True, "message": f"OTP sent to {email}"}
    except Exception as e:
        await db.rollback()
        print(f"Error in send_otp_service: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def verify_otp_service(email: str, otp: str, db: AsyncSession):
    result = await db.execute(select(EmailOTP).where(EmailOTP.email == email))
    otp_record = result.scalars().first()

    if not otp_record or otp_record.otp != otp:
        raise HTTPException(status_code=401, detail="Invalid OTP")

    if otp_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="OTP expired")

    # OTP is valid – optionally delete or expire it
    # await db.delete(otp_record)
    await db.commit()

    token = create_access_token(data={"sub": email})
    return {"status": True, "access_token": token, "token_type": "bearer"}
