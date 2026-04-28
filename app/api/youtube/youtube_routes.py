from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.youtube_client import YouTubeClient
from app.core.config import settings
from app.db.query.trend_video import get_videos_by_keyword
from app.db.session import get_db
from app.schemas.article import ArticleDraftGenerateRequest, ArticleResponse
from app.schemas.popular_video import PopularVideoOut
from app.schemas.trend_video import (
    TranscriptContentOut,
    TranscriptContentUpdateIn,
    TrendVideoOut,
)
from app.schemas.youtube import (
    PopularScanRunResponse,
    PopularScanSettingsOut,
    PopularScanSettingsUpdate,
    YouTubeRegionOut,
    YouTubeScanResponse,
)
from app.scheduler.jobs import scan_popular_videos
from app.services.popular_scan_settings import (
    get_or_create_popular_scan_settings,
    save_popular_scan_settings,
)
from app.services.scanner.youtube_scan_service import YouTubeScanService
from app.services.trend_video import (
    generate_article_draft_for_video,
    get_video_transcript,
    get_popular_videos,
    get_videos_with_transcripts,
    get_videos_by_niche,
    save_video_transcript,
)

router = APIRouter()


def _map_youtube_regions(payload: dict) -> list[dict[str, str]]:
    regions: list[dict[str, str]] = []

    for item in payload.get("items", []):
        code = str(item.get("id") or "").strip().upper()
        name = str(item.get("snippet", {}).get("name") or "").strip()
        if code and name:
            regions.append({"code": code, "name": name})

    return sorted(regions, key=lambda region: region["name"])


@router.get("/niches/{niche_id}/scan-youtube")
async def scan_youtube_for_niche(
    niche_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Scan YouTube for all keywords in a niche and store intelligence.
    """

    try:
        youtube_client = YouTubeClient(settings.YOUTUBE_API_KEY)
        service = YouTubeScanService(
            db_session=db,
            youtube_client=youtube_client,
        )

        videos_saved = await service.scan_youtube_niche(niche_id)

        return {
            "niche_id": niche_id,
            "videos_saved": videos_saved,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keywords/{keyword_id}/scan-youtube", response_model=YouTubeScanResponse)
async def scan_youtube(
    keyword_id: int,
    db: AsyncSession = Depends(get_db),
):
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


@router.get("/keywords/{keyword_id}/videos", response_model=list[TrendVideoOut])
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


@router.get("/niches/{niche_id}/videos", response_model=list[TrendVideoOut])
async def get_niche_videos_route(
    niche_id: int,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_videos_by_niche(
        db=db,
        niche_id=niche_id,
        sort=sort,
        min_views=min_views,
        days=days,
    )


@router.get("/popular/videos", response_model=list[PopularVideoOut])
async def get_popular_videos_route(
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
    region_code: str | None = None,
    source: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    
    print("Getting popular videos with params:", {
        "sort": sort,
        "min_views": min_views,
        "days": days,
        "region_code": region_code,
        "source": source,
    })
    return await get_popular_videos(
        db=db,
        sort=sort,
        min_views=min_views,
        days=days,
        region_code=region_code,
        source=source,
    )


@router.get("/popular/regions", response_model=list[YouTubeRegionOut])
async def get_popular_regions_route():
    try:
        youtube_client = YouTubeClient(settings.YOUTUBE_API_KEY)
        payload = await youtube_client.get_i18n_regions()
        return _map_youtube_regions(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/popular/settings", response_model=PopularScanSettingsOut)
async def get_popular_scan_settings_route(
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_or_create_popular_scan_settings(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/popular/settings", response_model=PopularScanSettingsOut)
async def update_popular_scan_settings_route(
    payload: PopularScanSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await save_popular_scan_settings(
            db,
            region_codes=payload.region_codes,
            max_results=payload.max_results,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/videos/{video_id}/transcript", response_model=TrendVideoOut)
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


@router.get("/videos/{video_id}/transcript", response_model=TranscriptContentOut)
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


@router.post("/videos/{video_id}/draft-article", response_model=ArticleResponse)
async def generate_article_draft_route(
    video_id: int,
    payload: ArticleDraftGenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await generate_article_draft_for_video(
            db=db,
            trend_video_id=video_id,
            provider=payload.provider if payload else "gemini",
            prompt=payload.prompt if payload else None,
            additional_context=payload.additional_context if payload else None,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/popular/scan", response_model=PopularScanRunResponse)
async def trigger_popular_scan(
    payload: PopularScanSettingsUpdate | None = None,
):
    try:
        if payload is None:
            return await scan_popular_videos()

        return await scan_popular_videos(
            region_codes=payload.region_codes,
            max_results=payload.max_results,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug-trending")
async def debug_trending():
    return await scan_popular_videos()
