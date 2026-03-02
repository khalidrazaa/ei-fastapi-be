# app/db/query/niche.py

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.niche import Niche, NicheKeyword


# =========================================================
# NICHE
# =========================================================

def get_niche_by_id(db: Session, niche_id: int) -> Optional[Niche]:
    return db.get(Niche, niche_id)


def get_niche_by_name(db: Session, name: str) -> Optional[Niche]:
    stmt = select(Niche).where(Niche.name == name)
    return db.execute(stmt).scalar_one_or_none()


def get_niche_by_slug(db: Session, slug: str) -> Optional[Niche]:
    stmt = select(Niche).where(Niche.slug == slug)
    return db.execute(stmt).scalar_one_or_none()


def get_all_niches(
    db: Session,
    skip: int = 0,
    limit: int = 50
) -> List[Niche]:
    stmt = select(Niche).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()


def create_niche(
    db: Session,
    name: str,
    display_name: str,
    slug: str,
) -> Niche:
    niche = Niche(
        name=name,
        display_name=display_name,
        slug=slug,
    )
    db.add(niche)
    db.commit()
    db.refresh(niche)
    return niche


def update_niche(
    db: Session,
    niche: Niche,
    **kwargs
) -> Niche:
    for key, value in kwargs.items():
        setattr(niche, key, value)

    db.commit()
    db.refresh(niche)
    return niche


def delete_niche(db: Session, niche: Niche) -> None:
    db.delete(niche)
    db.commit()


# =========================================================
# KEYWORDS
# =========================================================

def create_keyword(
    db: Session,
    niche_id: int,
    keyword: str
) -> NicheKeyword:
    keyword_obj = NicheKeyword(
        niche_id=niche_id,
        keyword=keyword
    )
    db.add(keyword_obj)
    db.commit()
    db.refresh(keyword_obj)
    return keyword_obj


def get_keyword_by_id(
    db: Session,
    keyword_id: int
) -> Optional[NicheKeyword]:
    return db.get(NicheKeyword, keyword_id)


def get_keywords_by_niche(
    db: Session,
    niche_id: int
) -> List[NicheKeyword]:
    stmt = select(NicheKeyword).where(NicheKeyword.niche_id == niche_id)
    return db.execute(stmt).scalars().all()


def delete_keyword(
    db: Session,
    keyword: NicheKeyword
) -> None:
    db.delete(keyword)
    db.commit()