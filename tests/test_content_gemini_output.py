"""Gemini HTTP-200 responses still require complete, valid, grounded output."""
import asyncio
import json
import unittest
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from google.genai import types

from app.schemas.content_workflow import ResearchPackage
from app.services import content_gemini
from app.services.content_gemini import GeminiContentAI


SOURCE = "https://example.com/docs"
INPUTS = {"title": "Warehouse", "question": "Need one?", "brief": {}}
LEDGER = {
    "ready": True, "summary": "Evidence", "gaps": [],
    "claims": [{
        "claim": "Reporting", "evidence": "Primary documentation",
        "qualification": "", "source_urls": [SOURCE],
    }],
}
PRIVATE_MARKERS = (
    "PRIVATE_PROVIDER_TEXT", "PRIVATE_FIELD_NAME", "PRIVATE_FIELD_VALUE",
    "PRIVATE_FINISH_DETAIL", "PRIVATE_BLOCK_DETAIL", "PRIVATE_THOUGHT",
)


def sdk_response(text=None, finish="STOP", *, sources=None, blocked=None,
                 thought=False):
    parts = []
    if thought:
        parts.append(types.Part(text="PRIVATE_THOUGHT", thought=True))
    if text is not None:
        parts.append(types.Part(text=text))
    grounding = None
    if sources is not None:
        grounding = types.GroundingMetadata(
            web_search_queries=["warehouse docs"],
            grounding_chunks=[
                types.GroundingChunk(
                    web=types.GroundingChunkWeb(uri=url, title="Docs")
                ) for url in sources
            ],
        )
    candidates = [] if blocked else [
        types.Candidate(
            content=types.Content(parts=parts), finish_reason=finish,
            finish_message="PRIVATE_FINISH_DETAIL", grounding_metadata=grounding,
        )
    ]
    feedback = None
    if blocked:
        feedback = types.GenerateContentResponsePromptFeedback(
            block_reason=blocked, block_reason_message="PRIVATE_BLOCK_DETAIL",
        )
    return types.GenerateContentResponse(
        candidates=candidates, prompt_feedback=feedback,
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=30, candidates_token_count=10,
            thoughts_token_count=500, total_token_count=540,
        ),
        model_version="fixture-model", response_id="fixture-response",
    )


def ledger_response(**options):
    return sdk_response(json.dumps(LEDGER), **options)


class GeminiOutputTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.object(
            content_gemini.settings, "CONTENT_GEMINI_MODEL", "gemini-2.5-flash"
        ))
        self.enterContext(patch.object(
            content_gemini.settings, "CONTENT_MAX_OUTPUT_TOKENS", 10000
        ))

    def ai(self, *responses):
        ai = GeminiContentAI.__new__(GeminiContentAI)
        ai.usage = []
        ai.client = NS(aio=NS(models=NS(
            generate_content=AsyncMock(side_effect=list(responses))
        )))
        return ai

    async def structured(self, ai, stage="research_ledger"):
        return await ai.structured(
            ResearchPackage, "Extract the evidence ledger.",
            {"research": "Supported research", "allowed_sources": [SOURCE]},
            stage,
        )

    def assert_no_private_diagnostics(self, *values):
        diagnostic = json.dumps(values, default=str)
        for marker in PRIVATE_MARKERS:
            self.assertNotIn(marker, diagnostic)

    async def test_grounded_research_retains_sources_and_usage(self):
        ai = self.ai(
            sdk_response("Supported research", sources=[SOURCE]), ledger_response()
        )
        result = await ai.research(deepcopy(INPUTS))
        self.assertTrue(result["ready"])
        self.assertEqual(result["sources"][0]["url"], SOURCE)
        self.assertEqual(result["claims"], LEDGER["claims"])
        self.assertEqual(result["search_queries"], ["warehouse docs"])
        self.assertEqual(
            [usage["stage"] for usage in result["usage"]],
            ["search", "research_ledger"],
        )
        self.assertTrue(all(u["provider"] == "gemini" for u in result["usage"]))
        search = ai.client.aio.models.generate_content.call_args_list[0].kwargs
        self.assertIn("google_search", search["config"]["tools"][0])

    async def test_rejects_ungrounded_research_without_requesting_a_ledger(self):
        ai = self.ai(sdk_response("Supported research", sources=[]))
        with self.assertRaisesRegex(ValueError, "(?i)(sources|ground)"):
            await ai.research(deepcopy(INPUTS))
        self.assertEqual(ai.client.aio.models.generate_content.await_count, 1)

    async def test_preserves_all_claims_after_strict_ledger_validation(self):
        ledger = deepcopy(LEDGER)
        original = ledger["claims"][0]
        ledger["claims"] = [
            {**original, "claim": "No citation", "source_urls": []},
            {**original, "claim": "Another source",
             "source_urls": ["https://invented.example/docs"]},
            {**original, "claim": "Mixed sources", "source_urls": [
                SOURCE, "https://other.example/source",
            ]},
        ]
        ai = self.ai(
            sdk_response("Supported research", sources=[SOURCE]),
            sdk_response(json.dumps(ledger)),
        )
        result = await ai.research(deepcopy(INPUTS))
        self.assertTrue(result["ready"])
        self.assertEqual(result["claims"], ledger["claims"])
        self.assertEqual([source["url"] for source in result["sources"]], [SOURCE])
        self.assertEqual(ai.client.aio.models.generate_content.await_count, 2)

    async def test_readiness_still_requires_provider_approval_and_nonempty_claims(self):
        for ready, claims in ((False, LEDGER["claims"]), (True, [])):
            with self.subTest(provider_ready=ready, claim_count=len(claims)):
                ledger = {**deepcopy(LEDGER), "ready": ready, "claims": claims}
                ai = self.ai(
                    sdk_response("Supported research", sources=[SOURCE]),
                    sdk_response(json.dumps(ledger)),
                )
                result = await ai.research(deepcopy(INPUTS))
                self.assertFalse(result["ready"])
                self.assertEqual(result["claims"], claims)
                self.assertEqual(
                    [source["url"] for source in result["sources"]], [SOURCE]
                )

    async def test_real_sdk_response_ignores_thought_parts_and_validates_json(self):
        ai = self.ai(ledger_response(thought=True))
        self.assertEqual(await self.structured(ai), LEDGER)
        self.assertEqual(ai.client.aio.models.generate_content.await_count, 1)
        config = ai.client.aio.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config["response_mime_type"], "application/json")
        self.assertEqual(
            config["response_json_schema"], ResearchPackage.model_json_schema()
        )
        self.assertEqual(config["max_output_tokens"], 10000)
        self.assert_no_private_diagnostics(ai.usage)

    async def test_unspecified_finish_reason_remains_compatible(self):
        ai = self.ai(ledger_response(finish=None))
        self.assertEqual(await self.structured(ai), LEDGER)

    async def test_legacy_mock_responses_without_metadata_remain_compatible(self):
        response = NS(
            text=json.dumps(LEDGER), usage_metadata=None, candidates=[NS()]
        )
        ai = self.ai(response)
        self.assertEqual(await self.structured(ai), LEDGER)

    async def test_recoverable_structured_failures_retry_once_from_original_data(self):
        bad_responses = {
            "empty": sdk_response(),
            "no-candidates": types.GenerateContentResponse(),
            "malformed": sdk_response('{"PRIVATE_PROVIDER_TEXT":'),
            "wrong-schema": sdk_response('{"ready":true,"claims":"wrong"}'),
            "extra-field": sdk_response(json.dumps({
                **LEDGER, "PRIVATE_FIELD_NAME": "PRIVATE_FIELD_VALUE",
            })),
            "truncated": sdk_response(
                '{"PRIVATE_PROVIDER_TEXT":', finish="MAX_TOKENS"
            ),
            "thought-only": sdk_response(finish="MAX_TOKENS", thought=True),
        }
        for category, bad in bad_responses.items():
            with self.subTest(category=category):
                ai = self.ai(bad, ledger_response())
                with self.assertLogs(
                    "app.services.content_gemini", level="INFO"
                ) as logs:
                    self.assertEqual(await self.structured(ai), LEDGER)
                calls = ai.client.aio.models.generate_content.call_args_list
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0].kwargs["contents"],
                                 calls[1].kwargs["contents"])
                self.assertEqual(calls[0].kwargs["config"]["max_output_tokens"],
                                 calls[1].kwargs["config"]["max_output_tokens"])
                for call in calls:
                    self.assertEqual(
                        call.kwargs["config"]["response_json_schema"],
                        ResearchPackage.model_json_schema(),
                    )
                self.assertEqual(len(ai.usage), 2)
                self.assert_no_private_diagnostics(
                    logs.output, ai.usage, calls[1].kwargs
                )

    async def test_second_invalid_result_fails_without_unbounded_retries_or_leaks(self):
        bad = sdk_response(json.dumps({
            **LEDGER, "PRIVATE_FIELD_NAME": "PRIVATE_FIELD_VALUE",
        }))
        ai = self.ai(bad, bad, ledger_response())
        with self.assertLogs(
            "app.services.content_gemini", level="INFO"
        ) as logs, self.assertRaisesRegex(
            ValueError, "(?i)(invalid|schema|structured)"
        ) as raised:
            await self.structured(ai)
        self.assertEqual(ai.client.aio.models.generate_content.await_count, 2)
        self.assertEqual(len(ai.usage), 2)
        self.assertIn("research_ledger", " ".join(logs.output))
        self.assert_no_private_diagnostics(logs.output, ai.usage, str(raised.exception))

    async def test_thought_only_truncation_reports_token_limit_after_one_retry(self):
        bad = sdk_response(finish="MAX_TOKENS", thought=True)
        ai = self.ai(bad, bad, ledger_response())
        with self.assertLogs(
            "app.services.content_gemini", level="INFO"
        ) as logs, self.assertRaisesRegex(
            ValueError, "(?i)(token|truncat|output limit)"
        ) as raised:
            await self.structured(ai)
        self.assertEqual(ai.client.aio.models.generate_content.await_count, 2)
        self.assert_no_private_diagnostics(logs.output, ai.usage, str(raised.exception))

    async def test_max_tokens_is_rejected_even_when_text_looks_like_complete_json(self):
        ai = self.ai(ledger_response(finish="MAX_TOKENS"), ledger_response())
        with self.assertLogs("app.services.content_gemini", level="INFO"):
            self.assertEqual(await self.structured(ai), LEDGER)
        self.assertEqual(ai.client.aio.models.generate_content.await_count, 2)

    async def test_fenced_json_is_not_repaired_or_accepted(self):
        bad = sdk_response("```json\n" + json.dumps(LEDGER) + "\n```")
        ai = self.ai(bad, bad)
        with self.assertLogs(
            "app.services.content_gemini", level="INFO"
        ), self.assertRaisesRegex(ValueError, "(?i)(invalid|json|structured)"):
            await self.structured(ai)
        self.assertEqual(ai.client.aio.models.generate_content.await_count, 2)

    async def test_blocked_structured_responses_are_not_retried(self):
        for bad in (
            sdk_response(blocked="SAFETY"),
            sdk_response("PRIVATE_PROVIDER_TEXT", finish="SAFETY"),
            sdk_response("PRIVATE_PROVIDER_TEXT", finish="RECITATION"),
        ):
            with self.subTest(finish=bad.candidates[0].finish_reason
                              if bad.candidates else "prompt-block"):
                ai = self.ai(bad, ledger_response())
                with self.assertLogs(
                    "app.services.content_gemini", level="INFO"
                ) as logs, self.assertRaisesRegex(
                    ValueError, "(?i)(blocked|safety|recitation)"
                ) as raised:
                    await self.structured(ai)
                self.assertEqual(ai.client.aio.models.generate_content.await_count, 1)
                self.assert_no_private_diagnostics(
                    logs.output, ai.usage, str(raised.exception)
                )

    async def test_ledger_retry_does_not_repeat_research_search(self):
        ai = self.ai(
            sdk_response("Supported research", sources=[SOURCE]),
            sdk_response('{"PRIVATE_PROVIDER_TEXT":'),
            ledger_response(),
        )
        with self.assertLogs("app.services.content_gemini", level="INFO"):
            result = await ai.research(deepcopy(INPUTS))
        calls = ai.client.aio.models.generate_content.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(
            [usage["stage"] for usage in result["usage"]],
            ["search", "research_ledger", "research_ledger"],
        )
        self.assertIn("google_search", calls[0].kwargs["config"]["tools"][0])
        self.assertNotIn("tools", calls[1].kwargs["config"])
        self.assertNotIn("tools", calls[2].kwargs["config"])
        self.assertEqual(calls[1].kwargs["contents"], calls[2].kwargs["contents"])

    async def test_failed_search_is_not_retried_and_does_not_request_a_ledger(self):
        for bad in (
            sdk_response("PRIVATE_PROVIDER_TEXT", "MAX_TOKENS", sources=[SOURCE]),
            sdk_response("PRIVATE_PROVIDER_TEXT", "SAFETY", sources=[SOURCE]),
            sdk_response(sources=[SOURCE]),
            sdk_response(blocked="SAFETY"),
        ):
            with self.subTest(finish=bad.candidates[0].finish_reason
                              if bad.candidates else "prompt-block"):
                ai = self.ai(bad, ledger_response())
                with self.assertLogs(
                    "app.services.content_gemini", level="INFO"
                ) as logs, self.assertRaises(ValueError) as raised:
                    await ai.research(deepcopy(INPUTS))
                self.assertEqual(ai.client.aio.models.generate_content.await_count, 1)
                self.assert_no_private_diagnostics(
                    logs.output, ai.usage, str(raised.exception)
                )

    async def test_thinking_budget_is_limited_to_25_flash_ledger_extraction(self):
        cases = (
            ("gemini-2.5-flash", "research_ledger", True),
            ("models/gemini-2.5-flash", "research_ledger", True),
            ("gemini-2.5-flash-preview-09-2025", "research_ledger", True),
            ("gemini-2.5-pro", "research_ledger", False),
            ("gemini-3-flash-preview", "research_ledger", False),
            ("gemini-2.0-flash", "research_ledger", False),
            ("unknown-model", "research_ledger", False),
            ("gemini-2.5-flash", "generate", False),
            ("gemini-2.5-flash", "qa", False),
            ("gemini-2.5-flash", "fix", False),
        )
        for model, stage, limited in cases:
            with self.subTest(model=model, stage=stage), patch.object(
                content_gemini.settings, "CONTENT_GEMINI_MODEL", model
            ):
                ai = self.ai(ledger_response())
                await self.structured(ai, stage)
                config = ai.client.aio.models.generate_content.call_args.kwargs[
                    "config"
                ]
                if limited:
                    self.assertEqual(
                        config["thinking_config"]["thinking_budget"], 0
                    )
                else:
                    self.assertNotIn("thinking_config", config)

    async def test_each_search_and_ledger_call_has_a_120_second_deadline(self):
        ai = self.ai(
            sdk_response("Supported research", sources=[SOURCE]), ledger_response()
        )
        real_wait_for = asyncio.wait_for
        with patch.object(
            content_gemini.asyncio, "wait_for", wraps=real_wait_for
        ) as bounded:
            await ai.research(deepcopy(INPUTS))
        self.assertEqual(bounded.call_count, 2)
        for call in bounded.call_args_list:
            timeout = call.kwargs.get("timeout")
            if timeout is None:
                timeout = call.args[1]
            self.assertEqual(timeout, 120)

    async def test_malformed_and_missing_fields_stop_after_the_second_attempt(self):
        for text in (
            '{"PRIVATE_PROVIDER_TEXT":',
            '{"ready":true}',
            json.dumps({**LEDGER, "claims": "PRIVATE_FIELD_VALUE"}),
        ):
            with self.subTest(text_kind=len(text)):
                bad = sdk_response(text)
                ai = self.ai(bad, bad, ledger_response())
                with self.assertLogs(
                    "app.services.content_gemini", level="INFO"
                ) as logs, self.assertRaisesRegex(
                    ValueError, "(?i)(invalid|schema|structured)"
                ) as raised:
                    await self.structured(ai)
                self.assertEqual(ai.client.aio.models.generate_content.await_count, 2)
                self.assertEqual([u["attempt"] for u in ai.usage], [1, 2])
                self.assert_no_private_diagnostics(
                    logs.output, ai.usage, str(raised.exception)
                )

    async def test_unknown_status_values_are_sanitized_in_logs_and_usage(self):
        response = NS(
            text="PRIVATE_PROVIDER_TEXT", usage_metadata=None,
            candidates=[NS(finish_reason="PRIVATE_FINISH_DETAIL")],
            prompt_feedback=NS(block_reason="PRIVATE_BLOCK_DETAIL"),
        )
        ai = self.ai(response)
        with self.assertLogs(
            "app.services.content_gemini", level="INFO"
        ) as logs, self.assertRaises(ValueError) as raised:
            await self.structured(ai)
        self.assertEqual(ai.client.aio.models.generate_content.await_count, 1)
        self.assertEqual(ai.usage[0]["finish_reason"], "UNKNOWN")
        self.assertEqual(ai.usage[0]["block_reason"], "UNKNOWN")
        self.assert_no_private_diagnostics(logs.output, ai.usage, str(raised.exception))

    async def test_request_timeout_is_actionable_and_does_not_leak_provider_text(self):
        ai = self.ai()
        ai.client.aio.models.generate_content.side_effect = TimeoutError(
            "PRIVATE_PROVIDER_TEXT"
        )
        with self.assertRaisesRegex(
            ValueError, "(?i)(timed out|timeout)"
        ) as raised:
            await ai.request("{}", {}, "research_ledger")
        self.assertEqual(ai.client.aio.models.generate_content.await_count, 1)
        self.assert_no_private_diagnostics(str(raised.exception), ai.usage)

