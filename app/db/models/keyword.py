from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from app.db.session import Base


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, unique=True, index=True, nullable=False)

    source = Column(String, nullable=True)  # e.g., google, youtube, reddit
    monthly_searches = Column(Integer, nullable=True)
    cpc = Column(Float, nullable=True)  # Cost per click
    seo_difficulty = Column(Float, nullable=True)

    # Suggestions per source
    google_trend = Column(JSON, default=[])  # from CSV "Trends" + breakdown
    google_autocomplete = Column(JSON, default=[])  # serpapi autocomplete
    google_search = Column(JSON, default=[])  # serpapi related searches
    google_news = Column(JSON, default=[])  # serpapi news
    youtube = Column(JSON, default=[])  # serpapi youtube

    # Volume + trend info
    volume = Column(String, nullable=True)  # e.g. "200K+" (keep string from CSV)
    trend_started = Column(String, nullable=True)  # keep datetime string for now
    trend_ended = Column(String, nullable=True)

    processed = Column(
        Boolean, default=False
    )  # whether an article has been generated for this keyword
    article_id = Column(Integer, nullable=True)  # link to Article table if processed

    # Extra
    web_domain = Column(String, nullable=True)
    geo = Column(String, nullable=False)  # "US" or "IN"

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
