from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.article import ArticleResponse
from app.db.query import article as article_query

router = APIRouter()


@router.get("", response_model=list[ArticleResponse])
async def list_articles_route(
    status: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    return await article_query.list_articles(db, status=status, limit=limit)
