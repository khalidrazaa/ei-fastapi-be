from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.article import Article


async def get_article_by_slug(db: AsyncSession, slug: str) -> Article | None:
    result = await db.execute(select(Article).where(Article.slug == slug))
    return result.scalar_one_or_none()


async def list_articles(
    db: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[Article]:
    query = select(Article)
    if status:
        query = query.where(Article.status == status)

    query = query.order_by(Article.created_at.desc()).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


async def create_article(db: AsyncSession, **values) -> Article:
    article = Article(**values)
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article
