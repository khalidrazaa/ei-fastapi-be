from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)

from app.db.base import Base


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new','contacted','qualified','proposal','won','lost','spam')",
            name="ck_leads_status",
        ),
        Index("ix_leads_status_submitted_at", "status", "submitted_at"),
        Index("ix_leads_email_submitted_at", "email", "submitted_at"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    email = Column(String(254), nullable=False)
    phone = Column(String(16), nullable=True)
    subject = Column(String(200), nullable=True)
    message = Column(Text, nullable=False)
    host_site = Column(String(120), nullable=False)
    landing_page = Column(String(2048), nullable=True)
    referrer = Column(String(2048), nullable=True)
    utm_source = Column(String(200), nullable=True, index=True)
    utm_medium = Column(String(200), nullable=True)
    utm_campaign = Column(String(200), nullable=True)
    utm_term = Column(String(200), nullable=True)
    utm_content = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, server_default="new")
    internal_notes = Column(Text, nullable=False, server_default="")
    submitted_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
