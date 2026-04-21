from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.niche import NicheKeyword
from app.db.models.trend_video import TrendVideo


STAGE_RANK = {
    "watchlist": 1,
    "emerging": 2,
    "breakout": 3,
    "sustained_demand": 4,
    "trending": 5,
}


def _video_views_per_hour(video: TrendVideo) -> float:
    age_hours = max(
        (datetime.now(timezone.utc) - video.published_at).total_seconds() / 3600,
        1.0,
    )
    return video.view_count / age_hours


def _stage_priority(video: TrendVideo, preferred_stage: str | None = None) -> tuple[int, int]:
    stage = video.trend_stage or "watchlist"
    is_preferred = 1 if preferred_stage and stage == preferred_stage else 0
    return (is_preferred, STAGE_RANK.get(stage, 0))


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
    if sort == "vph":
        return (_video_views_per_hour(video), video.virality_score, video.view_count)
    if sort == "breakout_score":
        return (
            video.breakout_score or 0,
            video.virality_score,
            video.view_count,
        )
    if sort == "engagement":
        return (
            video.engagement_score or 0,
            video.comment_count or 0,
            video.like_count or 0,
            video.virality_score,
        )
    if sort in STAGE_RANK:
        return (
            *_stage_priority(video, sort),
            video.virality_score,
            video.breakout_score or 0,
            _video_views_per_hour(video),
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

    return query


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _pick_thumbnail_url(thumbnails: dict[str, Any] | None) -> str | None:
    if not thumbnails:
        return None

    for key in ("maxres", "standard", "high", "medium", "default"):
        candidate = thumbnails.get(key, {})
        url = candidate.get("url")
        if url:
            return url

    return None


def _build_trend_video_values(
    *,
    keyword_id: int | None,
    video_data: dict[str, Any],
    channel_data: dict[str, Any] | None,
    score: float,
    analytics: dict[str, Any] | None,
    category_title: str,
    source: str,
    region_code: str | None,
) -> dict[str, Any]:
    snippet = video_data.get("snippet", {})
    stats = video_data.get("statistics", {})

    channel_snippet = (channel_data or {}).get("snippet", {})
    channel_stats = (channel_data or {}).get("statistics", {})

    published_at = _parse_datetime(snippet.get("publishedAt"))
    channel_published_at = _parse_datetime(channel_snippet.get("publishedAt"))

    values = {
        "keyword_id": keyword_id,
        "youtube_video_id": video_data["id"],
        "youtube_channel_id": snippet.get("channelId"),
        "title": snippet.get("title") or "",
        "description": snippet.get("description"),
        "channel_title": snippet.get("channelTitle") or "",
        "channel_custom_url": channel_snippet.get("customUrl"),
        "channel_description": channel_snippet.get("description"),
        "channel_country": channel_snippet.get("country"),
        "view_count": _coerce_int(stats.get("viewCount")) or 0,
        "like_count": _coerce_int(stats.get("likeCount")),
        "comment_count": _coerce_int(stats.get("commentCount")),
        "subscriber_count": _coerce_int(channel_stats.get("subscriberCount")),
        "channel_view_count": _coerce_int(channel_stats.get("viewCount")),
        "channel_video_count": _coerce_int(channel_stats.get("videoCount")),
        "hidden_subscriber_count": channel_stats.get("hiddenSubscriberCount"),
        "published_at": published_at,
        "channel_published_at": channel_published_at,
        "virality_score": score,
        "speed_score": analytics.get("speed_score") if analytics else None,
        "breakout_score": analytics.get("breakout_score") if analytics else None,
        "engagement_score": analytics.get("engagement_score") if analytics else None,
        "freshness_score": analytics.get("freshness_score") if analytics else None,
        "confidence_score": analytics.get("confidence_score") if analytics else None,
        "trend_stage": analytics.get("trend_stage") if analytics else None,
        "thumbnail_url": _pick_thumbnail_url(snippet.get("thumbnails")) or "",
        "channel_thumbnail_url": _pick_thumbnail_url(channel_snippet.get("thumbnails")),
        "category_id": snippet.get("categoryId"),
        "category_title": category_title,
        "source": source,
        "region_code": region_code,
        "video_payload": video_data,
        "channel_payload": channel_data,
    }

    if values["published_at"] is None:
        raise ValueError(
            f"Video {values['youtube_video_id']} is missing publishedAt and cannot be stored."
        )

    return values


async def create_or_update(
    db: AsyncSession,
    keyword_id: int | None,
    video_data: dict,
    score: float,
    analytics: dict[str, Any] | None = None,
    channel_data: dict | None = None,
    category_title: str = "Unknown",
    source: str | None = None,
    region_code: str | None = None,
) -> TrendVideo:
    """
    Uniqueness:
        - POPULAR -> (youtube_video_id + region_code)
        - NICHE -> (youtube_video_id + keyword_id)
    """

    resolved_source = source or "NICHE"
    values = _build_trend_video_values(
        keyword_id=keyword_id,
        video_data=video_data,
        channel_data=channel_data,
        score=score,
        analytics=analytics,
        category_title=category_title,
        source=resolved_source,
        region_code=region_code if resolved_source == "POPULAR" else None,
    )
    youtube_video_id = values["youtube_video_id"]

    if resolved_source == "POPULAR":
        result = await db.execute(
            select(TrendVideo).where(
                TrendVideo.youtube_video_id == youtube_video_id,
                TrendVideo.region_code == values["region_code"],
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
        for field, value in values.items():
            setattr(existing, field, value)

        await db.commit()
        await db.refresh(existing)
        return existing

    new_video = TrendVideo(**values)

    db.add(new_video)
    await db.commit()
    await db.refresh(new_video)

    return new_video


async def get_trend_video_by_id(db: AsyncSession, video_id: int) -> TrendVideo | None:
    result = await db.execute(
        select(TrendVideo).where(TrendVideo.id == video_id)
    )
    return result.scalar_one_or_none()


async def update_transcript(
    db: AsyncSession,
    video: TrendVideo,
    *,
    transcript_text: str | None,
    transcript_language_code: str | None = None,
    transcript_language: str | None = None,
    transcript_source: str | None = None,
    transcript_error: str | None = None,
) -> TrendVideo:
    video.transcript_text = transcript_text
    video.transcript_language_code = transcript_language_code
    video.transcript_language = transcript_language
    video.transcript_source = transcript_source
    video.transcript_error = transcript_error
    video.transcript_fetched_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(video)
    return video


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
    return sorted(
        result.scalars().all(),
        key=lambda video: _video_sort_key(video, sort),
        reverse=True,
    )


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
    return sorted(
        result.scalars().all(),
        key=lambda video: _video_sort_key(video, sort),
        reverse=True,
    )
