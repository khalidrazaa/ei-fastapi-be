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
    qb = QueryBuilder(TrendVideo)

    qb.join(
        NicheKeyword,
        TrendVideo.keyword_id == NicheKeyword.id,
    )

    qb.filter(
        NicheKeyword.niche_id == niche_id,
        TrendVideo.view_count >= min_views if min_views else None,
    )

    # ✅ Build query
    base_query = (
        QueryBuilder(TrendVideo)
        .join(NicheKeyword, TrendVideo.keyword_id == NicheKeyword.id)
        .filter(
            NicheKeyword.niche_id == niche_id,
            TrendVideo.view_count >= min_views if min_views else None,
        )
        .build()
    )

    # ✅ Deduplicate using window function
    deduped_query, video_columns = deduplicate_videos(base_query)

    if isinstance(sort, str):
        sort = sort.split(",")

    order_by_clause = []

    for f in sort:
        desc = f.startswith("-")
        key = f.lstrip("-")

        col = SORT_FIELD_MAP.get(key)

        if not col:
            raise ValueError(f"Unknown sort field: {key}")

        order_by_clause.append(col.desc() if desc else col.asc())

    final_query = (
        deduped_query.order_by(*order_by_clause).limit(size).offset((page - 1) * size)
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
        .label("rank")
    ).cte("ranked_videos")

    return select(ranked).where(ranked.c.rank == 1)
