"""Add reusable editorial research preferences; no defaults are inserted."""

import sqlalchemy as sa
from alembic import op

revision = "c02_research_settings"
down_revision = "c01_content_workflow"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "content_research_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("source_groups", sa.JSON(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_content_research_settings_singleton"),
        sa.CheckConstraint("version >= 1", name="ck_content_research_settings_version"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("content_research_settings")
