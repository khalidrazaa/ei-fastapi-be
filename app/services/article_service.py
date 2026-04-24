import math
from datetime import datetime, timezone
from typing import Any

from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trend_video import TrendVideo
from app.db.query import article as article_query
from app.services.gemini_service import GeminiClient


DEFAULT_HOST_SITE = "explainit.tech"


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


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
        raise ValueError("Gemini did not return article content.")

    title = str(payload.get("title") or video.title).strip() or video.title
    excerpt = str(payload.get("excerpt") or "").strip() or _fallback_excerpt(content)
    meta_description = (
        str(payload.get("meta_description") or "").strip() or excerpt[:160]
    )

    youtube_url = f"https://www.youtube.com/watch?v={video.youtube_video_id}"

    return {
        "title": title,
        "seo_title": str(payload.get("seo_title") or title).strip() or title,
        "content": content,
        "excerpt": excerpt,
        "meta_description": meta_description[:160],
        "category": str(payload.get("category") or video.category_title or "YouTube").strip()
        or "YouTube",
        "subcategory": str(payload.get("subcategory") or video.channel_title).strip() or None,
        "tags": _normalize_list(payload.get("tags")),
        "keywords": _normalize_list(payload.get("keywords")),
        "language": str(payload.get("language") or "en").strip() or "en",
        "canonical_url": str(payload.get("canonical_url") or youtube_url).strip(),
        "schema_type": str(payload.get("schema_type") or "Article").strip() or "Article",
        "open_graph_title": str(payload.get("open_graph_title") or title).strip() or title,
        "open_graph_description": (
            str(payload.get("open_graph_description") or meta_description).strip()
            or meta_description
        )[:200],
    }


async def generate_draft_from_video_transcript(
    db: AsyncSession,
    video: TrendVideo,
) -> object:
    if not video.transcript_text:
        raise ValueError("Transcript is not available for this video.")

    gemini = GeminiClient()
    payload = await gemini.generate_article_from_transcript(
        video_title=video.title,
        channel_title=video.channel_title,
        category_title=video.category_title,
        youtube_url=f"https://www.youtube.com/watch?v={video.youtube_video_id}",
        description=video.description,
        transcript_language=video.transcript_language,
        transcript_text=video.transcript_text,
    )

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
        host_site=DEFAULT_HOST_SITE,
        status="draft",
        language=article_fields["language"],
        drafted_at=now,
        meta_description=article_fields["meta_description"],
        keywords=article_fields["keywords"],
        canonical_url=article_fields["canonical_url"],
        schema_type=article_fields["schema_type"],
        open_graph_title=article_fields["open_graph_title"],
        open_graph_description=article_fields["open_graph_description"],
        open_graph_image=video.thumbnail_url,
        featured_image_url=video.thumbnail_url,
        image_alt_text=video.title,
        is_featured=False,
    )
