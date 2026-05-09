from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.article import ArticleResponse, ArticleUpdate
from app.services import article_service

router = APIRouter()


@router.get("", response_model=list[ArticleResponse])
async def list_articles_route(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.list_articles(db, status=status, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article_route(
    article_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.get_article(db, article_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{article_id}", response_model=ArticleResponse)
async def update_article_route(
    article_id: int,
    payload: ArticleUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.update_article(
            db,
            article_id,
            payload.model_dump(exclude_unset=True),
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
