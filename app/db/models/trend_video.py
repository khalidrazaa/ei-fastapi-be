from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, func
from sqlalchemy.orm import relationship
from app.db.base import Base


class TrendVideo(Base):
    __tablename__ = "trend_videos"

    id = Column(Integer, primary_key=True, index=True)

    niche_id = Column(
        Integer,
        ForeignKey("niches.id", ondelete="CASCADE"),
        nullable=False
    )

    youtube_video_id = Column(String, index=True, nullable=False)

    title = Column(String, nullable=False)
    channel_title = Column(String, nullable=False)

    view_count = Column(Integer, nullable=False)
    like_count = Column(Integer, nullable=True)
    comment_count = Column(Integer, nullable=True)

    published_at = Column(DateTime(timezone=True), nullable=False)

    virality_score = Column(Float, nullable=False)

    scanned_at = Column(DateTime(timezone=True), server_default=func.now())

    niche = relationship("Niche")