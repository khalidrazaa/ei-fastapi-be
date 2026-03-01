from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.services.youtube_service import YouTubeService
from app.services.niche_service import NicheService

from app.schemas.keyword import KeywordRequest, KeywordResponse
from app.services.keyword_service import KeywordService
from app.services.trend_scrape import TrendsScraper

router = APIRouter()


@router.post("/scrape")
async def scrape_trends(
    geo: str, hours: str, sts: str):
    scraper = TrendsScraper()
    return await scraper.fetch_trending_csv_bytes(geo, hours, sts)


@router.get("/list_trends")
async def list_trends(
    search: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    status: str | None = None,
    is_growing: bool | None = None,
    ongoing: bool | None = None,
    min_volume: int | None = None,
    sort_by: str = "search_volume",
    sort_dir: str = "desc",
    limit: int = 100,
    offset: int = 0,
):
    scraper = TrendsScraper()
    return await scraper.list_trends(
        search=search,
        category=category,
        subcategory=subcategory,
        status=status,
        is_growing=is_growing,
        ongoing=ongoing,
        min_volume=min_volume,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

@router.post("/youtube/scan")
async def scan_youtube_trends(niche_name: str):
    """
    Scans YouTube for breakout videos related to the given niche and updates the database. 
    """
    niche_service = NicheService()
    yt_service = YouTubeService()
    keywords = await niche_service.get_keywords_for_niche(niche_name)

    if not keywords:
        raise HTTPException(status_code=404,
                            detail=f"No keywords found for niche : {niche_name}. Add some keywords to the niche first.")
    
    try:
        trends = await yt_service.find_breakout_videos(keywords)
        return{
            "niche": niche_name,
            "trends_found": len(trends),
            "trends": trends
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scanning YouTube trends: {str(e)}")

    await yt_service.find_breakout_videos(keywords)


@router.get("/niches")
async def get_all_niches():
    # Your service logic here...
    pass