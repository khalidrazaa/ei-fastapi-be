# app/api/youtube_route.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.youtube_scan_service import YouTubeScanService
from app.clients.youtube_client import YouTubeClient
from app.schemas.trend_video import TrendVideoOut
from app.schemas.youtube import YouTubeScanResponse
from app.db.query.trend_video import get_videos_by_keyword
from app.core.config import settings


router = APIRouter()

@router.get("/niches/{niche_id}/scan-youtube", response_model=YouTubeScanResponse,)
async def scan_youtube_for_niche(niche_id: int, db: AsyncSession = Depends(get_db),):
    """
    Scan YouTube for all keywords in a niche and store intelligence.
    """

    try:

        youtube_client = YouTubeClient(settings.YOUTUBE_API_KEY)

        service = YouTubeScanService(
            db_session=db,
            youtube_client=youtube_client,
        )

        videos_saved = await service.scan_niche(niche_id)

        return {
            "niche_id": niche_id,
            "videos_saved": videos_saved,
            "videos": [],
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/keywords/{keyword_id}/scan-youtube", response_model=YouTubeScanResponse,)
async def scan_youtube(keyword_id: int, db: AsyncSession = Depends(get_db),):
    """
    Scan YouTube for a given keyword and store intelligence.
    """

    try:

        youtube_client = YouTubeClient(settings.YOUTUBE_API_KEY)

        service = YouTubeScanService(
            db_session=db,
            youtube_client=youtube_client,
        )

        videos_saved = await service.scan_keyword(keyword_id)

        return {
            "keyword_id": keyword_id,
            "videos_saved": videos_saved,
            "videos": [],
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/keywords/{keyword_id}/videos", response_model=list[TrendVideoOut],)
async def get_keyword_videos(keyword_id: int, db: AsyncSession = Depends(get_db),):
    """
    Get stored YouTube videos for a keyword.
    """

    videos = await get_videos_by_keyword(
        db=db,
        keyword_id=keyword_id,
    )

    return videos or []