from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.popular_scan_setting import PopularScanSetting


DEFAULT_KEY = "default"


async def get_popular_scan_setting(
    db: AsyncSession,
    key: str = DEFAULT_KEY,
) -> PopularScanSetting | None:
    result = await db.execute(
        select(PopularScanSetting).where(PopularScanSetting.key == key)
    )
    return result.scalar_one_or_none()


async def create_popular_scan_setting(
    db: AsyncSession,
    *,
    region_codes: list[str],
    max_results: int,
    key: str = DEFAULT_KEY,
) -> PopularScanSetting:
    setting = PopularScanSetting(
        key=key,
        region_codes=region_codes,
        max_results=max_results,
    )
    db.add(setting)
    await db.commit()
    await db.refresh(setting)
    return setting


async def update_popular_scan_setting(
    db: AsyncSession,
    setting: PopularScanSetting,
    *,
    region_codes: list[str],
    max_results: int,
) -> PopularScanSetting:
    setting.region_codes = region_codes
    setting.max_results = max_results
    await db.commit()
    await db.refresh(setting)
    return setting
