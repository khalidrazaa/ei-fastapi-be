"""Failure telemetry and discard guards, without database or provider calls."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import content_worker as worker

USAGE = [{
    "stage": "research_ledger",
    "provider": "gemini",
    "attempt": 1,
    "finish_reason": "MAX_TOKENS",
    "usage": {"thoughts_token_count": 1000, "candidates_token_count": 50},
}]
PRIVATE_CONTENT = "private research, article, or provider response"


class WorkerFailureDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = object()
        self.job = SimpleNamespace(
            id="failed-research-run",
            topic_id="EXPLAINIT-001",
            inputs={"brief_version": 4, "provider": "gemini"},
            status="running",
            lease_token="current-lease",
            cancel_requested=False,
            result=None,
            error=None,
            finished_at=None,
            lease_until="active lease",
        )
        self.topic = SimpleNamespace(brief_version=4, version=7)
        self.run_query = self.mock_query("run", self.job)
        self.topic_query = self.mock_query("topic", self.topic)
        self.commit = self.mock_query("commit")
        self.add = self.mock_query("add")

    def mock_query(self, name, result=None):
        mock = AsyncMock(return_value=result)
        patcher = patch.object(worker.q, name, mock)
        patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    async def finish(self, result, token="current-lease"):
        await worker.finish(
            self.db, self.job.id, token, result,
            "Gemini research ledger reached its output limit.",
        )

    async def test_failure_retains_only_usage_and_discards_partial_content(self):
        await self.finish({
            "usage": USAGE,
            "payload": {"content": PRIVATE_CONTENT},
            "research_text": PRIVATE_CONTENT,
            "raw_response": PRIVATE_CONTENT,
        })

        self.assertEqual(self.job.status, "failed")
        self.assertEqual(self.job.result, {"usage": USAGE})
        self.assertNotIn(PRIVATE_CONTENT, repr(self.job.result))
        self.assertIn("output limit", self.job.error)
        self.assertIsNotNone(self.job.finished_at)
        self.assertIsNone(self.job.lease_until)
        self.assertEqual(self.topic.version, 7)
        self.add.assert_not_awaited()
        self.commit.assert_awaited_once_with(self.db)

    async def test_failure_without_usage_does_not_store_partial_result(self):
        for result in (None, {}, {"payload": PRIVATE_CONTENT}, {"usage": []}):
            with self.subTest(result=result):
                self.job.status = "running"
                await self.finish(result)
                self.assertEqual(self.job.status, "failed")
                self.assertIsNone(self.job.result)
        self.add.assert_not_awaited()

    async def test_cancellation_discards_usage_even_when_provider_failed(self):
        self.job.cancel_requested = True
        await self.finish({"usage": USAGE, "payload": PRIVATE_CONTENT})

        self.assertEqual(self.job.status, "cancelled")
        self.assertIsNone(self.job.result)
        self.assertIsNone(self.job.error)
        self.commit.assert_awaited_once_with(self.db)
        self.add.assert_not_awaited()

    async def test_changed_brief_discards_failure_usage_and_partial_result(self):
        self.topic.brief_version = 5
        await self.finish({"usage": USAGE, "payload": PRIVATE_CONTENT})

        self.assertEqual(self.job.status, "failed")
        self.assertIn("Brief changed", self.job.error)
        self.assertIsNone(self.job.result)
        self.assertEqual(self.topic.version, 7)
        self.commit.assert_awaited_once_with(self.db)
        self.add.assert_not_awaited()

    async def test_stale_lease_or_finished_job_cannot_write_failure_diagnostics(self):
        await self.finish({"usage": USAGE}, token="expired-lease")
        self.assertEqual(self.job.status, "running")
        self.assertIsNone(self.job.result)
        self.assertIsNone(self.job.finished_at)

        self.job.status = "completed"
        self.job.result = {"existing": "successful result"}
        await self.finish({"usage": USAGE})
        self.assertEqual(self.job.result, {"existing": "successful result"})
        self.assertIsNone(self.job.error)
        self.topic_query.assert_not_awaited()
        self.commit.assert_not_awaited()

    async def test_tick_captures_usage_when_perform_fails_without_leaking_content(self):
        ai = SimpleNamespace(usage=[], close=AsyncMock())

        async def fail_perform(job, provider):
            provider.usage.extend(USAGE)
            raise RuntimeError(PRIVATE_CONTENT)

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=self.db)
        session.__aexit__ = AsyncMock(return_value=False)
        finished = AsyncMock()
        with (
            patch.object(worker, "SessionLocal", return_value=session),
            patch.object(worker.q, "claim", AsyncMock(return_value=self.job)),
            patch.object(worker, "GeminiContentAI", return_value=ai),
            patch.object(worker, "perform", side_effect=fail_perform),
            patch.object(worker, "finish", finished),
            self.assertLogs(worker.logger, level="WARNING") as logs,
        ):
            self.assertTrue(await worker.tick())

        finished.assert_awaited_once()
        args = finished.await_args.args
        self.assertEqual(args[:3], (self.db, self.job.id, "current-lease"))
        self.assertEqual(args[3], {"usage": USAGE})
        self.assertTrue(args[4].startswith("RuntimeError: provider or worker"))
        self.assertNotIn(PRIVATE_CONTENT, args[4])
        self.assertNotIn(PRIVATE_CONTENT, " ".join(logs.output))
        ai.close.assert_awaited_once()
