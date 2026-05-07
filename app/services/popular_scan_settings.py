from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query import popular_scan_setting as popular_scan_setting_query


DEFAULT_REGION_CODES = ["US"]
DEFAULT_MAX_RESULTS = 10
MAX_ALLOWED_RESULTS = 50


def _default_available_regions() -> list[dict[str, str]]:
    return [{"code": code, "name": code} for code in DEFAULT_REGION_CODES]


def normalize_available_regions(
    available_regions: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()

    for region in available_regions or []:
        code = str((region or {}).get("code") or "").strip().upper()
        name = str((region or {}).get("name") or "").strip()
        if not code or not name or code in seen:
            continue
        seen.add(code)
        normalized.append({"code": code, "name": name})

    return sorted(normalized, key=lambda region: region["name"])


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
) -> dict[str, list[str] | int | list[dict[str, str]]]:
    setting = await popular_scan_setting_query.get_popular_scan_setting(db)
    if setting is None:
        setting = await popular_scan_setting_query.create_popular_scan_setting(
            db,
            region_codes=DEFAULT_REGION_CODES,
            available_regions=_default_available_regions(),
            max_results=DEFAULT_MAX_RESULTS,
        )

    region_codes = normalize_region_codes(setting.region_codes) or DEFAULT_REGION_CODES.copy()
    available_regions = normalize_available_regions(setting.available_regions)
    if not available_regions:
        available_regions = [
            {"code": code, "name": code}
            for code in region_codes
        ]
    max_results = normalize_max_results(setting.max_results)

    if (
        region_codes != list(setting.region_codes or [])
        or available_regions != list(setting.available_regions or [])
        or max_results != setting.max_results
    ):
        setting = await popular_scan_setting_query.update_popular_scan_setting(
            db,
            setting,
            region_codes=region_codes,
            available_regions=available_regions,
            max_results=max_results,
        )

    return {
        "region_codes": list(setting.region_codes or region_codes),
        "available_regions": list(setting.available_regions or available_regions),
        "max_results": setting.max_results,
    }


async def save_popular_scan_settings(
    db: AsyncSession,
    *,
    region_codes: list[str],
    max_results: int,
) -> dict[str, list[str] | int | list[dict[str, str]]]:
    normalized_regions = normalize_region_codes(region_codes)
    if not normalized_regions:
        raise ValueError("Select at least one region.")

    normalized_max_results = normalize_max_results(max_results)
    setting = await popular_scan_setting_query.get_popular_scan_setting(db)
    current_available_regions = normalize_available_regions(
        list(setting.available_regions or []) if setting else None
    )
    if not current_available_regions:
        current_available_regions = [
            {"code": code, "name": code}
            for code in normalized_regions
        ]

    if setting is None:
        setting = await popular_scan_setting_query.create_popular_scan_setting(
            db,
            region_codes=normalized_regions,
            available_regions=current_available_regions,
            max_results=normalized_max_results,
        )
    else:
        setting = await popular_scan_setting_query.update_popular_scan_setting(
            db,
            setting,
            region_codes=normalized_regions,
            available_regions=current_available_regions,
            max_results=normalized_max_results,
        )

    return {
        "region_codes": list(setting.region_codes or normalized_regions),
        "available_regions": list(setting.available_regions or current_available_regions),
        "max_results": setting.max_results,
    }


async def save_popular_scan_regions(
    db: AsyncSession,
    *,
    available_regions: list[dict[str, str]],
) -> list[dict[str, str]]:
    normalized_regions = normalize_available_regions(available_regions)
    setting = await popular_scan_setting_query.get_popular_scan_setting(db)

    # Never overwrite stored regions with an empty payload from an upstream failure.
    if not normalized_regions:
        if setting and list(setting.available_regions or []):
            return normalize_available_regions(list(setting.available_regions or []))

        if setting is None:
            default_regions = _default_available_regions()
            setting = await popular_scan_setting_query.create_popular_scan_setting(
                db,
                region_codes=DEFAULT_REGION_CODES,
                available_regions=default_regions,
                max_results=DEFAULT_MAX_RESULTS,
            )
            return list(setting.available_regions or default_regions)

        fallback_region_codes = (
            normalize_region_codes(setting.region_codes) or DEFAULT_REGION_CODES.copy()
        )
        fallback_regions = [
            {"code": code, "name": code}
            for code in fallback_region_codes
        ]
        setting = await popular_scan_setting_query.update_popular_scan_setting(
            db,
            setting,
            region_codes=fallback_region_codes,
            available_regions=fallback_regions,
            max_results=normalize_max_results(setting.max_results),
        )
        return list(setting.available_regions or fallback_regions)

    if setting is None:
        setting = await popular_scan_setting_query.create_popular_scan_setting(
            db,
            region_codes=DEFAULT_REGION_CODES,
            available_regions=normalized_regions or _default_available_regions(),
            max_results=DEFAULT_MAX_RESULTS,
        )
    else:
        setting = await popular_scan_setting_query.update_popular_scan_setting(
            db,
            setting,
            region_codes=normalize_region_codes(setting.region_codes) or DEFAULT_REGION_CODES.copy(),
            available_regions=normalized_regions,
            max_results=normalize_max_results(setting.max_results),
        )

    return list(setting.available_regions or [])
