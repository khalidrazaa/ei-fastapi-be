from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.niche import Niche, NicheKeyword
from app.db.models.trend_video import TrendVideo
from app.db.pagination import paginate_query
from app.db.query_builder import QueryBuilder

PublishedAge = Literal[
    "6h", "12h", "24h", "2d", "3d", "4d", "5d", "6d", "7d", "7d+"
]

PUBLISHED_AGE_DELTAS: dict[PublishedAge, timedelta] = {
    "6h": timedelta(hours=6),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "2d": timedelta(days=2),
    "3d": timedelta(days=3),
    "4d": timedelta(days=4),
    "5d": timedelta(days=5),
    "6d": timedelta(days=6),
    "7d": timedelta(days=7),
    "7d+": timedelta(days=7),
}


def published_date_range(
    published_age: PublishedAge | None,
    *,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Translate a published-age selection into inclusive/exclusive date bounds."""
    if published_age is None:
        return None, None

    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - PUBLISHED_AGE_DELTAS[published_age]

    if published_age == "7d+":
        return None, cutoff

    return cutoff, current_time


async def query_videos(
    db: AsyncSession,
    niche_id: int | None = None,
    min_views: int = 0,
    published_age: PublishedAge | None = None,
    published_from: date | None = None,
    published_to: date | None = None,
    trend_stages: list[str] | None = None,
    region_codes: list[str] | None = None,
    sources: list[str] | None = None,
    category_titles: list[str] | None = None,
    min_score: float | None = None,
    min_speed_score: float | None = None,
    min_breakout_score: float | None = None,
    min_engagement_score: float | None = None,
    min_confidence_score: float | None = None,
    page: int = 1,
    size: int = 20,
):
    """Build both video lists with shared filters and database pagination."""
    age_from, age_before = published_date_range(published_age)
    range_start, range_end = published_from, published_to
    if published_from and published_to:
        range_start, range_end = sorted((published_from, published_to))
    date_from = (
        datetime.combine(range_start, time.min, tzinfo=timezone.utc)
        if range_start
        else age_from
    )
    date_before = (
        datetime.combine(range_end + timedelta(days=1), time.min, tzinfo=timezone.utc)
        if range_end
        else age_before
    )
    normalized_region_codes = (
        [region_code.upper() for region_code in region_codes]
        if region_codes
        else None
    )
    builder = QueryBuilder(TrendVideo)
    region_column = TrendVideo.region_code
    if niche_id is not None:
        builder = builder.join(
            NicheKeyword, TrendVideo.keyword_id == NicheKeyword.id
        ).join(Niche, NicheKeyword.niche_id == Niche.id)
        region_column = Niche.region_code

    base_query = (
        builder
        .filter_date_range(TrendVideo.published_at, date_from, date_before)
        .filter(
            NicheKeyword.niche_id == niche_id if niche_id is not None else None,
            TrendVideo.view_count >= min_views if min_views else None,
            TrendVideo.trend_stage.in_(trend_stages) if trend_stages else None,
            func.upper(region_column).in_(normalized_region_codes)
            if normalized_region_codes
            else None,
            TrendVideo.source.in_(sources) if sources else None,
            (
                TrendVideo.category_title.in_(category_titles)
                if category_titles
                else None
            ),
            TrendVideo.virality_score >= min_score if min_score is not None else None,
            TrendVideo.speed_score >= min_speed_score
            if min_speed_score is not None
            else None,
            TrendVideo.breakout_score >= min_breakout_score
            if min_breakout_score is not None
            else None,
            TrendVideo.engagement_score >= min_engagement_score
            if min_engagement_score is not None
            else None,
            TrendVideo.confidence_score >= min_confidence_score
            if min_confidence_score is not None
            else None,
        )
        .build()
    )

    ranked = deduplicate_videos(base_query)
    final_query = (
        select(TrendVideo)
        .join(
            ranked,
            TrendVideo.id == ranked.c.id,
        )
        .where(
            ranked.c.rank == 1,
        )
        .order_by(ranked.c.virality_score.desc(), ranked.c.id.desc())
    )

    return await paginate_query(
        db=db,
        query=final_query,
        page=page,
        size=size,
    )


def deduplicate_videos(base_query):
    ranked = base_query.add_columns(
        func.row_number()
        .over(
            partition_by=TrendVideo.youtube_video_id,
            order_by=(TrendVideo.virality_score.desc(), TrendVideo.id.desc()),
        )
        .label("rank"),
    ).cte("ranked_videos")

    return ranked
