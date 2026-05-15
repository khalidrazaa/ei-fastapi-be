from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.public_api_security import verify_public_app_access
from app.db.session import get_db
from app.schemas.article import ArticleResponse
from app.schemas.article_comment import ArticleCommentCreate, ArticleCommentResponse
from app.services import article_comment_service, article_service

router = APIRouter()


@router.get("", response_model=list[ArticleResponse])
async def list_public_articles_route(
    host_site: str = Depends(verify_public_app_access),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.list_published_articles_for_host(
            db,
            host_site=host_site,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{slug}", response_model=ArticleResponse)
async def get_public_article_by_slug_route(
    slug: str,
    host_site: str = Depends(verify_public_app_access),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.get_published_article_by_slug_for_host(
            db,
            slug=slug,
            host_site=host_site,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{slug}/comments", response_model=list[ArticleCommentResponse])
async def list_public_article_comments_route(
    slug: str,
    host_site: str = Depends(verify_public_app_access),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_comment_service.list_comments_for_article_slug(
            db,
            slug=slug,
            host_site=host_site,
            limit=limit,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/{slug}/comments",
    response_model=ArticleCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_public_article_comment_route(
    slug: str,
    payload: ArticleCommentCreate,
    host_site: str = Depends(verify_public_app_access),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_comment_service.create_comment_for_article_slug(
            db,
            slug=slug,
            host_site=host_site,
            author_name=payload.author_name,
            content=payload.content,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
