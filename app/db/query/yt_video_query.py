from datetime import datetime, timedelta, timezone
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


async def query_by_niche(
    db: AsyncSession,
    niche_id: int,
    min_views: int = 0,
    published_age: PublishedAge | None = None,
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
    published_from, published_before = published_date_range(published_age)
    normalized_region_codes = (
        [region_code.upper() for region_code in region_codes]
        if region_codes
        else None
    )
    base_query = (
        QueryBuilder(TrendVideo)
        .join(
            NicheKeyword,
            TrendVideo.keyword_id == NicheKeyword.id,
        )
        .join(Niche, NicheKeyword.niche_id == Niche.id)
        .filter(
            NicheKeyword.niche_id == niche_id,
            TrendVideo.view_count >= min_views if min_views else None,
            TrendVideo.published_at >= published_from if published_from else None,
            TrendVideo.published_at < published_before if published_before else None,
            TrendVideo.trend_stage.in_(trend_stages) if trend_stages else None,
            func.upper(Niche.region_code).in_(normalized_region_codes)
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
            order_by=TrendVideo.virality_score.desc(),
        )
        .label("rank"),
    ).cte("ranked_videos")

    return ranked
