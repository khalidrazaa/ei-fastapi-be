"""add host sites table

Revision ID: c2d7a0b1f6e9
Revises: f1a2b3c4d5e6
Create Date: 2026-05-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d7a0b1f6e9"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "host_sites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_host_sites_host"), "host_sites", ["host"], unique=True)
    op.create_index(op.f("ix_host_sites_id"), "host_sites", ["id"], unique=False)

    host_sites_table = sa.table(
        "host_sites",
        sa.column("host", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        host_sites_table,
        [
            {
                "host": "explainit.tech",
                "is_active": True,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_host_sites_id"), table_name="host_sites")
    op.drop_index(op.f("ix_host_sites_host"), table_name="host_sites")
    op.drop_table("host_sites")
