from sqlalchemy import Boolean, Column, Float, Integer, String, ForeignKey, DateTime, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.base import Base


class TrendIdea(Base):
    __tablename__ = "trend_ideas"

    id = Column(Integer, primary_key=True, index=True)

    trend_id = Column(
        Integer,
        ForeignKey("discovered_trends.id", ondelete="CASCADE"),
        nullable=False,
    )

    title = Column(String, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    is_selected = Column(Boolean, default=False)

    trend = relationship("DiscoveredTrend", back_populates="ideas")
    idea_score = Column(Float, default=0)

    __table_args__ = (
        UniqueConstraint("trend_id", "title", name="uq_trend_idea"),
    )