# app/api/niche/niche_routes.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.schemas.niche import NicheCreate, Niche
from app.services.niche_service import NicheService

router = APIRouter()

@router.post("/", response_model=Niche)
def create_niche(niche: NicheCreate, db: Session = Depends(get_db)):
    service = NicheService()
    return service.create_niche(db, niche.name, niche.display_name)


@router.get("/", response_model=List[Niche])
def list_niches(db: Session = Depends(get_db)):
    service = NicheService()
    return service.get_all_niches(db)


@router.delete("/{niche_id}")
def delete_niche(niche_id: int, db: Session = Depends(get_db)):
    service = NicheService()
    service.delete_niche(db, niche_id)
    return {"detail": "Niche deleted"}


@router.post("/{niche_id}/keywords")
def add_keyword(niche_id: int, keyword: str, db: Session = Depends(get_db)):
    service = NicheService()
    return service.add_seed_keyword(db, niche_id, keyword)


@router.delete("/{niche_id}/keywords/{keyword_id}")
def delete_keyword(niche_id: int, keyword_id: int, db: Session = Depends(get_db)):
    service = NicheService()
    service.delete_keyword(db, niche_id, keyword_id)
    return {"detail": "Keyword deleted"}