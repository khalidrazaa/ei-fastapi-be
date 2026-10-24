from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_security import require_admin
from app.db.session import get_db
from app.schemas.article import (
    AdminArticlePage,
    ArticleBulkDeleteRequest,
    ArticleDeleteResponse,
    ArticleDraftCreate,
    ArticleResponse,
    ArticleUpdate,
)
from app.services import article_service

router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("", response_model=ArticleResponse, status_code=201)
async def create_article_route(
    payload: ArticleDraftCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.create_draft(db, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/bulk-delete",
    response_model=ArticleDeleteResponse,
    dependencies=[Depends(require_admin)],
)
async def delete_articles_route(
    payload: ArticleBulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.delete_articles(db, payload.article_ids)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{article_id}",
    response_model=ArticleDeleteResponse,
    dependencies=[Depends(require_admin)],
)
async def delete_article_route(
    article_id: Annotated[int, Path(gt=0)],
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.delete_articles(db, [article_id])
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=AdminArticlePage | list[ArticleResponse])
async def list_articles_route(
    status: str | None = Query(
        default=None, description="Filter articles by draft or published status."
    ),
    page: int | None = Query(default=None, ge=1),
    size: int | None = Query(default=None, ge=1, le=100),
    category: str | None = Query(default=None, max_length=200),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500, deprecated=True),
    db: AsyncSession = Depends(get_db),
):
    try:
        if page is not None or size is not None or category is not None or search is not None:
            return await article_service.list_article_page(
                db, status=status, category=category, search=search,
                page=page if page is not None else 1,
                size=size if size is not None else 20,
            )
        return await article_service.list_articles(db, status=status, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/categories", response_model=list[str])
async def list_article_categories_route(db: AsyncSession = Depends(get_db)):
    return await article_service.list_article_categories(db)


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


