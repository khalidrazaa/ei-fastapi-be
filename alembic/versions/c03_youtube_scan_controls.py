"""Add persistent YouTube scan controls; preserve existing enabled behavior."""

import sqlalchemy as sa
from alembic import op

revision = "c03_youtube_scan_controls"
down_revision = "c02_research_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        "youtube_scan_enabled", "popular_scan_enabled", "niche_scan_enabled"
    ):
        op.add_column(
            "popular_scan_settings",
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    for column in (
        "niche_scan_enabled", "popular_scan_enabled", "youtube_scan_enabled"
    ):
        op.drop_column("popular_scan_settings", column)
