# app/db/query/niche.py

from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from app.db.models.niche import Niche, NicheKeyword


# =========================
# NICHE
# =========================

async def get_niche_by_id(db: AsyncSession, niche_id: int) -> Optional[Niche]:
    stmt = (
        select(Niche)
        .options(selectinload(Niche.keywords))
        .where(Niche.id == niche_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_niche_by_name(db: AsyncSession, name: str) -> Optional[Niche]:
    stmt = (
        select(Niche)
        .options(selectinload(Niche.keywords))
        .where(Niche.name == name)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_niches(db: AsyncSession, skip: int = 0, limit: int = 50) -> List[Niche]:
    stmt = (
        select(Niche)
        .where(Niche.is_active.is_(True))
        .options(selectinload(Niche.keywords))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def create_niche(db: AsyncSession, **data) -> Niche:
    niche = Niche(**data)
    db.add(niche)
    await db.commit()
    await db.refresh(niche)
    return await get_niche_by_id(db, niche.id)


async def update_niche(db: AsyncSession, niche: Niche, **kwargs) -> Niche:
    for key, value in kwargs.items():
        setattr(niche, key, value)
    await db.commit()
    await db.refresh(niche)
    return await get_niche_by_id(db, niche.id)


async def delete_niche(db: AsyncSession, niche: Niche) -> None:
    await db.delete(niche)
    await db.commit()


async def update_last_scanned(db: AsyncSession, niche_id: int,scanned_at: datetime,):
    """
    Update last scanned timestamp for a niche.
    """

    stmt = (
        update(Niche)
        .where(Niche.id == niche_id)
        .values(last_scanned_at=scanned_at)
    )

    await db.execute(stmt)
    await db.commit()


# =========================
# KEYWORDS
# =========================

async def create_keyword(db: AsyncSession, niche_id: int, keyword: str) -> NicheKeyword:
    keyword_obj = NicheKeyword(niche_id=niche_id, keyword=keyword)
    db.add(keyword_obj)
    await db.commit()
    await db.refresh(keyword_obj)
    return keyword_obj


async def get_keyword_by_id(db: AsyncSession, keyword_id: int) -> Optional[NicheKeyword]:
    return await db.get(NicheKeyword, keyword_id)


async def get_keywords_by_niche(db: AsyncSession, niche_id: int) -> List[NicheKeyword]:
    stmt = select(NicheKeyword).where(NicheKeyword.niche_id == niche_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def delete_keyword(db: AsyncSession, keyword: NicheKeyword) -> None:
    await db.delete(keyword)
    await db.commit()