# app/db/query/trend_video.py

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.db.models.trend_video import TrendVideo
from app.db.models.niche import NicheKeyword


async def create_or_update(
    db: AsyncSession,
    keyword_id: int|None,
    video_data: dict,
    score: float,
    source: str,
    region_code: str | None = None,
) -> TrendVideo:
    """
    Uniqueness:
        - POPULAR → (youtube_video_id + region_code)
        - NICHE → (youtube_video_id + keyword_id)
    """

    youtube_video_id = video_data["id"]

    snippet = video_data.get("snippet", {})
    stats = video_data.get("statistics", {})

    title = snippet.get("title", "")
    channel_title = snippet.get("channelTitle", "")

    # 🔥 Convert YouTube ISO string → datetime
    published_at_raw = snippet.get("publishedAt")

    thumbs = snippet.get("thumbnails", {})

    thumbnail_url = (
        thumbs.get("high", {}).get("url")
        or thumbs.get("medium", {}).get("url")
        or thumbs.get("default", {}).get("url")
    )

    published_at = None
    if published_at_raw:
        published_at = datetime.fromisoformat(
            published_at_raw.replace("Z", "+00:00")
        )

    view_count = int(stats.get("viewCount", 0))

    like_count = (
        int(stats.get("likeCount")) if stats.get("likeCount") else None
    )

    comment_count = (
        int(stats.get("commentCount")) if stats.get("commentCount") else None
    )

    if source == "POPULAR":
        result = await db.execute(
            select(TrendVideo)
            .where(
                TrendVideo.youtube_video_id == youtube_video_id,
                TrendVideo.region_code == region_code,
            )
        )
    else:
        result = await db.execute(
            select(TrendVideo).where(
                TrendVideo.keyword_id == keyword_id,
                TrendVideo.youtube_video_id == youtube_video_id,
            )
        )

    existing = result.scalar_one_or_none()

    if existing:
        existing.title = title
        existing.channel_title = channel_title
        existing.view_count = view_count
        existing.like_count = like_count
        existing.comment_count = comment_count
        existing.virality_score = score
        existing.published_at = published_at
        existing.thumbnail_url = thumbnail_url
        existing.source = source
        existing.region_code = region_code

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
        thumbnail_url=thumbnail_url,
        source=source,
        region_code=region_code,
    )

    db.add(new_video)
    await db.commit()
    await db.refresh(new_video)

    return new_video

async def get_recent_titles(db:AsyncSession, limit=500):

    result = await db.execute(
        select(TrendVideo.title)
        .order_by(TrendVideo.scanned_at.desc())
        .limit(limit)
    )

    return [row[0] for row in result.all()]

async def get_videos_by_keyword(db: AsyncSession,
                                 keyword_id: int,
                                 sort: str = "score",
                                 min_views: int = 0,
                                 days: int | None=None,
                                 ):
    
    query = select(TrendVideo).where(
        TrendVideo.keyword_id == keyword_id,
        TrendVideo.view_count >= min_views
    )

    # 🔽 Sorting
    if sort == "views":
        query = query.order_by(TrendVideo.view_count.desc())
    elif sort == "recent":
        query = query.order_by(TrendVideo.published_at.desc())
    else:  # default = score
        query = query.order_by(TrendVideo.virality_score.desc())

    result = await db.execute(query)
    return result.scalars().all()


async def get_recent_videos(db: AsyncSession, hours=24):

    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await db.execute(
        select(
            TrendVideo.title,
            TrendVideo.virality_score,
            TrendVideo.scanned_at
        ).where(
            TrendVideo.scanned_at >= cutoff
        )
    )

    return result.all()

async def get_videos_by_niche(
    db: AsyncSession,
    niche_id: int,
    sort: str = "score",
):
    query = (
        select(TrendVideo)
        .join(NicheKeyword, TrendVideo.keyword_id == NicheKeyword.id)
        .where(NicheKeyword.niche_id == niche_id)
    )

    # sorting
    if sort == "views":
        query = query.order_by(TrendVideo.view_count.desc())
    elif sort == "recent":
        query = query.order_by(TrendVideo.published_at.desc())
    else:
        query = query.order_by(TrendVideo.virality_score.desc())

    result = await db.execute(query)
    return result.scalars().all()