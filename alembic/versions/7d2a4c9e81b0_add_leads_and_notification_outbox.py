"""Add consulting leads and their transactional notification outbox.

Revision ID: 7d2a4c9e81b0
Revises: 1f4366203f2d
"""

import sqlalchemy as sa

from alembic import op

revision = "7d2a4c9e81b0"
down_revision = "1f4366203f2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("phone", sa.String(16), nullable=True),
        sa.Column("subject", sa.String(200), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("host_site", sa.String(120), nullable=False),
        sa.Column("landing_page", sa.String(2048), nullable=True),
        sa.Column("referrer", sa.String(2048), nullable=True),
        sa.Column("utm_source", sa.String(200), nullable=True),
        sa.Column("utm_medium", sa.String(200), nullable=True),
        sa.Column("utm_campaign", sa.String(200), nullable=True),
        sa.Column("utm_term", sa.String(200), nullable=True),
        sa.Column("utm_content", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), server_default="new", nullable=False),
        sa.Column("internal_notes", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('new','contacted','qualified','proposal','won','lost','spam')",
            name="ck_leads_status",
        ),
    )
    op.create_index("ix_leads_submitted_at", "leads", ["submitted_at"])
    op.create_index("ix_leads_utm_source", "leads", ["utm_source"])
    op.create_index("ix_leads_status_submitted_at", "leads", ["status", "submitted_at"])
    op.create_index("ix_leads_email_submitted_at", "leads", ["email", "submitted_at"])
    op.create_table(
        "lead_notification_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("state", sa.String(20), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("last_error", sa.String(80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "state IN ('pending','processing','sent','failed')",
            name="ck_lead_notification_state",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_lead_notification_attempts"),
    )
    op.create_index(
        "ix_lead_notification_ready",
        "lead_notification_outbox",
        ["state", "available_at"],
    )
    op.create_index(
        "ix_lead_notification_lease",
        "lead_notification_outbox",
        ["state", "lease_until"],
    )


def downgrade() -> None:
    op.drop_table("lead_notification_outbox")
    op.drop_table("leads")
