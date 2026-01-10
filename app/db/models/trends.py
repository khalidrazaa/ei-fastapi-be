from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Enum,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base, relationship

from app.db.session import Base


class TrendStatus(str, enum.Enum):
    Open = "Open"
    Processed = "Processed"
    Ignored = "Ignored"


class TrendItem(Base):
    """
    One trend keyword/topic (like 'ChatGPT', 'Cricket World Cup', etc.)
    """

    __tablename__ = "trend_items"

    id = Column(Integer, primary_key=True, index=True)
    trend = Column(String(255), unique=True, nullable=False)
    search_volume = Column(Integer, default=0)

    started = Column(DateTime(timezone=True))
    ended = Column(DateTime(timezone=True))

    trend_breakdown = Column(Text)
    explore_link = Column(Text)

    is_growing = Column(Boolean, default=False)
    category = Column(String(100))
    subcategory = Column(String(100))

    status = Column(Enum(TrendStatus), default=TrendStatus.Open)
    draft_id = Column(String(255))

    last_updated = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationship → one TrendItem has many VolumePoints
    volume_history = relationship(
        "VolumePoint",
        back_populates="trend_item",
        cascade="all, delete-orphan",
        lazy="selectin",  # Efficient async loading
    )


class VolumePoint(Base):
    """
    Individual (timestamp, value) record for trend's search volume.
    """

    __tablename__ = "volume_points"

    id = Column(Integer, primary_key=True, index=True)
    trend_id = Column(
        Integer, ForeignKey("trend_items.id", ondelete="CASCADE"), nullable=False
    )
    ts = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    value = Column(Integer, nullable=False)

    trend_item = relationship("TrendItem", back_populates="volume_history")

    __table_args__ = (UniqueConstraint("trend_id", "ts", name="uq_trend_volume_ts"),)
