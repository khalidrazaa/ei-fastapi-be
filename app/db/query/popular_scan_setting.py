from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.popular_scan_setting import PopularScanSetting


DEFAULT_KEY = "default"


async def get_popular_scan_setting(
    db: AsyncSession,
    key: str = DEFAULT_KEY,
) -> PopularScanSetting | None:
    result = await db.execute(
        select(PopularScanSetting)
        .where(PopularScanSetting.key == key)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def create_popular_scan_setting(
    db: AsyncSession,
    *,
    region_codes: list[str],
    available_regions: list[dict[str, str]],
    max_results: int,
    youtube_scan_enabled: bool = True,
    popular_scan_enabled: bool = True,
    niche_scan_enabled: bool = True,
    key: str = DEFAULT_KEY,
) -> PopularScanSetting:
    setting = PopularScanSetting(
        key=key,
        region_codes=region_codes,
        available_regions=available_regions,
        max_results=max_results,
        youtube_scan_enabled=youtube_scan_enabled,
        popular_scan_enabled=popular_scan_enabled,
        niche_scan_enabled=niche_scan_enabled,
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
    available_regions: list[dict[str, str]],
    max_results: int,
    youtube_scan_enabled: bool | None = None,
    popular_scan_enabled: bool | None = None,
    niche_scan_enabled: bool | None = None,
) -> PopularScanSetting:
    setting.region_codes = region_codes
    setting.available_regions = available_regions
    setting.max_results = max_results
    if youtube_scan_enabled is not None:
        setting.youtube_scan_enabled = youtube_scan_enabled
    if popular_scan_enabled is not None:
        setting.popular_scan_enabled = popular_scan_enabled
    if niche_scan_enabled is not None:
        setting.niche_scan_enabled = niche_scan_enabled
    await db.commit()
    await db.refresh(setting)
    return setting
