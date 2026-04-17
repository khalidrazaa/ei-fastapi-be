from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.niche import NicheKeyword
from app.db.models.trend_video import TrendVideo


def _video_sort_key(video: TrendVideo, sort: str) -> tuple:
    if sort == "views":
        return (video.view_count, video.comment_count or 0, video.virality_score)
    if sort == "comments":
        return (video.comment_count or 0, video.view_count, video.virality_score)
    if sort == "recent":
        return (
            video.published_at.timestamp(),
            video.virality_score,
            video.view_count,
        )
    return (video.virality_score, video.comment_count or 0, video.view_count)


def _apply_video_filters(
    query,
    *,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
):
    query = query.where(TrendVideo.view_count >= min_views)

    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.where(TrendVideo.published_at >= cutoff)

    if sort == "views":
        return query.order_by(
            TrendVideo.view_count.desc(),
            TrendVideo.comment_count.desc(),
        )
    if sort == "comments":
        return query.order_by(
            TrendVideo.comment_count.desc(),
            TrendVideo.view_count.desc(),
        )
    if sort == "recent":
        return query.order_by(TrendVideo.published_at.desc())
    return query.order_by(
        TrendVideo.virality_score.desc(),
        TrendVideo.comment_count.desc(),
        TrendVideo.view_count.desc(),
    )


async def create_or_update(
    db: AsyncSession,
    keyword_id: int | None,
    video_data: dict,
    score: float,
    category_title: str = "Unknown",
    source: str | None = None,
    region_code: str | None = None,
) -> TrendVideo:
    """
    Uniqueness:
        - POPULAR -> (youtube_video_id + region_code)
        - NICHE -> (youtube_video_id + keyword_id)
    """

    youtube_video_id = video_data["id"]

    snippet = video_data.get("snippet", {})
    stats = video_data.get("statistics", {})

    title = snippet.get("title", "")
    channel_title = snippet.get("channelTitle", "")

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
    like_count = int(stats.get("likeCount")) if stats.get("likeCount") else None
    comment_count = (
        int(stats.get("commentCount")) if stats.get("commentCount") else None
    )

    if source == "POPULAR":
        result = await db.execute(
            select(TrendVideo).where(
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
        existing.category_title = category_title
        existing.source = source or existing.source
        existing.region_code = region_code

        await db.commit()
        await db.refresh(existing)
        return existing

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
        category_title=category_title,
        source=source or "NICHE",
        region_code=region_code,
    )

    db.add(new_video)
    await db.commit()
    await db.refresh(new_video)

    return new_video


async def get_recent_titles(db: AsyncSession, limit=500):
    result = await db.execute(
        select(TrendVideo.title)
        .order_by(TrendVideo.scanned_at.desc())
        .limit(limit)
    )
    return [row[0] for row in result.all()]


async def get_videos_by_keyword(
    db: AsyncSession,
    keyword_id: int,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
):
    query = select(TrendVideo).where(TrendVideo.keyword_id == keyword_id)
    query = _apply_video_filters(
        query,
        sort=sort,
        min_views=min_views,
        days=days,
    )

    result = await db.execute(query)
    return result.scalars().all()


async def get_recent_videos(db: AsyncSession, hours=24):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await db.execute(
        select(
            TrendVideo.title,
            TrendVideo.virality_score,
            TrendVideo.scanned_at,
        ).where(TrendVideo.scanned_at >= cutoff)
    )

    return result.all()


async def get_videos_by_niche(
    db: AsyncSession,
    niche_id: int,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
):
    query = (
        select(TrendVideo)
        .join(NicheKeyword, TrendVideo.keyword_id == NicheKeyword.id)
        .where(NicheKeyword.niche_id == niche_id)
    )
    query = _apply_video_filters(
        query,
        sort=sort,
        min_views=min_views,
        days=days,
    )

    result = await db.execute(query)

    deduped_by_video_id: dict[str, TrendVideo] = {}
    for video in result.scalars():
        existing = deduped_by_video_id.get(video.youtube_video_id)
        if existing is None or video.virality_score > existing.virality_score:
            deduped_by_video_id[video.youtube_video_id] = video

    return sorted(
        deduped_by_video_id.values(),
        key=lambda video: _video_sort_key(video, sort),
        reverse=True,
    )


async def get_popular_videos(
    db: AsyncSession,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
    region_code: str | None = None,
    source: str | None = None,
):
    print(f"Fetching popular videos with filters source: {source}")
    query = select(TrendVideo)

    if source and source != "all":
        query = query.where(TrendVideo.source == source)

    if region_code:
        query = query.where(TrendVideo.region_code == region_code.upper())

    query = _apply_video_filters(
        query,
        sort=sort,
        min_views=min_views,
        days=days,
    )

    result = await db.execute(query)
    return result.scalars().all()
