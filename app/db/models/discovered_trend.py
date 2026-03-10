from sqlalchemy import Column, Index, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class DiscoveredTrend(Base):
    __tablename__ = "discovered_trends"

    id = Column(Integer, primary_key=True)

    phrase = Column(String, unique=True, nullable=False)

    score = Column(Float, nullable=False)

    burst_score = Column(Float, nullable=True)

    video_count = Column(Integer)

    last_seen = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_trend_score", "score"),
        Index("idx_trend_burst", "burst_score"),
    )