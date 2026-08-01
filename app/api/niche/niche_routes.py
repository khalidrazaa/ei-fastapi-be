# app/api/niche/niche_routes.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from app.db.models.niche import Niche
from app.db.session import get_db
from app.schemas.niche import (
    NicheCreate,
    NicheOut,
    NicheUpdate,
    PaginatedNicheOut,
)
from app.services.niche_service import NicheService

router = APIRouter()
service = NicheService()


@router.post("/", response_model=NicheOut)
async def create_niche(
    niche: NicheCreate,
    db: AsyncSession = Depends(get_db),
):
    return await service.create_niche(db, niche)


@router.get("/", response_model = PaginatedNicheOut)
async def list_niches(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    return await service.get_all_niches(db, page, size)


@router.delete("/{niche_id}")
async def delete_niche(
    niche_id: int,
    db: AsyncSession = Depends(get_db),
):
    await service.delete_niche(db, niche_id)
    return {"detail": "Niche deleted"}


@router.post("/{niche_id}/keywords")
async def add_keyword(
    niche_id: int,
    keyword: str,
    db: AsyncSession = Depends(get_db),
):
    return await service.add_seed_keyword(db, niche_id, keyword)


@router.delete("/{niche_id}/keywords/{keyword_id}")
async def delete_keyword(
    niche_id: int,
    keyword_id: int,
    db: AsyncSession = Depends(get_db),
):
    await service.delete_keyword(db, niche_id, keyword_id)
    return {"detail": "Keyword deleted"}

@router.patch("/{niche_id}")
async def update_niche(
    niche_id: int,
    data: NicheUpdate,
    db: AsyncSession = Depends(get_db)
):
    niche = await service.update_niche(db, niche_id, data)

    if data.is_active is not None:
        niche.is_active = data.is_active

    await db.commit()
    return niche