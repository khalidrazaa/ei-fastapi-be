from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.niche import NicheKeyword
from app.db.models.trend_video import TrendVideo
from app.db.query_builder import QueryBuilder

SORT_FIELD_MAP = {
    "score": TrendVideo.virality_score,
    "trending": TrendVideo.trending_score,
    "breakout": TrendVideo.breakout_score,
    "emerging": TrendVideo.emerging_score,
    "sustained_demand": TrendVideo.sustained_demand_score,
    "watchlist": TrendVideo.watchlist_score,
    "vph": TrendVideo.views_per_hour,
    "breakout_score": TrendVideo.breakout_score,
    "engagement": TrendVideo.engagement_score,
    "views": TrendVideo.view_count,
    "recent": TrendVideo.created_at,
    "region": TrendVideo.region_code,
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

    base_query = (
        qb.join((NicheKeyword, TrendVideo.keyword_id == NicheKeyword.id))
        .filter(
            NicheKeyword.niche_id == niche_id,
            TrendVideo.view_count >= min_views if min_views else None,
        )
        .build()
    )

    # ✅ Deduplicate using window function
    deduped_query = deduplicate_videos(base_query)

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

    deduped_query = deduped_query.order_by(*order_by_clause)

    # ✅ Apply sorting + pagination
    final_query = select(TrendVideo).from_statement(
        deduped_query.order_by(
            *[
                getattr(TrendVideo, f.lstrip("-")).desc()
                if f.startswith("-")
                else getattr(TrendVideo, f).asc()
                for f in sort
            ]
        )
        .offset((page - 1) * size)
        .limit(size)
    )

    result = await db.execute(final_query)
    items = result.scalars().all()

    return items


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
