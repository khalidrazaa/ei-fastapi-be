"""Inventory and durable editorial workspace. Public articles stay separate."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text
from app.db.base import Base

def now():
    return datetime.now(timezone.utc)

class ContentResearchSettings(Base):
    __tablename__ = 'content_research_settings'
    id = Column(Integer, primary_key=True, autoincrement=False)
    version = Column(Integer, nullable=False, default=1)
    instructions = Column(Text, nullable=False)
    source_groups = Column(JSON, nullable=False)
    __table_args__ = (
        CheckConstraint('id = 1', name='ck_content_research_settings_singleton'),
        CheckConstraint('version >= 1', name='ck_content_research_settings_version'),
    )

class TopicIdentifier(Base):
    __tablename__ = 'content_topic_identifiers'
    id = Column(Integer, primary_key=True, autoincrement=True)
    # This registry is never deleted, so imported/deleted IDs cannot be reused.

class ContentTopic(Base):
    __tablename__ = 'content_topics'
    topic_id = Column(String(40), primary_key=True)
    title = Column(String(300), nullable=False)
    reader_question = Column(Text, nullable=False)
    track = Column(String(120), nullable=False)
    priority = Column(Integer, nullable=False, default=0)
    notes = Column(Text, nullable=False, default='')
    status = Column(String(40), nullable=False, default='Idea')
    archived = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)
    brief = Column(JSON, nullable=False, default=dict)
    brief_version = Column(Integer, nullable=False, default=0)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='SET NULL'), unique=True)
    saved_version_id = Column(Integer)
    review_date = Column(String(10))
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)

class ContentRun(Base):
    __tablename__ = 'content_runs'
    id = Column(String(36), primary_key=True)
    topic_id = Column(String(40), ForeignKey('content_topics.topic_id'), nullable=False, index=True)
    stage = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default='queued')
    request_key = Column(String(100), unique=True, nullable=False)
    inputs = Column(JSON, nullable=False)
    result = Column(JSON)
    error = Column(Text)
    attempts = Column(Integer, nullable=False, default=0)
    lease_token = Column(String(36))
    lease_until = Column(DateTime(timezone=True))
    cancel_requested = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
    finished_at = Column(DateTime(timezone=True))
    __table_args__ = (Index('uq_content_active_topic', 'topic_id', unique=True,
        postgresql_where=text("status IN ('queued', 'running')")),)

class ContentVersion(Base):
    __tablename__ = 'content_versions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String(40), ForeignKey('content_topics.topic_id'), nullable=False, index=True)
    run_id = Column(String(36), ForeignKey('content_runs.id'), unique=True)
    research_id = Column(String(36), ForeignKey('content_runs.id'))
    brief_version = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)

class ContentQA(Base):
    __tablename__ = 'content_qa_reports'
    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(Integer, ForeignKey('content_versions.id'), nullable=False, index=True)
    report = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)

class ContentAudit(Base):
    __tablename__ = 'content_audit'
    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String(40), nullable=False, index=True)
    actor = Column(String(100), nullable=False)
    action = Column(String(60), nullable=False)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
