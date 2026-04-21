import asyncio
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi


class YouTubeTranscriptService:
    DEFAULT_LANGUAGES = ("en", "en-US", "en-GB")

    def __init__(self):
        self.client = YouTubeTranscriptApi()

    async def fetch_transcript(
        self,
        video_id: str,
        preferred_languages: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        transcript = await self._get_best_transcript(
            video_id,
            preferred_languages or self.DEFAULT_LANGUAGES,
        )
        transcript_text = self._flatten_transcript(transcript)

        if not transcript_text:
            raise ValueError("Transcript was fetched but returned no readable text.")

        return {
            "transcript_text": transcript_text,
            "transcript_language_code": getattr(transcript, "language_code", None),
            "transcript_language": getattr(transcript, "language", None),
            "transcript_source": (
                "asr" if getattr(transcript, "is_generated", False) else "manual"
            ),
        }

    async def _get_best_transcript(
        self,
        video_id: str,
        preferred_languages: tuple[str, ...],
    ):
        transcript_list = await asyncio.to_thread(self.client.list, video_id)

        try:
            transcript = await asyncio.to_thread(
                transcript_list.find_transcript,
                list(preferred_languages),
            )
        except Exception:
            transcript = next(iter(transcript_list), None)

        if transcript is None:
            raise ValueError("No transcript tracks available for this video.")

        return await asyncio.to_thread(transcript.fetch)

    def _flatten_transcript(self, transcript_data: Any) -> str:
        parts: list[str] = []

        for snippet in transcript_data:
            text = getattr(snippet, "text", None)
            if text is None and isinstance(snippet, dict):
                text = snippet.get("text")

            normalized = " ".join(str(text or "").split()).strip()
            if normalized:
                parts.append(normalized)

        return " ".join(parts).strip()
