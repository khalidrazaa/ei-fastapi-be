from pydantic import BaseModel, EmailStr
from datetime import datetime


class OTPStatus(BaseModel):
    email: EmailStr
    expires_at: datetime
