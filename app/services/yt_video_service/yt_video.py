from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query.yt_video_query import PublishedAge, query_by_niche


async def get_videos_by_niche_id(
    db: AsyncSession,
    niche_id: int,
    min_views: int = 0,
    published_age: PublishedAge | None = None,
    published_from: date | None = None,
    published_to: date | None = None,
    trend_stages: list[str] | None = None,
    region_codes: list[str] | None = None,
    sources: list[str] | None = None,
    category_titles: list[str] | None = None,
    min_score: float | None = None,
    min_speed_score: float | None = None,
    min_breakout_score: float | None = None,
    min_engagement_score: float | None = None,
    min_confidence_score: float | None = None,
    page: int = 1,
    size: int = 20,
):
    return await query_by_niche(
        db=db,
        niche_id=niche_id,
        min_views=min_views,
        published_age=published_age,
        published_from=published_from,
        published_to=published_to,
        trend_stages=trend_stages,
        region_codes=region_codes,
        sources=sources,
        category_titles=category_titles,
        min_score=min_score,
        min_speed_score=min_speed_score,
        min_breakout_score=min_breakout_score,
        min_engagement_score=min_engagement_score,
        min_confidence_score=min_confidence_score,
        page=page,
        size=size,
    )
