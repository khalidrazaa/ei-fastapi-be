from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query import trend_video as trend_video_query


async def get_videos_by_niche(
    db: AsyncSession,
    niche_id: int,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
):
    return await trend_video_query.get_videos_by_niche(
        db=db,
        niche_id=niche_id,
        sort=sort,
        min_views=min_views,
        days=days,
    )


async def get_popular_videos(
    db: AsyncSession,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
    region_code: str | None = None,
):
    return await trend_video_query.get_popular_videos(
        db=db,
        sort=sort,
        min_views=min_views,
        days=days,
        region_code=region_code,
    )
