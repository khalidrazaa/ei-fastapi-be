from datetime import date

from fastapi import Query

from app.db.query.yt_video_query import PublishedAge


def _split_query_values(values: list[str] | None) -> list[str] | None:
    """Support repeated parameters and comma-separated values."""
    if not values:
        return None
    normalized = [item.strip() for value in values for item in value.split(",")]
    return [item for item in normalized if item] or None


def video_list_filters(
    min_views: int = Query(0, ge=0),
    published_age: PublishedAge | None = None,
    published_from: date | None = Query(None),
    published_to: date | None = Query(None),
    trend_stage: list[str] | None = Query(None),
    region_code: list[str] | None = Query(None),
    source: list[str] | None = Query(None),
    category_title: list[str] | None = Query(None),
    min_score: float | None = Query(None, ge=0),
    min_speed_score: float | None = Query(None, ge=0),
    min_breakout_score: float | None = Query(None, ge=0),
    min_engagement_score: float | None = Query(None, ge=0),
    min_confidence_score: float | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    return dict(
        min_views=min_views,
        published_age=published_age,
        published_from=published_from,
        published_to=published_to,
        trend_stages=_split_query_values(trend_stage),
        region_codes=_split_query_values(region_code),
        sources=_split_query_values(source),
        category_titles=_split_query_values(category_title),
        min_score=min_score,
        min_speed_score=min_speed_score,
        min_breakout_score=min_breakout_score,
        min_engagement_score=min_engagement_score,
        min_confidence_score=min_confidence_score,
        page=page,
        size=size,
    )
