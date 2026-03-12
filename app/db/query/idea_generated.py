from sqlalchemy import delete, select, update
from app.db.models.idea_generated import TrendIdea


async def create_trend_idea(db, trend_id: int, title: str):

    # check if idea already exists
    result = await db.execute(
        select(TrendIdea).where(
            TrendIdea.trend_id == trend_id,
            TrendIdea.title == title
        )
    )

    existing = result.scalar_one_or_none()

    if existing:
        return existing.id

    idea = TrendIdea(
        trend_id=trend_id,
        title=title
    )

    db.add(idea)
    await db.commit()
    await db.refresh(idea)

    return idea.id

async def get_ideas_by_trend(db, trend_id: int):

    result = await db.execute(
        select(TrendIdea)
        .where(TrendIdea.trend_id == trend_id)
        .order_by(TrendIdea.created_at.desc())
    )

    return result.scalars().all()


async def delete_trend_idea(db, idea_id: int):

    await db.execute(
        delete(TrendIdea).where(
            TrendIdea.id == idea_id
        )
    )

    await db.commit()

    return 

async def delete_ideas_by_trend(db, trend_id: int):

    await db.execute(
        delete(TrendIdea).where(
            TrendIdea.trend_id == trend_id
        )
    )

    await db.commit()

    return True

async def select_trend_idea(db, trend_id: int, idea_id: int):

    # reset previous selections
    await db.execute(
        update(TrendIdea)
        .where(TrendIdea.trend_id == trend_id)
        .values(is_selected=False)
    )

    # select the new one
    await db.execute(
        update(TrendIdea)
        .where(TrendIdea.id == idea_id)
        .values(is_selected=True)
    )

    await db.commit()

    return True