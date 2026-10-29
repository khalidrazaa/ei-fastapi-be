"""Persist VPS article images and atomic multipart import receipts."""

import sqlalchemy as sa
from alembic import op

revision = "c04_article_images"
down_revision = "c03_youtube_scan_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("article_images",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="SET NULL")),
        sa.Column("original_article_id", sa.Integer(), nullable=False),
        sa.Column("storage_name", sa.String(40), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_article_images_article_id", "article_images", ["article_id"])
    op.create_index("ix_article_images_original_article_id", "article_images", ["original_article_id"])
    op.create_table("article_imports",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("admin_id", sa.String(), nullable=False),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="SET NULL")),
        sa.Column("target_article_id", sa.Integer()),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_article_imports_article_id", "article_imports", ["article_id"])


def downgrade() -> None:
    # Back up and remove stored files separately; a schema rollback does not delete media.
    op.drop_index("ix_article_imports_article_id", table_name="article_imports")
    op.drop_table("article_imports")
    op.drop_index("ix_article_images_original_article_id", table_name="article_images")
    op.drop_index("ix_article_images_article_id", table_name="article_images")
    op.drop_table("article_images")
