from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.keyword import KeywordRequest, KeywordResponse
from app.services.keyword_service import KeywordService
from app.db.session import get_db
from app.services.trend_scrape import TrendsScraper

router = APIRouter()

@router.post("/scrape")
async def scrape_trends(geo:str, hours:str, sts:str, db: AsyncSession = Depends(get_db)):
    scraper = TrendsScraper(db=db)
    # data = await scraper.fetch_trending_csv_bytes(geo, hours, sts)
    # result = await save_csv_bytes_to_mongo_pandas(csv_bytes)
    return await scraper.fetch_trending_csv_bytes(geo, hours, sts)

@router.get("/list_trends")
async def list_trends(
    db: AsyncSession = Depends(get_db),
    search: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    status: str | None = None,
    is_growing: bool | None = None,
    limit: int = 100,
    offset: int = 0,
):
    scraper = TrendsScraper(db=db)
    return await scraper.list_trends(
        search=search,
        category=category,
        subcategory=subcategory,
        status=status,
        is_growing=is_growing,
        limit=limit,
        offset=offset,
    )


@router.post("/keywords", response_model=KeywordResponse)
async def get_keywords(req: KeywordRequest, db: AsyncSession = Depends(get_db)):
    if not req.keyword or not req.keyword.strip():
        raise HTTPException(status_code=400, detail="keyword is required")
    service = KeywordService(db)
    return await service.get_keyword_data(req.keyword.strip())