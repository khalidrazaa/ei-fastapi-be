import math
from datetime import datetime, timezone
from typing import Any

from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.article import Article
from app.db.models.trend_video import TrendVideo
from app.db.query import article as article_query
from app.services.gemini_service import GeminiClient
from app.services.openai_service import OpenAIClient


DEFAULT_HOST_SITE = "explainit.tech"


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None

    normalized = str(value).strip()
    return normalized or None


def _normalize_required_string(value: Any, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _normalize_status(value: Any, *, strict: bool = False) -> str:
    normalized = str(value or "draft").strip().lower()
    if normalized in {"draft", "published"}:
        return normalized
    if strict:
        raise ValueError("Status must be either `draft` or `published`.")
    return "draft"


def _normalize_slug(value: Any) -> str:
    raw_slug = _normalize_required_string(value, "Slug")
    slug_value = slugify(raw_slug)
    if not slug_value:
        raise ValueError("Slug is invalid.")
    return slug_value


def _normalize_host_site(value: Any) -> str:
    normalized = str(value or "").strip()
    return normalized or DEFAULT_HOST_SITE


def _normalize_host_for_lookup(value: Any) -> str:
    host = str(value or "").strip().lower()
    host = host.removeprefix("https://").removeprefix("http://")
    host = host.split("/", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    if not host:
        raise ValueError("Host site is required.")
    return host


def _host_matches(article_host: Any, expected_host: str) -> bool:
    try:
        normalized_article_host = _normalize_host_for_lookup(article_host)
    except ValueError:
        return False
    return normalized_article_host == expected_host


def _normalize_optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number.")

    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number.") from exc

    if normalized < 0:
        raise ValueError(f"{field_name} must be 0 or greater.")
    return normalized


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "featured"}
    return bool(value)


def _estimate_reading_time(content: str) -> int:
    words = len(content.split())
    return max(1, math.ceil(words / 200))


def _fallback_excerpt(content: str, limit: int = 220) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."


async def _build_unique_slug(db: AsyncSession, title: str) -> str:
    base_slug = slugify(title) or "video-transcript-article"
    candidate = base_slug
    suffix = 2

    while await article_query.get_article_by_slug(db, candidate):
        candidate = f"{base_slug}-{suffix}"
        suffix += 1

    return candidate


def _coerce_article_payload(payload: dict[str, Any], video: TrendVideo) -> dict[str, Any]:
    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("The AI provider did not return article content.")

    title = str(payload.get("title") or video.title).strip() or video.title
    excerpt = str(payload.get("excerpt") or "").strip() or _fallback_excerpt(content)
    meta_description = (
        str(payload.get("meta_description") or "").strip() or excerpt[:160]
    )

    is_manual = video.source == "MANUAL" or video.youtube_video_id.startswith("manual-")
    source_url = "" if is_manual else f"https://www.youtube.com/watch?v={video.youtube_video_id}"

    return {
        "title": title,
        "seo_title": str(payload.get("seo_title") or title).strip() or title,
        "content": content,
        "excerpt": excerpt,
        "meta_description": meta_description[:160],
        "category": str(payload.get("category") or video.category_title or "YouTube").strip()
        or "YouTube",
        "subcategory": _normalize_optional_string(
            payload.get("subcategory") or video.channel_title
        ),
        "tags": _normalize_list(payload.get("tags")),
        "keywords": _normalize_list(payload.get("keywords")),
        "host_site": _normalize_host_site(payload.get("host_site")),
        "status": _normalize_status(payload.get("status")),
        "language": str(payload.get("language") or "en").strip() or "en",
        "canonical_url": str(payload.get("canonical_url") or source_url).strip() or None,
        "schema_type": str(payload.get("schema_type") or "Article").strip() or "Article",
        "open_graph_title": str(payload.get("open_graph_title") or title).strip() or title,
        "open_graph_description": (
            str(payload.get("open_graph_description") or meta_description).strip()
            or meta_description
        )[:200],
        "open_graph_image": _normalize_optional_string(
            payload.get("open_graph_image") or video.thumbnail_url
        ),
        "featured_image_url": _normalize_optional_string(
            payload.get("featured_image_url") or video.thumbnail_url
        ),
        "image_alt_text": str(payload.get("image_alt_text") or video.title).strip()
        or video.title,
        "is_featured": _normalize_bool(payload.get("is_featured")),
    }


def _build_article_generation_prompt(
    *,
    video: TrendVideo,
    prompt: str | None = None,
    additional_context: str | None = None,
) -> str:
    custom_prompt = (prompt or "").strip()
    extra_context = (additional_context or "").strip()
    is_manual = video.source == "MANUAL" or video.youtube_video_id.startswith("manual-")
    source_label = "Manual transcript" if is_manual else "YouTube transcript"
    source_url = "" if is_manual else f"https://www.youtube.com/watch?v={video.youtube_video_id}"

    sections = [
        "You are an expert long-form editorial writer and SEO strategist.",
        f"Create a complete article draft from the {source_label.lower()} below.",
        "Ground the writing in the transcript. Do not invent facts that are not supported by the transcript or the video metadata.",
        "Return ONLY a JSON object with these keys:",
        "- title",
        "- seo_title",
        "- content",
        "- excerpt",
        "- meta_description",
        "- category",
        "- subcategory",
        "- tags",
        "- keywords",
        "- host_site",
        "- status",
        "- language",
        "- canonical_url",
        "- schema_type",
        "- open_graph_title",
        "- open_graph_description",
        "- open_graph_image",
        "- featured_image_url",
        "- image_alt_text",
        "- is_featured",
        "",
        "Requirements:",
        "- `content` must be markdown.",
        "- Use a strong headline, introduction, clear section headings, and a conclusion.",
        "- Make it read like a polished article, not like raw transcript notes.",
        "- Keep the article detailed and useful.",
        "- `tags` and `keywords` must be arrays of short strings.",
        "- `status` must be `draft` unless explicitly asked otherwise.",
        "- `host_site` should default to `explainit.tech`.",
        "- Keep `meta_description` concise and SEO-friendly.",
        "- `canonical_url` should be either the source YouTube URL or a clean site URL candidate if clearly appropriate.",
        "- `schema_type` should usually be `Article`.",
        "- `language` should usually be `en` unless the transcript clearly indicates a different language.",
        "- Image fields may be null if no suitable image URL is available.",
        "- `is_featured` must be a boolean.",
    ]

    if custom_prompt:
        sections.extend(["", "User prompt:", custom_prompt])

    if extra_context:
        sections.extend(["", "Additional input:", extra_context])

    sections.extend(
        [
            "",
            f"Source title: {video.title}",
            f"Source: {video.channel_title}",
            f"Category: {video.category_title or 'YouTube'}",
            f"Description: {video.description or 'N/A'}",
            f"Transcript language: {video.transcript_language or 'Unknown'}",
            "",
            "Transcript:",
            video.transcript_text or "",
        ]
    )

    if source_url:
        sections.insert(-5, f"Video URL: {source_url}")

    return "\n".join(sections).strip()


async def list_articles(
    db: AsyncSession,
    *,
    status: str | None = None,
    host_site: str | None = None,
    limit: int = 100,
) -> list[Article]:
    normalized_status = _normalize_status(status, strict=True) if status else None
    normalized_host = _normalize_host_for_lookup(host_site) if host_site else None
    return await article_query.list_articles(
        db,
        status=normalized_status,
        host_site=normalized_host,
        limit=limit,
    )


async def get_article(
    db: AsyncSession,
    article_id: int,
) -> Article:
    article = await article_query.get_article_by_id(db, article_id)
    if article is None:
        raise LookupError("Article not found.")
    return article


async def list_published_articles_for_host(
    db: AsyncSession,
    *,
    host_site: str,
    limit: int = 100,
) -> list[Article]:
    normalized_host = _normalize_host_for_lookup(host_site)
    return await article_query.list_articles(
        db,
        status="published",
        host_site=normalized_host,
        limit=limit,
    )


async def get_published_article_by_slug_for_host(
    db: AsyncSession,
    *,
    slug: str,
    host_site: str,
) -> Article:
    normalized_host = _normalize_host_for_lookup(host_site)
    article = await article_query.get_article_by_slug(db, slug)
    if article is None:
        raise LookupError("Article not found.")
    if article.status != "published":
        raise LookupError("Article not found.")
    if not _host_matches(article.host_site, normalized_host):
        raise LookupError("Article not found.")
    return article


def _normalize_article_update_payload(payload: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}

    if "title" in payload:
        updates["title"] = _normalize_required_string(payload["title"], "Title")
    if "seo_title" in payload:
        updates["seo_title"] = _normalize_optional_string(payload["seo_title"])
    if "slug" in payload:
        updates["slug"] = _normalize_slug(payload["slug"])
    if "category" in payload:
        updates["category"] = _normalize_optional_string(payload["category"])
    if "subcategory" in payload:
        updates["subcategory"] = _normalize_optional_string(payload["subcategory"])
    if "tags" in payload:
        updates["tags"] = _normalize_list(payload["tags"])
    if "keywords" in payload:
        updates["keywords"] = _normalize_list(payload["keywords"])
    if "status" in payload:
        updates["status"] = _normalize_status(payload["status"], strict=True)
    if "content" in payload:
        updates["content"] = _normalize_optional_string(payload["content"])
    if "excerpt" in payload:
        updates["excerpt"] = _normalize_optional_string(payload["excerpt"])
    if "reading_time" in payload:
        updates["reading_time"] = _normalize_optional_int(
            payload["reading_time"],
            "Reading time",
        )
    if "featured_image_url" in payload:
        updates["featured_image_url"] = _normalize_optional_string(
            payload["featured_image_url"]
        )
    if "image_alt_text" in payload:
        updates["image_alt_text"] = _normalize_optional_string(payload["image_alt_text"])
    if "language" in payload:
        updates["language"] = str(payload["language"] or "en").strip() or "en"
    if "host_site" in payload:
        updates["host_site"] = _normalize_host_site(payload["host_site"])
    if "is_featured" in payload:
        updates["is_featured"] = _normalize_bool(payload["is_featured"])
    if "drafted_at" in payload:
        updates["drafted_at"] = payload["drafted_at"]
    if "meta_description" in payload:
        updates["meta_description"] = _normalize_optional_string(payload["meta_description"])
    if "canonical_url" in payload:
        updates["canonical_url"] = _normalize_optional_string(payload["canonical_url"])
    if "schema_type" in payload:
        updates["schema_type"] = _normalize_optional_string(payload["schema_type"])
    if "open_graph_title" in payload:
        updates["open_graph_title"] = _normalize_optional_string(payload["open_graph_title"])
    if "open_graph_description" in payload:
        updates["open_graph_description"] = _normalize_optional_string(
            payload["open_graph_description"]
        )
    if "open_graph_image" in payload:
        updates["open_graph_image"] = _normalize_optional_string(payload["open_graph_image"])

    return updates


async def update_article(
    db: AsyncSession,
    article_id: int,
    payload: dict[str, Any],
) -> Article:
    article = await get_article(db, article_id)
    updates = _normalize_article_update_payload(payload)
    if not updates:
        return article

    next_slug = updates.get("slug")
    if next_slug:
        existing = await article_query.get_article_by_slug(db, next_slug)
        if existing and existing.id != article.id:
            raise ValueError("Slug is already in use.")

    if "content" in updates and "reading_time" not in updates:
        next_content = updates["content"]
        updates["reading_time"] = (
            _estimate_reading_time(next_content) if next_content else None
        )

    next_status = updates.get("status")
    now = datetime.now(timezone.utc)
    if next_status == "published" and "published_at" not in updates:
        updates["published_at"] = article.published_at or now
    if next_status == "draft" and "drafted_at" not in updates:
        updates["drafted_at"] = article.drafted_at or now

    return await article_query.update_article(db, article, **updates)


async def generate_draft_from_video_transcript(
    db: AsyncSession,
    video: TrendVideo,
    *,
    provider: str = "gemini",
    prompt: str | None = None,
    additional_context: str | None = None,
) -> object:
    if not video.transcript_text:
        raise ValueError("Transcript is not available for this video.")

    request_prompt = _build_article_generation_prompt(
        video=video,
        prompt=prompt,
        additional_context=additional_context,
    )

    if provider == "chatgpt":
        openai_client = OpenAIClient()
        payload = await openai_client.generate_article_from_transcript(
            prompt=request_prompt
        )
    else:
        gemini = GeminiClient()
        payload = await gemini.generate_article_from_transcript(prompt=request_prompt)

    article_fields = _coerce_article_payload(payload, video)
    title = article_fields["title"]
    slug = await _build_unique_slug(db, title)
    now = datetime.now(timezone.utc)

    return await article_query.create_article(
        db,
        title=title,
        seo_title=article_fields["seo_title"],
        slug=slug,
        content=article_fields["content"],
        excerpt=article_fields["excerpt"],
        reading_time=_estimate_reading_time(article_fields["content"]),
        category=article_fields["category"],
        subcategory=article_fields["subcategory"],
        tags=article_fields["tags"],
        host_site=article_fields["host_site"],
        status=article_fields["status"],
        language=article_fields["language"],
        drafted_at=now,
        meta_description=article_fields["meta_description"],
        keywords=article_fields["keywords"],
        canonical_url=article_fields["canonical_url"],
        schema_type=article_fields["schema_type"],
        open_graph_title=article_fields["open_graph_title"],
        open_graph_description=article_fields["open_graph_description"],
        open_graph_image=article_fields["open_graph_image"],
        featured_image_url=article_fields["featured_image_url"],
        image_alt_text=article_fields["image_alt_text"],
        is_featured=article_fields["is_featured"],
    )
