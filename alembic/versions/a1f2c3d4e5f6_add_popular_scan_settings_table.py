"""add popular scan settings table

Revision ID: a1f2c3d4e5f6
Revises: f3c81c6c7f2a
Create Date: 2026-04-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1f2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f3c81c6c7f2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "popular_scan_settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("region_codes", sa.JSON(), nullable=False),
        sa.Column("max_results", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
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
        sa.PrimaryKeyConstraint("key"),
    )

    settings_table = sa.table(
        "popular_scan_settings",
        sa.column("key", sa.String()),
        sa.column("region_codes", sa.JSON()),
        sa.column("max_results", sa.Integer()),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "key": "default",
                "region_codes": ["US"],
                "max_results": 10,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("popular_scan_settings")
