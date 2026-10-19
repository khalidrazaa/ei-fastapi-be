from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, func, true

from app.db.base import Base


class PopularScanSetting(Base):
    __tablename__ = "popular_scan_settings"

    key = Column(String, primary_key=True, default="default")
    region_codes = Column(JSON, nullable=False, default=list)
    available_regions = Column(JSON, nullable=False, default=list)
    max_results = Column(Integer, nullable=False, default=10)
    youtube_scan_enabled = Column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    popular_scan_enabled = Column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    niche_scan_enabled = Column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
