from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.article_comment import ArticleComment


async def list_comments_for_article(
    db: AsyncSession,
    *,
    article_id: int,
    host_site: str,
    limit: int = 100,
) -> list[ArticleComment]:
    query = (
        select(ArticleComment)
        .where(ArticleComment.article_id == article_id)
        .where(ArticleComment.host_site == host_site)
        .order_by(ArticleComment.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def create_comment(
    db: AsyncSession,
    *,
    article_id: int,
    host_site: str,
    author_name: str,
    content: str,
) -> ArticleComment:
    comment = ArticleComment(
        article_id=article_id,
        host_site=host_site,
        author_name=author_name,
        content=content,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment
