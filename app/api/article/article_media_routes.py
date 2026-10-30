"""Public, unguessable, immutable image URLs also used by static article builds."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.article_media_service import get_public_image
from app.services.article_media_schema import ArticleMediaMigrationRequiredError

router = APIRouter()


@router.get("/articles/{article_id}/{storage_name}")
async def article_image_route(
    article_id: Annotated[int, Path(gt=0)],
    storage_name: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        path, mime_type = await get_public_image(db, article_id, storage_name)
    except ArticleMediaMigrationRequiredError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Cache-Control": "no-store"}) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type=mime_type, headers={
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
        "Cross-Origin-Resource-Policy": "cross-origin",
        "Referrer-Policy": "no-referrer",
    })
