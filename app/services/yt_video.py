from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query import yt_video as trend_video_query
from app.db.query.yt_video import get_videos_by_niche
from app.services.article_service import generate_draft_from_video_transcript


def _normalize_transcript_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


async def get_videos_by_niche(
    db: AsyncSession,
    niche_id: int,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
    page: int = 1,
    size: int = 20,
):
    skip = (page - 1) * size
    items, total = await trend_video_query.get_videos_by_niche(
        db=db,
        niche_id=niche_id,
        sort=sort,
        min_views=min_views,
        days=days,
        skip=skip,
        limit=size,
    )
    return await trend_video_query.get_videos_by_niche(
        db=db,
        niche_id=niche_id,
        sort=sort,
        min_views=min_views,
        days=days,
        skip=skip,
        limit=size,
    )


async def get_popular_videos(
    db: AsyncSession,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
    region_code: str | None = None,
    source: str | None = None,
):
    return await trend_video_query.get_popular_videos(
        db=db,
        sort=sort,
        min_views=min_views,
        days=days,
        region_code=region_code,
        source=source,
    )


async def get_videos_with_transcripts(
    db: AsyncSession,
) -> object:
    return await trend_video_query.get_videos_with_transcripts(db=db)


async def save_video_transcript(
    db: AsyncSession,
    trend_video_id: int,
    transcript_text: str,
) -> object:
    video = await trend_video_query.get_trend_video_by_id(db, trend_video_id)
    if not video:
        raise LookupError("Video not found.")

    normalized_text = _normalize_transcript_text(transcript_text)
    if not normalized_text:
        raise ValueError("Transcript text is required.")

    return await trend_video_query.update_transcript(
        db,
        video,
        transcript_text=normalized_text,
        transcript_language_code=video.transcript_language_code,
        transcript_language=video.transcript_language,
        transcript_source="manual",
        transcript_error=None,
    )


async def create_manual_transcript(
    db: AsyncSession,
    *,
    title: str,
    category_title: str,
    transcript_text: str,
) -> object:
    normalized_title = title.strip()
    normalized_category = category_title.strip()
    normalized_text = _normalize_transcript_text(transcript_text)

    if not normalized_title:
        raise ValueError("Title is required.")
    if not normalized_category:
        raise ValueError("Category is required.")
    if not normalized_text:
        raise ValueError("Transcript text is required.")

    return await trend_video_query.create_manual_transcript(
        db,
        title=normalized_title,
        category_title=normalized_category,
        transcript_text=normalized_text,
    )


async def get_video_transcript(
    db: AsyncSession,
    trend_video_id: int,
) -> dict[str, object]:
    video = await trend_video_query.get_trend_video_by_id(db, trend_video_id)
    if not video:
        raise LookupError("Video not found.")
    if not video.transcript_text:
        raise ValueError("Transcript is not available for this video.")

    return {
        "id": video.id,
        "title": video.title,
        "youtube_video_id": video.youtube_video_id,
        "transcript_text": video.transcript_text,
        "transcript_language": video.transcript_language,
        "transcript_source": video.transcript_source,
        "transcript_fetched_at": video.transcript_fetched_at,
    }


async def generate_article_draft_for_video(
    db: AsyncSession,
    trend_video_id: int,
    *,
    provider: str = "gemini",
    prompt: str | None = None,
    additional_context: str | None = None,
) -> object:
    video = await trend_video_query.get_trend_video_by_id(db, trend_video_id)
    if not video:
        raise LookupError("Video not found.")

    return await generate_draft_from_video_transcript(
        db,
        video,
        provider=provider,
        prompt=prompt,
        additional_context=additional_context,
    )
