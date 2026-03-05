# app/db/query/trend_video.py

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trend_video import TrendVideo


async def create_or_update(
    db: AsyncSession,
    keyword_id: int,
    video_data: dict,
    score: float,
) -> TrendVideo:
    """
    Insert new trend video or update existing one.
    Uniqueness: keyword_id + youtube_video_id
    """

    youtube_video_id = video_data["id"]

    snippet = video_data.get("snippet", {})
    stats = video_data.get("statistics", {})

    title = snippet.get("title", "")
    channel_title = snippet.get("channelTitle", "")
    published_at = snippet.get("publishedAt")

    view_count = int(stats.get("viewCount", 0))
    like_count = (
        int(stats.get("likeCount")) if stats.get("likeCount") else None
    )
    comment_count = (
        int(stats.get("commentCount")) if stats.get("commentCount") else None
    )

    # 🔎 Check if video already exists for this keyword
    result = await db.execute(
        select(TrendVideo).where(
            TrendVideo.keyword_id == keyword_id,
            TrendVideo.youtube_video_id == youtube_video_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # 🔁 Update existing record
        existing.title = title
        existing.channel_title = channel_title
        existing.view_count = view_count
        existing.like_count = like_count
        existing.comment_count = comment_count
        existing.virality_score = score

        await db.commit()
        await db.refresh(existing)
        return existing

    # ➕ Create new record
    new_video = TrendVideo(
        keyword_id=keyword_id,
        youtube_video_id=youtube_video_id,
        title=title,
        channel_title=channel_title,
        view_count=view_count,
        like_count=like_count,
        comment_count=comment_count,
        published_at=published_at,
        virality_score=score,
    )

    db.add(new_video)
    await db.commit()
    await db.refresh(new_video)

    return new_video

async def get_videos_by_keyword(db: AsyncSession, keyword_id: int):
    result = await db.execute(
        select(TrendVideo)
        .where(TrendVideo.keyword_id == keyword_id)
        .order_by(TrendVideo.published_at.desc())
    )
    return result.scalars().all()