from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.article_comment import ArticleComment
from app.db.query import article_comment as article_comment_query
from app.services import article_service


def _normalize_host_site(host_site: str) -> str:
    host = str(host_site or "").strip().lower()
    host = host.removeprefix("https://").removeprefix("http://")
    host = host.split("/", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    if not host:
        raise ValueError("Host site is required.")
    return host


def _normalize_author_name(value: str) -> str:
    normalized = str(value or "").strip()
    if len(normalized) < 2:
        raise ValueError("Author name must be at least 2 characters.")
    if len(normalized) > 80:
        raise ValueError("Author name must be at most 80 characters.")
    return normalized


def _normalize_comment_content(value: str) -> str:
    normalized = str(value or "").strip()
    if len(normalized) < 2:
        raise ValueError("Comment must be at least 2 characters.")
    if len(normalized) > 2000:
        raise ValueError("Comment must be at most 2000 characters.")
    return normalized


async def list_comments_for_article_slug(
    db: AsyncSession,
    *,
    slug: str,
    host_site: str,
    limit: int = 100,
) -> list[ArticleComment]:
    normalized_host = _normalize_host_site(host_site)
    article = await article_service.get_published_article_by_slug_for_host(
        db,
        slug=slug,
        host_site=normalized_host,
    )
    return await article_comment_query.list_comments_for_article(
        db,
        article_id=article.id,
        host_site=normalized_host,
        limit=limit,
    )


async def create_comment_for_article_slug(
    db: AsyncSession,
    *,
    slug: str,
    host_site: str,
    author_name: str,
    content: str,
) -> ArticleComment:
    normalized_host = _normalize_host_site(host_site)
    normalized_author = _normalize_author_name(author_name)
    normalized_content = _normalize_comment_content(content)

    article = await article_service.get_published_article_by_slug_for_host(
        db,
        slug=slug,
        host_site=normalized_host,
    )
    return await article_comment_query.create_comment(
        db,
        article_id=article.id,
        host_site=normalized_host,
        author_name=normalized_author,
        content=normalized_content,
    )
