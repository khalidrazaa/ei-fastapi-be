from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.niche import NicheKeyword
from app.db.models.trend_video import TrendVideo
from app.db.pagination import paginate_query
from app.db.query_builder import QueryBuilder

SORT_FIELD_MAP = {
    "score": TrendVideo.virality_score,
    "trend_stage": TrendVideo.trend_stage,
    "speed_score": TrendVideo.speed_score,
    "breakout_score": TrendVideo.breakout_score,
    "engagement": TrendVideo.engagement_score,
    "views": TrendVideo.view_count,
    "published_at": TrendVideo.published_at,
    "region": TrendVideo.region_code,
    "source": TrendVideo.source,
    "category_title": TrendVideo.category_title,
    "confidence_score": TrendVideo.confidence_score,
}


async def query_by_niche(
    db: AsyncSession,
    niche_id: int,
    sort: list[str],
    min_views: int = 0,
    days: int | None = None,
    page: int = 1,
    size: int = 20,
):
    # 1. Build base query
    base_query = (
        QueryBuilder(TrendVideo)
        .join(
            NicheKeyword,
            TrendVideo.keyword_id == NicheKeyword.id,
        )
        .filter(
            NicheKeyword.niche_id == niche_id,
            TrendVideo.view_count >= min_views if min_views else None,
        )
        .build()
    )

    # 2. Create ranked CTE
    ranked = deduplicate_videos(base_query)

    # 3. Build sorting
    if isinstance(sort, str):
        sort = sort.split(",")

    order_by_clause = []

    for f in sort:
        descending = f.startswith("-")
        key = f.lstrip("-")

        original_col = SORT_FIELD_MAP.get(key)

        if original_col is None:
            raise ValueError(f"Unknown sort field: {key}")

        # Sort using the CTE column, NOT TrendVideo.column
        col = ranked.c[original_col.name]

        order_by_clause.append(col.desc() if descending else col.asc())

    # 4. Select actual TrendVideo ORM objects
    final_query = (
        select(TrendVideo)
        .join(
            ranked,
            TrendVideo.id == ranked.c.id,
        )
        .where(
            ranked.c.rank == 1,
        )
        .order_by(*order_by_clause)
    )

    # 5. Pagination + total + metadata
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
