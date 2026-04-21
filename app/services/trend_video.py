from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query import trend_video as trend_video_query
from app.services.article_service import generate_draft_from_video_transcript
from app.services.youtube_transcript_service import YouTubeTranscriptService


async def get_videos_by_niche(
    db: AsyncSession,
    niche_id: int,
    sort: str = "score",
    min_views: int = 0,
    days: int | None = None,
):
    return await trend_video_query.get_videos_by_niche(
        db=db,
        niche_id=niche_id,
        sort=sort,
        min_views=min_views,
        days=days,
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


async def fetch_and_store_transcript(
    db: AsyncSession,
    trend_video_id: int,
) -> object:
    video = await trend_video_query.get_trend_video_by_id(db, trend_video_id)
    if not video:
        raise LookupError("Video not found.")

    transcript_service = YouTubeTranscriptService()

    try:
        transcript = await transcript_service.fetch_transcript(video.youtube_video_id)
    except Exception as exc:
        await trend_video_query.update_transcript(
            db,
            video,
            transcript_text=video.transcript_text,
            transcript_language_code=video.transcript_language_code,
            transcript_language=video.transcript_language,
            transcript_source=video.transcript_source,
            transcript_error=str(exc),
        )
        raise

    return await trend_video_query.update_transcript(
        db,
        video,
        transcript_text=transcript["transcript_text"],
        transcript_language_code=transcript.get("transcript_language_code"),
        transcript_language=transcript.get("transcript_language"),
        transcript_source=transcript.get("transcript_source"),
        transcript_error=None,
    )


async def get_video_transcript(
    db: AsyncSession,
    trend_video_id: int,
) -> dict[str, object]:
    video = await trend_video_query.get_trend_video_by_id(db, trend_video_id)
    if not video:
        raise LookupError("Video not found.")
    if not video.transcript_text:
        raise ValueError("Transcript not found. Fetch it first.")

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
) -> object:
    video = await trend_video_query.get_trend_video_by_id(db, trend_video_id)
    if not video:
        raise LookupError("Video not found.")

    return await generate_draft_from_video_transcript(db, video)
