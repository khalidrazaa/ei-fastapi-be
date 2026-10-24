from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.article import Article
from app.db.pagination import paginate_query
from app.db.query_builder import QueryBuilder


async def get_article_by_id(db: AsyncSession, article_id: int) -> Article | None:
    result = await db.execute(select(Article).where(Article.id == article_id))
    return result.scalar_one_or_none()

async def get_article_for_update(db: AsyncSession, article_id: int) -> Article | None:
    result = await db.execute(select(Article).where(Article.id == article_id).with_for_update())
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
        .sort(Article.created_at.desc(), Article.id.desc())
        .build()
        .limit(limit)
    )

    result = await db.execute(query)
    return result.scalars().all()


async def list_article_categories(db: AsyncSession) -> list[str]:
    category = func.trim(Article.category).label("category")
    query = (
        QueryBuilder(Article)
        .filter(Article.status.in_(["draft", "published"]), category != "")
        .sort(category)
        .build()
        .with_only_columns(category)
        .distinct()
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_article_page(
    db: AsyncSession,
    *,
    status: str | None = None,
    host_site: str | None = None,
    category: str | None = None,
    search: str | None = None,
    page: int = 1,
    size: int = 20,
    include_categories: bool = False,
) -> dict:
    builder = QueryBuilder(Article).filter(
        Article.status == status if status else None,
        Article.host_site == host_site if host_site else None,
    )
    # Match the category label used by the admin, including blank categories.
    category_name = func.coalesce(func.nullif(func.trim(Article.category), ""), "Uncategorized")
    categories = []
    if include_categories:
        # Count the full status/host scope before applying category or search.
        category_query = (
            builder.build()
            .with_only_columns(category_name.label("name"), func.count().label("count"))
            .group_by(category_name)
            .order_by(category_name)
        )
        result = await db.execute(category_query)
        categories = [dict(row) for row in result.mappings().all()]

    builder.filter(category_name == category if category else None)
    if search:
        # Treat user input as a literal substring, not SQL wildcard syntax.
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        builder.filter(or_(
            Article.title.ilike(pattern, escape="\\"),
            Article.slug.ilike(pattern, escape="\\"),
            category_name.ilike(pattern, escape="\\"),
        ))

    query = builder.sort(Article.created_at.desc(), Article.id.desc()).build()
    result = await paginate_query(db, query, page, size)
    if include_categories:
        result["categories"] = categories
        result["category_total"] = sum(category["count"] for category in categories)
    return result


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
