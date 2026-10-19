from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.videos.video_filters import video_list_filters
from app.db.query.yt_video import get_videos_by_keyword
from app.db.session import get_db
from app.schemas.trend_video import (
    TrendVideoOut,
    TrendVideoPaginated,
)
from app.services.yt_video_service.yt_video import get_video_list

router = APIRouter()


@router.get("/keywords/{keyword_id}", response_model=list[TrendVideoOut])
async def get_keyword_videos(
    keyword_id: int,
    db: AsyncSession = Depends(get_db),
    sort: str = "score",
    min_views: int = Query(0, ge=0),
    days: int | None = Query(None, ge=1),
):
    """
    Get stored YouTube videos for a keyword.
    """

    videos = await get_videos_by_keyword(
        db=db,
        keyword_id=keyword_id,
        sort=sort,
        min_views=min_views,
        days=days,
    )

    return videos or []


@router.get("/niches/{niche_id}", response_model=TrendVideoPaginated)
async def get_niche_videos_route(
    niche_id: int,
    filters: dict = Depends(video_list_filters),
    db: AsyncSession = Depends(get_db),
):
    return await get_video_list(db=db, niche_id=niche_id, **filters)


@router.get("/popular", response_model=TrendVideoPaginated)
async def get_popular_videos_route(
    filters: dict = Depends(video_list_filters),
    db: AsyncSession = Depends(get_db),
):
    """Use the same filtered, deduplicated pagination as the niche list."""
    return await get_video_list(db=db, **filters)


