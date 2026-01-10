from sqlalchemy import Column, Integer, String, Text, DateTime, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ARRAY
from app.db.session import Base


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)

    # Main identifiers
    title = Column(String, nullable=False)
    seo_title = Column(String, nullable=True)
    slug = Column(String, unique=True, index=True, nullable=False)

    # Classification
    category = Column(String, nullable=True)
    subcategory = Column(String, nullable=True)
    tags = Column(ARRAY(String), nullable=True)

    # Status + timeline
    status = Column(String, default="draft")  # draft | published
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)

    # Author relationship (optional foreign key if you have users table)
    author_id = Column(Integer, nullable=True)

    # Content
    content = Column(Text, nullable=True)  # HTML / Markdown
    excerpt = Column(Text, nullable=True)
    reading_time = Column(Integer, nullable=True)

    # SEO & Meta
    keywords = Column(ARRAY(String), nullable=True)
    featured_image_url = Column(String, nullable=True)
    image_alt_text = Column(String, nullable=True)
    language = Column(String, default="en")
    canonical_url = Column(String, nullable=True)

    # Open Graph metadata
    open_graph_title = Column(String, nullable=True)
    open_graph_description = Column(String, nullable=True)
    open_graph_image = Column(String, nullable=True)
