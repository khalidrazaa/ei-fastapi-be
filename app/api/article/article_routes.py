from typing import Annotated

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.core.admin_security import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.schemas.article import (
    AdminArticlePage,
    ArticleBulkDeleteRequest,
    ArticleDeleteResponse,
    ArticleDraftCreate,
    ArticleResponse,
    ArticleUpdate,
)
from app.services import article_media_service, article_service

router = APIRouter(dependencies=[Depends(require_admin)])
logger = logging.getLogger(__name__)
IMPORT_BODY = {"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
    "type": "object", "required": ["article", "request_id"], "properties": {
        "article": {"type": "string", "description": "Reviewed article JSON"},
        "request_id": {"type": "string", "format": "uuid"},
        "manifest": {"type": "string", "default": "{}"},
        "images": {"type": "array", "items": {"type": "string", "format": "binary"}},
    },
}}}}}


async def _import_article(article_json, manifest_json, request_id, images, admin, db, article_id=None):
    try:
        if len(article_json.encode("utf-8")) > 3 * 1024 * 1024 or len(manifest_json.encode("utf-8")) > 65536:
            raise ValueError("Article metadata or image manifest is too large.")
        schema = ArticleDraftCreate if article_id is None else ArticleUpdate
        payload = schema.model_validate_json(article_json)
        manifest = TypeAdapter(dict[str, str]).validate_json(manifest_json)
        return await article_media_service.import_article(db,
            payload=payload.model_dump(exclude_unset=article_id is not None),
            manifest=manifest, request_id=request_id, images=images or [],
            admin_id=str(admin.id), article_id=article_id,
            metadata_bytes=len(article_json.encode("utf-8")) + len(manifest_json.encode("utf-8")) + len(request_id.encode("utf-8")))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json(include_input=False))) from exc
    except article_media_service.ImportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except article_media_service.ArticleMediaMigrationRequiredError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Cache-Control": "no-store"}) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Article media storage is unavailable")
        raise HTTPException(status_code=503, detail="Article image storage is unavailable. Retry the same save.") from exc


async def _read_import_form(request, admin, db, article_id=None):
    # Explicit parsing avoids Starlette's default 1 MiB text-part limit and runs
    # only after authentication. The context also closes rejected upload parts.
    async with request.form(max_files=settings.MEDIA_MAX_IMAGES, max_fields=3,
                            max_part_size=3 * 1024 * 1024) as form:
        if set(form) - {"article", "manifest", "request_id", "images"}:
            raise HTTPException(status_code=422, detail="Unexpected article import form field.")
        for name in ("article", "request_id"):
            if len(form.getlist(name)) != 1 or not isinstance(form[name], str):
                raise HTTPException(status_code=422, detail=f"Provide one {name} form field.")
        if len(form.getlist("manifest")) > 1 or not isinstance(form.get("manifest", "{}"), str):
            raise HTTPException(status_code=422, detail="Provide one manifest JSON form field.")
        images = form.getlist("images")
        if any(not isinstance(upload, UploadFile) for upload in images):
            raise HTTPException(status_code=422, detail="images must contain uploaded files.")
        return await _import_article(form["article"], form.get("manifest", "{}"),
            form["request_id"], images, admin, db, article_id)


@router.post("/import", response_model=ArticleResponse, status_code=201, openapi_extra=IMPORT_BODY)
async def import_article_route(
    request: Request,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _read_import_form(request, admin, db)


@router.put("/{article_id}/import", response_model=ArticleResponse, openapi_extra=IMPORT_BODY)
async def update_article_import_route(
    article_id: Annotated[int, Path(gt=0)],
    request: Request,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _read_import_form(request, admin, db, article_id)


@router.post("", response_model=ArticleResponse, status_code=201)
async def create_article_route(
    payload: ArticleDraftCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.create_draft(db, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/bulk-delete",
    response_model=ArticleDeleteResponse,
    dependencies=[Depends(require_admin)],
)
async def delete_articles_route(
    payload: ArticleBulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.delete_articles(db, payload.article_ids)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{article_id}",
    response_model=ArticleDeleteResponse,
    dependencies=[Depends(require_admin)],
)
async def delete_article_route(
    article_id: Annotated[int, Path(gt=0)],
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.delete_articles(db, [article_id])
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=AdminArticlePage | list[ArticleResponse])
async def list_articles_route(
    status: str | None = Query(
        default=None, description="Filter articles by draft or published status."
    ),
    page: int | None = Query(default=None, ge=1),
    size: int | None = Query(default=None, ge=1, le=100),
    category: str | None = Query(default=None, max_length=200),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500, deprecated=True),
    db: AsyncSession = Depends(get_db),
):
    try:
        if page is not None or size is not None or category is not None or search is not None:
            return await article_service.list_article_page(
                db, status=status, category=category, search=search,
                page=page if page is not None else 1,
                size=size if size is not None else 20,
            )
        return await article_service.list_articles(db, status=status, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/categories", response_model=list[str])
async def list_article_categories_route(db: AsyncSession = Depends(get_db)):
    return await article_service.list_article_categories(db)


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article_route(
    article_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.get_article(db, article_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{article_id}", response_model=ArticleResponse)
async def update_article_route(
    article_id: int,
    payload: ArticleUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await article_service.update_article(
            db,
            article_id,
            payload.model_dump(exclude_unset=True),
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


