import os
from google import genai
from typing import List, Dict
import json
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

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        try:
            categories = json.loads(response.text.strip())
            # Ensure order matches input trends
            results = [{"category": c.get("category"), "subcategory": c.get("subcategory")} for c in categories]
            return results
        except Exception:
            # Fallback: return None for all trends
            return [{"category": None, "subcategory": None} for _ in trends]