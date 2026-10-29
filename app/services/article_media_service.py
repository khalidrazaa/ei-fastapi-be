"""Save one reviewed Markdown/image batch on the VPS and in PostgreSQL."""

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.query import article as article_query
from app.db.query import article_image as image_query
from app.schemas.article import ArticleResponse
from app.services import article_service
from app.services.article_image_validation import validate_png, validate_svg
from app.services.article_markdown_images import resolve_images, rewrite_images

logger = logging.getLogger(__name__)
STORAGE_NAME = re.compile(r"^[0-9a-f]{32}\.(?:svg|png)$")


class ImportConflict(ValueError):
    pass


def media_root() -> Path:
    return Path(settings.MEDIA_ROOT).expanduser().resolve()


def _public_base() -> str:
    base = settings.MEDIA_PUBLIC_BASE_URL.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.path.endswith("/v1"):
        raise ValueError("Configure MEDIA_PUBLIC_BASE_URL as the public API URL including /v1 before uploading images.")
    return base


def _write_file(path: Path, data: bytes) -> None:
    with path.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


async def _stage_images(images: list[UploadFile], stage: Path, *, metadata_bytes: int):
    if len(images) > settings.MEDIA_MAX_IMAGES:
        raise ValueError(f"Choose at most {settings.MEDIA_MAX_IMAGES} diagram images.")
    prepared, names, total = [], set(), metadata_bytes
    if total > settings.MEDIA_MAX_BATCH_BYTES:
        raise ValueError("The article and images exceed the total upload limit.")
    if images:
        await asyncio.to_thread(stage.mkdir, parents=True, exist_ok=False)
    for upload in images:
        name = upload.filename or ""
        if not name or len(name) > 255 or Path(name).name != name or any(char in name for char in "\\/\0") or name in names:
            raise ValueError("Each selected image must have a unique filename without a folder path.")
        suffix = Path(name).suffix.lower()
        if suffix not in {".svg", ".png"}:
            raise ValueError("Diagram images must be SVG or PNG files.")
        names.add(name)
        data = await upload.read(settings.MEDIA_MAX_IMAGE_BYTES + 1)
        if not data or len(data) > settings.MEDIA_MAX_IMAGE_BYTES:
            raise ValueError(f"Each diagram must be nonempty and no larger than {settings.MEDIA_MAX_IMAGE_BYTES // (1024 * 1024)} MiB.")
        total += len(data)
        if total > settings.MEDIA_MAX_BATCH_BYTES:
            raise ValueError("The article and images exceed the total upload limit.")
        validator = validate_svg if suffix == ".svg" else validate_png
        try:
            sanitized = await asyncio.to_thread(validator, data, settings.MEDIA_MAX_PIXELS)
        except ValueError as exc:
            raise ValueError(f"{name}: {exc}") from exc
        identifier = uuid4().hex
        storage_name = identifier + suffix
        await asyncio.to_thread(_write_file, stage / storage_name, sanitized)
        prepared.append({
            "id": str(UUID(identifier)), "storage_name": storage_name,
            "original_filename": name, "mime_type": "image/svg+xml" if suffix == ".svg" else "image/png",
            "byte_size": len(sanitized), "sha256": hashlib.sha256(sanitized).hexdigest(),
            "input_sha256": hashlib.sha256(data).hexdigest(),
        })
    return prepared


def _replay(receipt, admin_id, target_id, digest):
    if receipt.admin_id != admin_id or receipt.target_article_id != target_id or receipt.payload_sha256 != digest:
        raise ImportConflict("This upload request ID was already used for different content. Start a new save.")
    if receipt.response is None:
        raise ImportConflict("This upload is still being saved. Retry the same request shortly.")
    return ArticleResponse.model_validate(receipt.response)


