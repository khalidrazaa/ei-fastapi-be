"""add article comments table

Revision ID: 8c41e2aa7d31
Revises: c2d7a0b1f6e9
Create Date: 2026-05-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c41e2aa7d31"
down_revision: Union[str, Sequence[str], None] = "c2d7a0b1f6e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("host_site", sa.String(), nullable=False),
        sa.Column("author_name", sa.String(length=80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_article_comments_article_id"),
        "article_comments",
        ["article_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_article_comments_host_site"),
        "article_comments",
        ["host_site"],
        unique=False,
    )
    op.create_index(
        op.f("ix_article_comments_id"),
        "article_comments",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_article_comments_id"), table_name="article_comments")
    op.drop_index(op.f("ix_article_comments_host_site"), table_name="article_comments")
    op.drop_index(op.f("ix_article_comments_article_id"), table_name="article_comments")
    op.drop_table("article_comments")
