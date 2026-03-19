from sqlalchemy.ext.asyncio import AsyncSession
from app.db.query import trend_video as trend_video_query


async def get_videos_by_niche(
    db: AsyncSession,
    niche_id: int,
    sort: str = "score",
):
    return await trend_video_query.get_videos_by_niche(
        db=db,
        niche_id=niche_id,
        sort=sort,
    )