"""Remove the obsolete contact notification outbox; preserve all leads.

Revision ID: b6f3e94d2a10
Revises: 7d2a4c9e81b0
"""

import sqlalchemy as sa

from alembic import op

revision = "b6f3e94d2a10"
down_revision = "7d2a4c9e81b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("lead_notification_outbox")


def downgrade() -> None:
    # Restore the previous schema, not the deleted notification records.
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
