from sqlalchemy import Column, String, DateTime, func
from app.db.session import Base
from datetime import datetime, timedelta


class EmailOTP(Base):
    __tablename__ = "email_otps"

    email = Column(String, primary_key=True, index=True)
    otp = Column(String, nullable=False)
    expires_at = Column(
        DateTime, default=lambda: datetime.utcnow() + timedelta(minutes=5)
    )
    created_at = Column(DateTime, server_default=func.now())
