"""Persistence for article media; transaction ownership stays with the service."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.article_image import ArticleImage, ArticleImport


async def get_import(db: AsyncSession, request_id: str) -> ArticleImport | None:
    result = await db.execute(select(ArticleImport).where(ArticleImport.request_id == request_id))
    return result.scalar_one_or_none()


async def add_import(db: AsyncSession, **values) -> ArticleImport:
    receipt = ArticleImport(**values)
    db.add(receipt)
    await db.flush()
    return receipt


async def add_image(db: AsyncSession, **values) -> ArticleImage:
    image = ArticleImage(**values)
    db.add(image)
    await db.flush()
    return image


async def get_image(db: AsyncSession, article_id: int, storage_name: str) -> ArticleImage | None:
    result = await db.execute(select(ArticleImage).where(
        ArticleImage.original_article_id == article_id,
        ArticleImage.storage_name == storage_name,
    ))
    return result.scalar_one_or_none()


async def storage_paths(db: AsyncSession) -> set[str]:
    result = await db.execute(select(ArticleImage.original_article_id, ArticleImage.storage_name))
    return {f"articles/{article_id}/{name}" for article_id, name in result.all()}
