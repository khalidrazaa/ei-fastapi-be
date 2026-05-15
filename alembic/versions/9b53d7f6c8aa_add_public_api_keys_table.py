"""add public api keys table

Revision ID: 9b53d7f6c8aa
Revises: 8c41e2aa7d31
Create Date: 2026-05-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b53d7f6c8aa"
down_revision: Union[str, Sequence[str], None] = "8c41e2aa7d31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "public_api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host_site_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["host_site_id"], ["host_sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_public_api_keys_host_site_id"),
        "public_api_keys",
        ["host_site_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_public_api_keys_id"),
        "public_api_keys",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_public_api_keys_key_hash"),
        "public_api_keys",
        ["key_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_public_api_keys_key_prefix"),
        "public_api_keys",
        ["key_prefix"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_public_api_keys_key_prefix"), table_name="public_api_keys")
    op.drop_index(op.f("ix_public_api_keys_key_hash"), table_name="public_api_keys")
    op.drop_index(op.f("ix_public_api_keys_id"), table_name="public_api_keys")
    op.drop_index(op.f("ix_public_api_keys_host_site_id"), table_name="public_api_keys")
    op.drop_table("public_api_keys")
