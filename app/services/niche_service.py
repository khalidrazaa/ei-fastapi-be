# app/services/niche.py

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.query import niche as niche_query
from app.schemas.niche import NicheCreate


class NicheService:

    async def create_niche(self, db: AsyncSession, niche: NicheCreate):
        existing = await niche_query.get_niche_by_name(db, niche.name)
        if existing:
            return existing

        return await niche_query.create_niche(
            db,
            name=niche.name,
            display_name=niche.display_name,
            region_code=niche.region_code,
            scan_mode=niche.scan_mode,
            is_active=niche.is_active,
        )

    async def get_all_niches(self, db: AsyncSession):
        return await niche_query.get_all_niches(db)

    async def delete_niche(self, db: AsyncSession, niche_id: int):
        niche = await niche_query.get_niche_by_id(db, niche_id)
        if niche:
            await niche_query.delete_niche(db, niche)

    async def add_seed_keyword(self, db: AsyncSession, niche_id: int, keyword: str):
        return await niche_query.create_keyword(db, niche_id, keyword)

    async def delete_keyword(self, db: AsyncSession, niche_id: int, keyword_id: int):
        keyword = await niche_query.get_keyword_by_id(db, keyword_id)

        if not keyword:
            return

        if keyword.niche_id != niche_id:
            return

        await niche_query.delete_keyword(db, keyword)