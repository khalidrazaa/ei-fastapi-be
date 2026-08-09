from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query.yt_video_query import query_by_niche


async def get_videos_by_niche_id(
    db: AsyncSession,
    niche_id: int,
    sort: list[str] = [],
    min_views: int = 0,
    days: int | None = None,
    page: int = 1,
    size: int = 20,
):
    return await query_by_niche(
        db=db,
        niche_id=niche_id,
        sort=sort,
        min_views=min_views,
        days=days,
        page=page,
        size=size,
    )
