from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query.yt_video import get_videos_by_keyword
from app.db.session import get_db
from app.schemas.popular_video import PopularVideoOut
from app.schemas.trend_video import (
    ManualTranscriptCreateIn,
    TranscriptContentOut,
    TranscriptContentUpdateIn,
    TrendVideoOut,
)
from app.services.yt_video import (
    create_manual_transcript,
    get_popular_videos,
    get_video_transcript,
    get_videos_with_transcripts,
    save_video_transcript,
)
from app.services.yt_video_service.yt_video import get_videos_by_niche_id

router = APIRouter()


@router.get("/keywords/{keyword_id}", response_model=list[TrendVideoOut])
async def get_keyword_videos(
    keyword_id: int,
    db: AsyncSession = Depends(get_db),
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
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


@router.get("/niches/{niche_id}", response_model=list[TrendVideoOut])
async def get_niche_videos_route(
    niche_id: int,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    return await get_videos_by_niche_id(
        db=db,
        niche_id=niche_id,
        sort=sort,
        min_views=min_views,
        days=days,
        page=page,
        size=size,
    )


@router.get("/popular", response_model=list[PopularVideoOut])
async def get_popular_videos_route(
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
    region_code: str | None = None,
    source: str | None = None,
    db: AsyncSession = Depends(get_db),
):

    print(
        "Getting popular videos with params:",
        {
            "sort": sort,
            "min_views": min_views,
            "days": days,
            "region_code": region_code,
            "source": source,
        },
    )
    return await get_popular_videos(
        db=db,
        sort=sort,
        min_views=min_views,
        days=days,
        region_code=region_code,
        source=source,
    )


@router.post("/transcript/{video_id}", response_model=TrendVideoOut)
async def save_video_transcript_route(
    video_id: int,
    payload: TranscriptContentUpdateIn,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await save_video_transcript(
            db=db,
            trend_video_id=video_id,
            transcript_text=payload.transcript_text,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcripts/manual", response_model=TrendVideoOut)
async def create_manual_transcript_route(
    payload: ManualTranscriptCreateIn,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_manual_transcript(
            db=db,
            title=payload.title,
            category_title=payload.category_title,
            transcript_text=payload.transcript_text,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transcript/{video_id}", response_model=TranscriptContentOut)
async def get_video_transcript_route(
    video_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_video_transcript(db=db, trend_video_id=video_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transcripts/videos", response_model=list[TrendVideoOut])
async def get_videos_with_transcripts_route(
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_videos_with_transcripts(db=db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
