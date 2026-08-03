from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.youtube_client import YouTubeClient
from app.core.config import settings
from app.db.session import get_db
from app.scheduler.jobs import scan_popular_videos
from app.schemas.youtube import (
    PopularScanRunResponse,
    PopularScanSettingsOut,
    PopularScanSettingsUpdate,
    YouTubeRegionOut,
    YouTubeScanResponse,
)
from app.services.popular_scan_settings import (
    get_or_create_popular_scan_settings,
    normalize_available_regions,
    save_popular_scan_regions,
    save_popular_scan_settings,
)
from app.services.scanner.youtube_scan_service import YouTubeScanService

router = APIRouter()


# YT-scanning setting routes---------------------------------------------------
def _map_youtube_regions(payload: dict) -> list[dict[str, str]]:
    regions: list[dict[str, str]] = []

    for item in payload.get("items", []):
        code = str(item.get("id") or "").strip().upper()
        name = str(item.get("snippet", {}).get("name") or "").strip()
        if code and name:
            regions.append({"code": code, "name": name})

    return sorted(regions, key=lambda region: region["name"])


@router.get("/popular/regions", response_model=list[YouTubeRegionOut])
async def get_popular_regions_route(
    db: AsyncSession = Depends(get_db),
):
    try:
        settings_payload = await get_or_create_popular_scan_settings(db)
        return normalize_available_regions(
            settings_payload.get("available_regions")
            if isinstance(settings_payload, dict)
            else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/popular/regions/refresh", response_model=list[YouTubeRegionOut])
async def refresh_popular_regions_route(
    db: AsyncSession = Depends(get_db),
):
    try:
        youtube_client = YouTubeClient(settings.YOUTUBE_API_KEY)
        payload = await youtube_client.get_i18n_regions()
        regions = _map_youtube_regions(payload)
        return await save_popular_scan_regions(db, available_regions=regions)
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


# YT-scanning routes-----------------------------------------------------------
@router.get("/niches/{niche_id}")
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


@router.post("/keywords/{keyword_id}", response_model=YouTubeScanResponse)
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
