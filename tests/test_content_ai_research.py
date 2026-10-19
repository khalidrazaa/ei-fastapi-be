"""OpenAI retains returned claims without expanding its search source catalog."""

import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas.content_workflow import ResearchPackage
from app.services import content_ai

GROUND_SOURCE = "https://example.com/docs"
ANNOTATED_SOURCE = "https://example.com/reference"
UNMATCHED_SOURCE = "https://other.example.com/not-retrieved"
INPUTS = {
    "title": "Warehouse decision",
    "question": "When do managers need a warehouse?",
    "brief": {"source_urls": ["https://preferred.example.com"]},
}
CLAIMS = [
    {
        "claim": "A grounded finding",
        "source_urls": [GROUND_SOURCE],
        "evidence": "Provider research narrative",
        "qualification": "",
    },
    {
        "claim": "A claim with an unmatched reference",
        "source_urls": [UNMATCHED_SOURCE],
        "evidence": "Returned evidence for editorial review",
        "qualification": "Citation needs review",
    },
    {
        "claim": "A claim without a reference",
        "source_urls": [],
        "evidence": "Returned evidence without a source URL",
        "qualification": "Source needs review",
    },
]


class OpenAIResearchClaimsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.object(
            content_ai.settings, "OPENAI_API_KEY", "dummy-key"
        ))
        self.factory = self.enterContext(patch.object(content_ai, "AsyncOpenAI"))

    def ai(self, *, ready=True, claims=None, sources=True):
        search_data = {
            "action": {"sources": [
                {"url": GROUND_SOURCE, "title": "Docs"},
                {"url": "http://invalid.example.com", "title": "Invalid"},
            ] if sources else []},
        }
        annotation_data = {"content": [{"annotations": [
            {"url": ANNOTATED_SOURCE, "title": "Reference"},
        ] if sources else []}]}
        search = SimpleNamespace(
            id="search-response", model="fixture-model", usage=None,
            output_text="The provider research narrative.",
            output=[
                SimpleNamespace(model_dump=lambda: deepcopy(search_data)),
                SimpleNamespace(model_dump=lambda: deepcopy(annotation_data)),
            ],
        )
        ledger = ResearchPackage(
            ready=ready, summary="Research findings", gaps=[],
            claims=deepcopy(CLAIMS if claims is None else claims),
        )
        extraction = SimpleNamespace(
            id="ledger-response", model="fixture-model", usage=None,
            output_parsed=ledger,
        )
        client = SimpleNamespace(responses=SimpleNamespace(
            create=AsyncMock(return_value=search),
            parse=AsyncMock(return_value=extraction),
        ))
        self.factory.return_value = client
        return content_ai.ContentAI(), client

    async def test_mixed_claims_survive_without_becoming_grounded_sources(self):
        ai, client = self.ai()
        result = await ai.research(INPUTS)

        self.assertEqual(result["claims"], CLAIMS)
        self.assertTrue(result["ready"])
        self.assertEqual(
            {source["url"] for source in result["sources"]},
            {GROUND_SOURCE, ANNOTATED_SOURCE},
        )
        self.assertNotIn(UNMATCHED_SOURCE, {
            source["url"] for source in result["sources"]
        })
        self.assertEqual(result["research_text"], "The provider research narrative.")
        self.assertEqual(
            [usage["stage"] for usage in result["usage"]],
            ["search", "research_ledger"],
        )
        extraction = client.responses.parse.await_args.kwargs
        self.assertIs(extraction["text_format"], ResearchPackage)
        self.assertEqual(
            set(json.loads(extraction["input"])["allowed_sources"]),
            {GROUND_SOURCE, ANNOTATED_SOURCE},
        )
        client.responses.create.assert_awaited_once()
        client.responses.parse.assert_awaited_once()

    async def test_provider_not_ready_stays_false_with_retained_claims(self):
        ai, _ = self.ai(ready=False)
        result = await ai.research(INPUTS)

        self.assertFalse(result["ready"])
        self.assertEqual(result["claims"], CLAIMS)

    async def test_no_claims_remains_not_ready_even_when_provider_marks_ready(self):
        ai, _ = self.ai(ready=True, claims=[])
        result = await ai.research(INPUTS)

        self.assertFalse(result["ready"])
        self.assertEqual(result["claims"], [])
        self.assertEqual(len(result["sources"]), 2)

    async def test_no_grounded_search_sources_still_stops_before_extraction(self):
        ai, client = self.ai(sources=False)

        with self.assertRaisesRegex(ValueError, "no usable cited sources"):
            await ai.research(INPUTS)

        client.responses.parse.assert_not_awaited()
        client.responses.create.assert_awaited_once()
