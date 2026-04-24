from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query import popular_scan_setting as popular_scan_setting_query


DEFAULT_REGION_CODES = ["US"]
DEFAULT_MAX_RESULTS = 10
MAX_ALLOWED_RESULTS = 50


def normalize_region_codes(region_codes: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for code in region_codes or []:
        value = str(code or "").strip().upper()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)

    return normalized


def normalize_max_results(max_results: int | None) -> int:
    value = max_results or DEFAULT_MAX_RESULTS
    return max(1, min(int(value), MAX_ALLOWED_RESULTS))


async def get_or_create_popular_scan_settings(
    db: AsyncSession,
) -> dict[str, list[str] | int]:
    setting = await popular_scan_setting_query.get_popular_scan_setting(db)
    if setting is None:
        setting = await popular_scan_setting_query.create_popular_scan_setting(
            db,
            region_codes=DEFAULT_REGION_CODES,
            max_results=DEFAULT_MAX_RESULTS,
        )

    region_codes = normalize_region_codes(setting.region_codes) or DEFAULT_REGION_CODES.copy()
    max_results = normalize_max_results(setting.max_results)

    if region_codes != list(setting.region_codes or []) or max_results != setting.max_results:
        setting = await popular_scan_setting_query.update_popular_scan_setting(
            db,
            setting,
            region_codes=region_codes,
            max_results=max_results,
        )

    return {
        "region_codes": list(setting.region_codes or region_codes),
        "max_results": setting.max_results,
    }


async def save_popular_scan_settings(
    db: AsyncSession,
    *,
    region_codes: list[str],
    max_results: int,
) -> dict[str, list[str] | int]:
    normalized_regions = normalize_region_codes(region_codes)
    if not normalized_regions:
        raise ValueError("Select at least one region.")

    normalized_max_results = normalize_max_results(max_results)
    setting = await popular_scan_setting_query.get_popular_scan_setting(db)

    if setting is None:
        setting = await popular_scan_setting_query.create_popular_scan_setting(
            db,
            region_codes=normalized_regions,
            max_results=normalized_max_results,
        )
    else:
        setting = await popular_scan_setting_query.update_popular_scan_setting(
            db,
            setting,
            region_codes=normalized_regions,
            max_results=normalized_max_results,
        )

    return {
        "region_codes": list(setting.region_codes or normalized_regions),
        "max_results": setting.max_results,
    }
