# app/db/models/trend_video.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    Float,
    func,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.db.base import Base


class TrendVideo(Base):
    __tablename__ = "trend_videos"

    id = Column(Integer, primary_key=True, index=True)

    # 🔥 Now linked to keyword (not niche)
    keyword_id = Column(
        Integer,
        ForeignKey("niche_keywords.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    youtube_video_id = Column(String, nullable=False, index=True)

    title = Column(String, nullable=False)
    channel_title = Column(String, nullable=False)

    view_count = Column(Integer, nullable=False)
    like_count = Column(Integer, nullable=True)
    comment_count = Column(Integer, nullable=True)

    published_at = Column(DateTime(timezone=True), nullable=False)

    virality_score = Column(Float, nullable=False)

    thumbnail_url = Column(String, nullable=False)

    scanned_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    source = Column(String, nullable=False, default="youtube")
    
    # Relationship to keyword
    keyword = relationship("NicheKeyword")

    __table_args__ = (
        UniqueConstraint(
            "keyword_id",
            "youtube_video_id",
            name="uq_keyword_video",
        ),
    )