# app/services/niche.py

from sqlalchemy.orm import Session
from app.db.query import niche as niche_query


class NicheService:

    def create_niche(self, db: Session, name: str, display_name: str):
        existing = niche_query.get_niche_by_name(db, name)
        if existing:
            return existing

        return niche_query.create_niche(db, name, display_name)


    def get_all_niches(self, db: Session):
        return niche_query.get_all_niches(db)


    def delete_niche(self, db: Session, niche_id: int):
        niche = niche_query.get_niche_by_id(db, niche_id)
        if niche:
            niche_query.delete_niche(db, niche)


    def add_seed_keyword(self, db: Session, niche_id: int, keyword: str):
        return niche_query.create_keyword(db, niche_id, keyword)


    def delete_keyword(self, db: Session, niche_id: int, keyword_id: int):
        keyword = niche_query.get_keyword_by_id(db, keyword_id)

        if not keyword:
            return

        if keyword.niche_id != niche_id:
            return

        niche_query.delete_keyword(db, keyword_id)