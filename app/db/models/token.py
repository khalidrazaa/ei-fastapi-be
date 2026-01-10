from sqlalchemy import Column, Integer, String, DateTime
from app.db.session import Base
from datetime import datetime


class Token(Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True, index=True)
    access_token = Column(String, nullable=False)
    token_type = Column(String, default="bearer")
    expires_at = Column(DateTime, default=None)
    created_at = Column(DateTime, default=datetime.utcnow)
