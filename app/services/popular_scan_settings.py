import re
from typing import Literal, TypedDict

from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.popular_scan_setting import PopularScanSetting
from app.db.query import popular_scan_setting as popular_scan_setting_query


DEFAULT_REGION_CODES = ["US"]
DEFAULT_MAX_RESULTS = 10
MAX_ALLOWED_RESULTS = 50
_SCAN_CONTROL_COLUMNS = {
    "youtube_scan_enabled", "popular_scan_enabled", "niche_scan_enabled"
}
_MISSING_SCAN_CONTROL_COLUMN = re.compile(
    r'\bcolumn\s+(?:"?popular_scan_settings"?\.)?'
    r'"?(youtube_scan_enabled|popular_scan_enabled|niche_scan_enabled)"?'
    r'(?:\s+of\s+relation\s+"?popular_scan_settings"?)?\s+does not exist\b',
    re.IGNORECASE,
)


class PopularScanSettings(TypedDict):
    region_codes: list[str]
    available_regions: list[dict[str, str]]
    max_results: int
    youtube_scan_enabled: bool
    popular_scan_enabled: bool
    niche_scan_enabled: bool


class YouTubeScanDisabledError(Exception):
    pass


class YouTubeScanMigrationRequiredError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Apply the YouTube scan controls database migration "
            "(011_youtube_scan_controls.sql or c03_youtube_scan_controls), "
            "then reload."
        )


def _is_missing_scan_controls(error: ProgrammingError) -> bool:
    original = error.orig
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate != "42703":
        return False

    diagnostic = getattr(original, "diag", None)
    table_name = getattr(diagnostic, "table_name", None)
    if (
        getattr(diagnostic, "column_name", None) in _SCAN_CONTROL_COLUMNS
        and table_name in (None, "", "popular_scan_settings")
    ):
        return True

    # Inspect the driver's diagnosis only. SQLAlchemy's full error also contains
    # the SELECT statement, which always mentions these columns even when a
    # different column is missing.
    diagnosis = str(original).partition("\n")[0]
    return _MISSING_SCAN_CONTROL_COLUMN.search(diagnosis) is not None


async def _get_popular_scan_setting(db: AsyncSession) -> PopularScanSetting | None:
    try:
        return await popular_scan_setting_query.get_popular_scan_setting(db)
    except ProgrammingError as error:
        if not _is_missing_scan_controls(error):
            raise
        await db.rollback()
        raise YouTubeScanMigrationRequiredError() from error


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
) -> PopularScanSettings:
    setting = await _get_popular_scan_setting(db)
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
        "youtube_scan_enabled": setting.youtube_scan_enabled,
        "popular_scan_enabled": setting.popular_scan_enabled,
        "niche_scan_enabled": setting.niche_scan_enabled,
    }


async def save_popular_scan_settings(
    db: AsyncSession,
    *,
    region_codes: list[str],
    max_results: int,
    youtube_scan_enabled: bool | None = None,
    popular_scan_enabled: bool | None = None,
    niche_scan_enabled: bool | None = None,
) -> PopularScanSettings:
    normalized_regions = normalize_region_codes(region_codes)
    if not normalized_regions:
        raise ValueError("Select at least one region.")

    normalized_max_results = normalize_max_results(max_results)
    setting = await _get_popular_scan_setting(db)
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
            youtube_scan_enabled=(
                True if youtube_scan_enabled is None else youtube_scan_enabled
            ),
            popular_scan_enabled=(
                True if popular_scan_enabled is None else popular_scan_enabled
            ),
            niche_scan_enabled=(
                True if niche_scan_enabled is None else niche_scan_enabled
            ),
        )
    else:
        setting = await popular_scan_setting_query.update_popular_scan_setting(
            db,
            setting,
            region_codes=normalized_regions,
            available_regions=current_available_regions,
            max_results=normalized_max_results,
            youtube_scan_enabled=youtube_scan_enabled,
            popular_scan_enabled=popular_scan_enabled,
            niche_scan_enabled=niche_scan_enabled,
        )

    return {
        "region_codes": list(setting.region_codes or normalized_regions),
        "available_regions": list(setting.available_regions or current_available_regions),
        "max_results": setting.max_results,
        "youtube_scan_enabled": setting.youtube_scan_enabled,
        "popular_scan_enabled": setting.popular_scan_enabled,
        "niche_scan_enabled": setting.niche_scan_enabled,
    }


async def save_popular_scan_regions(
    db: AsyncSession,
    *,
    available_regions: list[dict[str, str]],
) -> list[dict[str, str]]:
    normalized_regions = normalize_available_regions(available_regions)
    setting = await _get_popular_scan_setting(db)

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


async def ensure_youtube_scan_enabled(
    db: AsyncSession,
    scan_type: Literal["popular", "niche"],
) -> None:
    settings = await get_or_create_popular_scan_settings(db)
    if not settings["youtube_scan_enabled"]:
        raise YouTubeScanDisabledError(
            "All YouTube video scanning is disabled in admin settings."
        )
    if scan_type == "popular" and not settings["popular_scan_enabled"]:
        raise YouTubeScanDisabledError(
            "YouTube popular scanning is disabled in admin settings."
        )
    if scan_type == "niche" and not settings["niche_scan_enabled"]:
        raise YouTubeScanDisabledError(
            "YouTube niche scanning is disabled in admin settings."
        )
