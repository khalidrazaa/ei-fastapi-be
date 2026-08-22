import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate_query(
    db: AsyncSession,
    query,
    page: int,
    size: int,
):
    # Count rows produced by the query
    count_query = select(func.count()).select_from(query.order_by(None).subquery())

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Apply pagination
    paginated_query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(paginated_query)
    items = result.scalars().all()

    total_pages = math.ceil(total / size) if total else 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }
