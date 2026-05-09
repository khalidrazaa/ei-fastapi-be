from sqlalchemy import Boolean, Column, DateTime, Integer, String, func

from app.db.base import Base


class HostSite(Base):
    __tablename__ = "host_sites"

    id = Column(Integer, primary_key=True, index=True)
    host = Column(String, nullable=False, unique=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
