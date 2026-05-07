import asyncio
import json
import logging
import os
import random
import re
from typing import Dict, List

from google import genai
from google.genai import errors as genai_errors
from dotenv import load_dotenv

from app.services.ai_exceptions import TemporaryProviderError

load_dotenv()

logger = logging.getLogger(__name__)

_MAX_TRANSIENT_RETRIES = 3
_BASE_BACKOFF_SECONDS = 1.0
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
_TRANSIENT_STATUS_NAMES = {
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "DEADLINE_EXCEEDED",
    "INTERNAL",
}


class GeminiClient:
    def __init__(self):
        # Uses GEMINI_API_KEY from environment
        self.client = genai.Client(api_key=os.getenv("GOOGLE_AI_STUDIO_API_KEY"))

    async def categorize_batch(
        self, trends: List[str], trend_breakdowns: List[str]
    ) -> List[Dict[str, str]]:
        """
        Categorize a batch of trends in a single API call.
        Returns a list of dicts: [{"category": "...", "subcategory": "..."}, ...]
        """
        # Build batch prompt
        prompt_lines = [
            "You are a trend classifier. Classify the following trends logically into category and subcategory. "
            "Return ONLY JSON array with objects like {'trend': '...', 'category': '...', 'subcategory': '...'}"
        ]
        for trend, breakdown in zip(trends, trend_breakdowns):
            prompt_lines.append(f"Trend: {trend}\nContext: {breakdown}")

        prompt = "\n\n".join(prompt_lines)

        response = await self._generate_content(prompt)

        try:
            categories = json.loads(response.text.strip())
            # Ensure order matches input trends
            results = [
                {"category": c.get("category"), "subcategory": c.get("subcategory")}
                for c in categories
            ]
            return results
        except Exception:
            # Fallback: return None for all trends
            return [{"category": None, "subcategory": None} for _ in trends]

    async def generate_article_from_transcript(
        self,
        *,
        prompt: str,
    ) -> Dict[str, object]:
        response = await self._generate_content(prompt)
        text = (response.text or "").strip()

        try:
            return self._extract_json_object(text)
        except Exception as exc:
            raise ValueError("Gemini returned an invalid article draft payload.") from exc

    async def _generate_content(self, prompt: str):
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_TRANSIENT_RETRIES + 1):
            try:
                return await self._to_thread(
                    self.client.models.generate_content,
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
            except Exception as exc:  # pragma: no cover - network/provider behavior
                if not self._is_transient_provider_error(exc):
                    raise

                last_exc = exc
                if attempt >= _MAX_TRANSIENT_RETRIES:
                    break

                delay = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                jitter = random.uniform(0.0, 0.35)
                wait_seconds = delay + jitter

                logger.warning(
                    "Transient Gemini error on attempt %s/%s; retrying in %.2fs: %s",
                    attempt,
                    _MAX_TRANSIENT_RETRIES,
                    wait_seconds,
                    exc,
                )
                await asyncio.sleep(wait_seconds)

        raise TemporaryProviderError(
            "Gemini is temporarily unavailable due to high demand. Please retry in a few moments."
        ) from last_exc

    async def _to_thread(self, fn, /, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    def _is_transient_provider_error(self, exc: Exception) -> bool:
        if isinstance(exc, genai_errors.ServerError):
            return True

        if isinstance(exc, genai_errors.ClientError):
            code = getattr(exc, "code", None)
            status = str(getattr(exc, "status", "") or "").upper()
            if code in _TRANSIENT_STATUS_CODES or status in _TRANSIENT_STATUS_NAMES:
                return True

        message = str(exc).upper()
        return "UNAVAILABLE" in message or "HIGH DEMAND" in message

    def _extract_json_object(self, text: str) -> Dict[str, object]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))
