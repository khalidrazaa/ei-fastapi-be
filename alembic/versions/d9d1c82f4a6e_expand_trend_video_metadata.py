"""expand trend video metadata

Revision ID: d9d1c82f4a6e
Revises: c3f4e92ab7d1
Create Date: 2026-04-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9d1c82f4a6e"
down_revision: Union[str, Sequence[str], None] = "c3f4e92ab7d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trend_videos", sa.Column("youtube_channel_id", sa.String(), nullable=True))
    op.add_column("trend_videos", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("trend_videos", sa.Column("channel_custom_url", sa.String(), nullable=True))
    op.add_column("trend_videos", sa.Column("channel_description", sa.Text(), nullable=True))
    op.add_column("trend_videos", sa.Column("channel_country", sa.String(), nullable=True))
    op.add_column("trend_videos", sa.Column("subscriber_count", sa.BigInteger(), nullable=True))
    op.add_column("trend_videos", sa.Column("channel_view_count", sa.BigInteger(), nullable=True))
    op.add_column("trend_videos", sa.Column("channel_video_count", sa.BigInteger(), nullable=True))
    op.add_column("trend_videos", sa.Column("hidden_subscriber_count", sa.Boolean(), nullable=True))
    op.add_column("trend_videos", sa.Column("channel_published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("trend_videos", sa.Column("channel_thumbnail_url", sa.String(), nullable=True))
    op.add_column("trend_videos", sa.Column("category_id", sa.String(), nullable=True))
    op.add_column("trend_videos", sa.Column("video_payload", sa.JSON(), nullable=True))
    op.add_column("trend_videos", sa.Column("channel_payload", sa.JSON(), nullable=True))

    op.create_index(
        op.f("ix_trend_videos_youtube_channel_id"),
        "trend_videos",
        ["youtube_channel_id"],
        unique=False,
    )

    op.alter_column(
        "trend_videos",
        "view_count",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        "trend_videos",
        "like_count",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )
    op.alter_column(
        "trend_videos",
        "comment_count",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )

    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY keyword_id, youtube_video_id
                    ORDER BY scanned_at DESC NULLS LAST, id DESC
                ) AS rn
            FROM trend_videos
            WHERE keyword_id IS NOT NULL
        )
        DELETE FROM trend_videos tv
        USING ranked
        WHERE tv.id = ranked.id AND ranked.rn > 1
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY region_code, youtube_video_id
                    ORDER BY scanned_at DESC NULLS LAST, id DESC
                ) AS rn
            FROM trend_videos
            WHERE region_code IS NOT NULL
        )
        DELETE FROM trend_videos tv
        USING ranked
        WHERE tv.id = ranked.id AND ranked.rn > 1
        """
    )

    op.execute("ALTER TABLE trend_videos DROP CONSTRAINT IF EXISTS uq_keyword_video")
    op.create_unique_constraint(
        "uq_trend_keyword_video",
        "trend_videos",
        ["keyword_id", "youtube_video_id"],
    )
    op.create_unique_constraint(
        "uq_trend_region_video",
        "trend_videos",
        ["region_code", "youtube_video_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_trend_region_video", "trend_videos", type_="unique")
    op.drop_constraint("uq_trend_keyword_video", "trend_videos", type_="unique")
    op.create_unique_constraint(
        "uq_keyword_video",
        "trend_videos",
        ["region_code", "youtube_video_id"],
    )

    op.alter_column(
        "trend_videos",
        "comment_count",
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        existing_nullable=True,
    )
    op.alter_column(
        "trend_videos",
        "like_count",
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        existing_nullable=True,
    )
    op.alter_column(
        "trend_videos",
        "view_count",
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        existing_nullable=False,
    )

    op.drop_index(op.f("ix_trend_videos_youtube_channel_id"), table_name="trend_videos")

    op.drop_column("trend_videos", "channel_payload")
    op.drop_column("trend_videos", "video_payload")
    op.drop_column("trend_videos", "category_id")
    op.drop_column("trend_videos", "channel_thumbnail_url")
    op.drop_column("trend_videos", "channel_published_at")
    op.drop_column("trend_videos", "hidden_subscriber_count")
    op.drop_column("trend_videos", "channel_video_count")
    op.drop_column("trend_videos", "channel_view_count")
    op.drop_column("trend_videos", "subscriber_count")
    op.drop_column("trend_videos", "channel_country")
    op.drop_column("trend_videos", "channel_description")
    op.drop_column("trend_videos", "channel_custom_url")
    op.drop_column("trend_videos", "description")
    op.drop_column("trend_videos", "youtube_channel_id")
