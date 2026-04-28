import json
import re
from typing import Dict

from openai import AsyncOpenAI

from app.core.config import settings


class OpenAIClient:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not configured.")

        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_DRAFT_MODEL

    async def generate_article_from_transcript(
        self,
        *,
        prompt: str,
    ) -> Dict[str, object]:
        response = await self.client.responses.create(
            model=self.model,
            input=prompt,
        )
        text = (response.output_text or "").strip()

        try:
            return self._extract_json_object(text)
        except Exception as exc:
            raise ValueError("OpenAI returned an invalid article draft payload.") from exc

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
