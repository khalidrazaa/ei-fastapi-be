from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Niche(Base):
    __tablename__ = "niches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)  # slug: "tech_ai"
    display_name = Column(String, nullable=False)                 # UI label: "Tech & AI"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to keywords
    keywords = relationship("NicheKeyword", back_populates="niche", cascade="all, delete-orphan")


class NicheKeyword(Base):
    __tablename__ = "niche_keywords"

    id = Column(Integer, primary_key=True, index=True)
    niche_id = Column(Integer, ForeignKey("niches.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String, nullable=False)  # e.g., "Nvidia Blackwell"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Reference back to the niche
    niche = relationship("Niche", back_populates="keywords")