"""add trend score components

Revision ID: e7a9b7e9c41f
Revises: d9d1c82f4a6e
Create Date: 2026-04-20 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7a9b7e9c41f"
down_revision: Union[str, Sequence[str], None] = "d9d1c82f4a6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trend_videos", sa.Column("speed_score", sa.Float(), nullable=True))
    op.add_column("trend_videos", sa.Column("breakout_score", sa.Float(), nullable=True))
    op.add_column("trend_videos", sa.Column("engagement_score", sa.Float(), nullable=True))
    op.add_column("trend_videos", sa.Column("freshness_score", sa.Float(), nullable=True))
    op.add_column("trend_videos", sa.Column("confidence_score", sa.Float(), nullable=True))
    op.add_column("trend_videos", sa.Column("trend_stage", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("trend_videos", "trend_stage")
    op.drop_column("trend_videos", "confidence_score")
    op.drop_column("trend_videos", "freshness_score")
    op.drop_column("trend_videos", "engagement_score")
    op.drop_column("trend_videos", "breakout_score")
    op.drop_column("trend_videos", "speed_score")
