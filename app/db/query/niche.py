# app/db/query/niche.py

from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.models.niche import Niche, NicheKeyword


# ---------- Niche ----------

def get_niche_by_name(db: Session, name: str):
    stmt = select(Niche).where(Niche.name == name)
    return db.execute(stmt).scalar_one_or_none()


def get_niche_by_id(db: Session, niche_id: int):
    return db.get(Niche, niche_id)


def get_all_niches(db: Session):
    stmt = select(Niche)
    return db.execute(stmt).scalars().all()


def create_niche(db: Session, name: str, display_name: str):
    niche = Niche(name=name, display_name=display_name)
    db.add(niche)
    db.commit()
    db.refresh(niche)
    return niche


def delete_niche(db: Session, niche: Niche):
    db.delete(niche)
    db.commit()


# ---------- Keywords ----------

def create_keyword(db: Session, niche_id: int, keyword: str):
    keyword_obj = NicheKeyword(niche_id=niche_id, keyword=keyword)
    db.add(keyword_obj)
    db.commit()
    db.refresh(keyword_obj)
    return keyword_obj


def get_keyword_by_id(db: Session, keyword_id: int):
    return db.get(NicheKeyword, keyword_id)


def delete_keyword(db: Session, keyword_id: int):
    keyword = db.get(NicheKeyword, keyword_id)
    if keyword:
        db.delete(keyword)
        db.commit()