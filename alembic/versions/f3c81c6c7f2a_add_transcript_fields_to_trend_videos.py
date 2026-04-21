"""add transcript fields to trend videos

Revision ID: f3c81c6c7f2a
Revises: e7a9b7e9c41f
Create Date: 2026-04-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3c81c6c7f2a"
down_revision: Union[str, Sequence[str], None] = "e7a9b7e9c41f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trend_videos", sa.Column("transcript_text", sa.Text(), nullable=True))
    op.add_column("trend_videos", sa.Column("transcript_language_code", sa.String(), nullable=True))
    op.add_column("trend_videos", sa.Column("transcript_language", sa.String(), nullable=True))
    op.add_column("trend_videos", sa.Column("transcript_source", sa.String(), nullable=True))
    op.add_column("trend_videos", sa.Column("transcript_error", sa.Text(), nullable=True))
    op.add_column("trend_videos", sa.Column("transcript_fetched_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("trend_videos", "transcript_fetched_at")
    op.drop_column("trend_videos", "transcript_error")
    op.drop_column("trend_videos", "transcript_source")
    op.drop_column("trend_videos", "transcript_language")
    op.drop_column("trend_videos", "transcript_language_code")
    op.drop_column("trend_videos", "transcript_text")
