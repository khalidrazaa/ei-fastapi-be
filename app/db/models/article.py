from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
)
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ARRAY
from app.db.session import Base


class Article(Base):
    __tablename__ = "articles"

    # Primary
    id = Column(Integer, primary_key=True, index=True)

    # Core Identity
    title = Column(String, nullable=False)
    seo_title = Column(String, nullable=True)
    slug = Column(String, unique=True, index=True, nullable=False)

    # Content
    content = Column(Text, nullable=True)  # Markdown
    excerpt = Column(Text, nullable=True)
    reading_time = Column(Integer, nullable=True)

    # Classification
    category = Column(String, nullable=True)
    subcategory = Column(String, nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    host_site = Column(String, nullable=False)

    # Publishing Status
    status = Column(String, default="draft")  # draft | published
    is_featured = Column(Boolean, default=False)
    language = Column(String, default="en")

    drafted_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    # SEO Meta
    meta_description = Column(String, nullable=True)
    keywords = Column(ARRAY(String), nullable=True)
    canonical_url = Column(String, nullable=True)
    schema_type = Column(String, default="Article")

    # Open Graph
    open_graph_title = Column(String, nullable=True)
    open_graph_description = Column(String, nullable=True)
    open_graph_image = Column(String, nullable=True)

    # Media
    featured_image_url = Column(String, nullable=True)
    image_alt_text = Column(String, nullable=True)

    # Metrics
    view_count = Column(Integer, default=0)

    # Author (optional)
    author_id = Column(Integer, nullable=True)

    # System Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())