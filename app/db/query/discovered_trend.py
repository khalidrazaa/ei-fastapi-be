from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.discovered_trend import DiscoveredTrend


async def upsert_trend(db: AsyncSession, data: dict):

    result = await db.execute(
        select(DiscoveredTrend)
        .where(DiscoveredTrend.phrase == data["phrase"])
    )

    existing = result.scalar_one_or_none()

    if existing:

        existing.score = data["score"]
        existing.burst_score = data["burst_score"]
        existing.video_count = data["count"]

    else:

        trend = DiscoveredTrend(
            phrase=data["phrase"],
            score=data["score"],
            burst_score=data["burst_score"],
            video_count=data["count"],
        )

        db.add(trend)

    await db.commit()