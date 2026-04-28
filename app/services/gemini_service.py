import os
import json
import re
from typing import Dict, List

from google import genai
from dotenv import load_dotenv

load_dotenv()


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
        return await self._to_thread(
            self.client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
        )

    async def _to_thread(self, fn, /, *args, **kwargs):
        import asyncio

        return await asyncio.to_thread(fn, *args, **kwargs)

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
