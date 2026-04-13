"""add category title to trend videos

Revision ID: ab12c7f4d8a1
Revises: 629d9bebfda8
Create Date: 2026-04-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ab12c7f4d8a1"
down_revision: Union[str, Sequence[str], None] = "629d9bebfda8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trend_videos",
        sa.Column("category_title", sa.String(), nullable=True),
    )
    op.execute(
        "UPDATE trend_videos SET category_title = 'Unknown' WHERE category_title IS NULL"
    )
    op.alter_column(
        "trend_videos",
        "category_title",
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("trend_videos", "category_title")
