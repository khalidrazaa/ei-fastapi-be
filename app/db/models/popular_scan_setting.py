from sqlalchemy import Column, DateTime, Integer, JSON, String, func

from app.db.base import Base


class PopularScanSetting(Base):
    __tablename__ = "popular_scan_settings"

    key = Column(String, primary_key=True, default="default")
    region_codes = Column(JSON, nullable=False, default=list)
    max_results = Column(Integer, nullable=False, default=10)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
