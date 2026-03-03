from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.base import Base


class Niche(Base):
    __tablename__ = "niches"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=False)

    # Intelligence Configuration
    region_code = Column(String(5), nullable=False, default="US")

    scan_mode = Column(String, nullable=False, default="most_popular")
    # values:
    # "most_popular"
    # "keyword"
    # "hybrid"

    is_active = Column(Boolean, default=True, nullable=False)

    last_scanned_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    keywords = relationship(
        "NicheKeyword",
        back_populates="niche",
        cascade="all, delete-orphan"
    )



class NicheKeyword(Base):
    __tablename__ = "niche_keywords"

    id = Column(Integer, primary_key=True, index=True)

    niche_id = Column(
        Integer,
        ForeignKey("niches.id", ondelete="CASCADE"),
        nullable=False
    )

    keyword = Column(String, nullable=False)

    # Intelligence control
    is_active = Column(Boolean, default=True, nullable=False)

    # Tracking scans
    last_scanned_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    niche = relationship("Niche", back_populates="keywords")

    __table_args__ = (
        UniqueConstraint("niche_id", "keyword", name="uq_niche_keyword"),
    )