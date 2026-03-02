from sqlalchemy import Column, String, Date, Boolean
import uuid

from app.db.base import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    phone = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    gender = Column(String, nullable=False)
    dob = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True)