async def import_article(db, *, payload: dict, manifest: dict[str, str], request_id: str,
                         images: list[UploadFile], admin_id: str, article_id: int | None = None,
                         metadata_bytes: int = 0):
    try:
        request_id = str(UUID(request_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("request_id must be a UUID.") from exc
    if len(str(payload.get("content") or "").encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("Article Markdown must be no larger than 2 MiB.")
    root = media_root()
    stage = root / ".staging" / uuid4().hex
    finalized = []
    try:
        prepared = await _stage_images(images, stage, metadata_bytes=metadata_bytes)
        filenames = [image["original_filename"] for image in prepared]
        # Updated articles may keep content unchanged when no files were selected.
        content = str(payload.get("content") or "")
        if article_id is not None and "content" not in payload and (images or manifest):
            raise ValueError("Include the reviewed Markdown when importing images.")
        text, resolved = resolve_images(content, filenames, manifest)
        fingerprint = {
            "article": payload, "manifest": manifest, "target": article_id,
            "images": sorted((image["original_filename"], image["input_sha256"]) for image in prepared),
        }
        digest = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
        receipt = await image_query.get_import(db, request_id)
        if receipt is not None:
            return _replay(receipt, admin_id, article_id, digest)
        try:
            # The unique request ID serializes concurrent retries before article mutation.
            receipt = await image_query.add_import(db, request_id=request_id, admin_id=admin_id,
                target_article_id=article_id, payload_sha256=digest)
        except IntegrityError:
            await db.rollback()
            receipt = await image_query.get_import(db, request_id)
            if receipt is not None:
                return _replay(receipt, admin_id, article_id, digest)
            raise
        base = _public_base() if prepared else ""
        if article_id is None:
            article = await article_service.create_draft(db, payload.copy(), commit=False)
            urls = {image["original_filename"]: f"{base}/media/articles/{article.id}/{image['storage_name']}" for image in prepared}
            rewritten = rewrite_images(text, resolved, urls)
            if prepared:
                article = await article_query.update_article(db, article, commit=False, content=rewritten)
        else:
            urls = {image["original_filename"]: f"{base}/media/articles/{article_id}/{image['storage_name']}" for image in prepared}
            next_payload = payload.copy()
            if "content" in payload:
                next_payload["content"] = rewrite_images(text, resolved, urls)
            article = await article_service.update_article(db, article_id, next_payload, commit=False)
        receipt.article_id = article.id
        if prepared:
            destination = root / "articles" / str(article.id)
            await asyncio.to_thread(destination.mkdir, parents=True, exist_ok=True)
            for image in prepared:
                values = {key: value for key, value in image.items() if key != "input_sha256"}
                await image_query.add_image(db, article_id=article.id, original_article_id=article.id, **values)
                final_path = destination / image["storage_name"]
                await asyncio.to_thread(os.replace, stage / image["storage_name"], final_path)
                finalized.append(final_path)
            await asyncio.to_thread(_sync_directory, destination)
            # Persist newly created article-directory entries as well as files.
            await asyncio.to_thread(_sync_directory, destination.parent)
            await asyncio.to_thread(_sync_directory, root)
        response = ArticleResponse.model_validate(article)
        receipt.response = response.model_dump(mode="json")
        await db.commit()
        return response
    except Exception:
        await db.rollback()
        if finalized:
            # A connection can fail after COMMIT reached PostgreSQL. Never remove
            # those files unless a new transaction confirms the receipt is absent.
            try:
                committed = await image_query.get_import(db, request_id)
            except Exception:
                logger.exception("Retaining import files until media reconciliation after uncertain commit")
            else:
                if committed is None:
                    for path in finalized:
                        await asyncio.to_thread(path.unlink, missing_ok=True)
        raise
    finally:
        if stage.exists():
            await asyncio.to_thread(shutil.rmtree, stage)
        for upload in images:
            await upload.close()


async def get_public_image(db, article_id: int, storage_name: str):
    if article_id <= 0 or not STORAGE_NAME.fullmatch(storage_name):
        raise LookupError("Image not found.")
    record = await image_query.get_image(db, article_id, storage_name)
    if record is None:
        raise LookupError("Image not found.")
    path = media_root() / "articles" / str(article_id) / storage_name
    if not path.is_file() or path.is_symlink():
        raise LookupError("Image not found.")
    return path, record.mime_type
