# app/db/models/trend_video.py

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class TrendVideo(Base):
    __tablename__ = "trend_videos"

    id = Column(Integer, primary_key=True, index=True)

    keyword_id = Column(
        Integer,
        ForeignKey("niche_keywords.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    youtube_video_id = Column(String, nullable=False, index=True)
    youtube_channel_id = Column(String, nullable=True, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    channel_title = Column(String, nullable=False)
    channel_custom_url = Column(String, nullable=True)
    channel_description = Column(Text, nullable=True)
    channel_country = Column(String, nullable=True)

    view_count = Column(BigInteger, nullable=False)
    like_count = Column(BigInteger, nullable=True)
    comment_count = Column(BigInteger, nullable=True)
    subscriber_count = Column(BigInteger, nullable=True)
    channel_view_count = Column(BigInteger, nullable=True)
    channel_video_count = Column(BigInteger, nullable=True)
    hidden_subscriber_count = Column(Boolean, nullable=True)

    published_at = Column(DateTime(timezone=True), nullable=False)
    channel_published_at = Column(DateTime(timezone=True), nullable=True)

    virality_score = Column(Float, nullable=False)
    speed_score = Column(Float, nullable=True)
    breakout_score = Column(Float, nullable=True)
    engagement_score = Column(Float, nullable=True)
    freshness_score = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    trend_stage = Column(String, nullable=True)

    thumbnail_url = Column(String, nullable=False)
    channel_thumbnail_url = Column(String, nullable=True)
    category_id = Column(String, nullable=True)
    category_title = Column(String, nullable=False, default="Unknown")
    video_payload = Column(JSON, nullable=True)
    channel_payload = Column(JSON, nullable=True)

    scanned_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    source = Column(String, nullable=False, default="NICHE")
    region_code = Column(String, nullable=True)

    keyword = relationship("NicheKeyword")

    __table_args__ = (
        UniqueConstraint(
            "keyword_id",
            "youtube_video_id",
            name="uq_trend_keyword_video",
        ),
        UniqueConstraint(
            "region_code",
            "youtube_video_id",
            name="uq_trend_region_video",
        ),
    )
