from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.article import Article
from app.db.query_builder import QueryBuilder


async def get_article_by_id(db: AsyncSession, article_id: int) -> Article | None:
    result = await db.execute(select(Article).where(Article.id == article_id))
    return result.scalar_one_or_none()


async def get_article_ids_for_update(
    db: AsyncSession, article_ids: list[int]
) -> list[int]:
    result = await db.execute(
        select(Article.id)
        .where(Article.id.in_(article_ids))
        .order_by(Article.id)
        .with_for_update()
    )
    return list(result.scalars().all())


async def delete_articles(db: AsyncSession, article_ids: list[int]) -> list[int]:
    # Related comments are removed by their ON DELETE CASCADE foreign key.
    result = await db.execute(
        delete(Article).where(Article.id.in_(article_ids)).returning(Article.id)
    )
    return list(result.scalars().all())


async def get_article_by_slug(db: AsyncSession, slug: str) -> Article | None:
    result = await db.execute(select(Article).where(Article.slug == slug))
    return result.scalar_one_or_none()


async def list_articles(
    db: AsyncSession,
    *,
    status: str | None = None,
    host_site: str | None = None,
    limit: int = 100,
) -> list[Article]:
    query = (
        QueryBuilder(Article)
        .filter(
            Article.status == status if status else None,
            Article.host_site == host_site if host_site else None,
        )
        .sort(Article.created_at.desc())
        .build()
        .limit(limit)
    )

    result = await db.execute(query)
    return result.scalars().all()


async def create_article(db: AsyncSession, **values) -> Article:
    article = Article(**values)
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article


async def update_article(
    db: AsyncSession,
    article: Article,
    **values,
) -> Article:
    for field, value in values.items():
        setattr(article, field, value)

    await db.commit()
    await db.refresh(article)
    return article
