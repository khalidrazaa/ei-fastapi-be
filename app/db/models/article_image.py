"""Durable media and import receipts, including media retained for static pages."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.db.base import Base


class ArticleImage(Base):
    __tablename__ = "article_images"

    id = Column(String(36), primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), index=True)
    # Retained when an article is deleted: already deployed static pages still use it.
    original_article_id = Column(Integer, nullable=False, index=True)
    storage_name = Column(String(40), nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(40), nullable=False)
    byte_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ArticleImport(Base):
    __tablename__ = "article_imports"

    request_id = Column(String(36), primary_key=True)
    admin_id = Column(String, nullable=False)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), index=True)
    # Distinguish create retries from updates, even after the article is deleted.
    target_article_id = Column(Integer)
    payload_sha256 = Column(String(64), nullable=False)
    response = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
