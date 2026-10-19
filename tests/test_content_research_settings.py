"""Isolated research profiles, immutable jobs, migrations and mocked providers."""
import importlib.util
import json
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import JSON, MetaData, create_engine, event, inspect, insert, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.admin import content_routes
from app.core.admin_security import require_admin
from app.db.base import Base
from app.db.models.content_workflow import ContentResearchSettings, ContentRun
from app.db.query import content_workflow as q
from app.db.session import get_db
from app.schemas.content_workflow import (
    Brief, BriefEdit, ResearchSettingsInput, RunInput, TopicInput,
)
from app.services import content_research_settings as profile_service
from app.services import content_workflow as workflow
from app.services.content_ai import ContentAI
from app.services.content_gemini import GeminiContentAI
from app.services.content_research_defaults import (
    RESEARCH_INSTRUCTIONS, default_research_settings, research_context,
)
from app.services.content_worker import finish
from migrations import migration_script
from test_content_workflow import Adapter, PAYLOAD, RESEARCH


CUSTOM_INSTRUCTIONS = "Explain operating effort and tradeoffs using primary evidence."
CUSTOM_GROUPS = [
    {"name": "Documentation", "urls": ["https://docs.example.com/seed"]},
    {"name": "Engineering", "urls": ["https://engineering.example.com/seed"]},
]
EXTRA_URL = "https://business.example.com/article-specific"
CITED_URL = "https://primary.example.com/actual-evidence"


def profile_input(expected_version=0, **changes):
    return ResearchSettingsInput(
        **{
            "expected_version": expected_version,
            "instructions": CUSTOM_INSTRUCTIONS,
            "source_groups": deepcopy(CUSTOM_GROUPS),
            **changes,
        }
    )


class ResearchSettingsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        for table in Base.metadata.sorted_tables:
            if table.name == "articles" or table.name.startswith("content_"):
                local = table.to_metadata(metadata)
                if table.name == "articles":
                    local.c.tags.type = JSON()
                    local.c.keywords.type = JSON()
                for index in local.indexes:
                    if index.name == "uq_content_active_topic":
                        index.dialect_options["sqlite"]["where"] = text(
                            "status IN ('queued','running')"
                        )
        metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.addCleanup(lambda: self.session.close())
        self.db = Adapter(self.session)
        self.enterContext(
            patch.object(content_routes.settings, "CONTENT_WORKFLOW_ENABLED", True)
        )

    def reload_session(self):
        self.session.close()
        self.session = Session(self.engine, expire_on_commit=False)
        self.db = Adapter(self.session)

    async def topic(self, suffix="", source_urls=None):
        created = await workflow.create(
            self.db,
            TopicInput(
                title="Data warehouse decision" + suffix,
                reader_question="Does our company need a warehouse?",
                track="Foundations",
            ),
            1,
        )
        topic = await q.topic(self.db, created["topic_id"])
        brief = Brief(scope=topic.reader_question, source_urls=source_urls or [])
        await workflow.brief(
            self.db, topic.topic_id,
            BriefEdit(expected_version=topic.version, brief=brief), 1,
        )
        return topic

    def client(self, authenticated=False):
        app = FastAPI()
        app.include_router(content_routes.router, prefix="/v1/admin")
        app.dependency_overrides[get_db] = lambda: self.db
        if authenticated:
            app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
        return TestClient(app)

    async def test_unsaved_defaults_need_no_row_and_share_no_mutable_values(self):
        first = await profile_service.get_settings(self.db)
        self.assertEqual(first["version"], 0)
        self.assertEqual(len(first["source_groups"]), 4)
        urls = [url for group in first["source_groups"] for url in group["urls"]]
        self.assertEqual(len(urls), 20)
        self.assertEqual(len(set(urls)), 20)
        self.assertEqual([g["name"] for g in first["source_groups"]], [
            "Primary technical sources", "Independent research",
            "Business research and use cases", "Community insights",
        ])
        self.assertEqual(set(urls), {
            "https://cloud.google.com/docs", "https://learn.microsoft.com",
            "https://docs.databricks.com", "https://docs.aws.amazon.com",
            "https://docs.snowflake.com", "https://airflow.apache.org/docs",
            "https://kafka.apache.org/documentation", "https://docs.getdbt.com",
            "https://www.thoughtworks.com/radar", "https://www.infoq.com",
            "https://martinfowler.com", "https://www.cncf.io",
            "https://www.mckinsey.com", "https://www.deloitte.com",
            "https://cloud.google.com/customers",
            "https://www.microsoft.com/en/customers",
            "https://www.databricks.com/customers",
            "https://www.reddit.com/r/dataengineering/",
            "https://www.reddit.com/r/BusinessIntelligence/",
            "https://news.ycombinator.com",
        })
        self.assertIsNone(await q.research_settings(self.db))
        expected = deepcopy(first)
        first["instructions"] = "Accidental caller change"
        first["source_groups"][0]["urls"].clear()
        self.assertEqual(await profile_service.get_settings(self.db), expected)
        self.assertEqual(default_research_settings(), expected)
        self.assertIsNone(await q.research_settings(self.db))

    async def test_saved_profile_survives_new_session_and_edits_increment_version(self):
        saved = await profile_service.save_settings(self.db, profile_input())
        self.assertEqual(saved, {
            "version": 1,
            "instructions": CUSTOM_INSTRUCTIONS,
            "source_groups": CUSTOM_GROUPS,
        })
        self.reload_session()
        self.assertEqual(await profile_service.get_settings(self.db), saved)
        updated = await profile_service.save_settings(
            self.db, profile_input(1, instructions="Updated research policy.")
        )
        self.assertEqual(updated["version"], 2)
        self.reload_session()
        self.assertEqual(await profile_service.get_settings(self.db), updated)

    async def test_saved_empty_source_pool_remains_empty_after_reload_and_enqueue(self):
        saved = await profile_service.save_settings(
            self.db, profile_input(source_groups=[])
        )
        self.reload_session()
        self.assertEqual(saved["source_groups"], [])
        self.assertEqual(await profile_service.get_settings(self.db), saved)
        topic = await self.topic()
        job = await workflow.start(
            self.db, topic.topic_id,
            RunInput(
                stage="research", expected_version=topic.version,
                request_key="empty-pool-profile-research",
            ), 1,
        )
        self.assertEqual(job["inputs"]["research_settings"], saved)

    async def test_preloaded_stale_session_cannot_overwrite_another_editors_save(self):
        first = await profile_service.save_settings(self.db, profile_input())
        other_session = Session(self.engine, expire_on_commit=False)
        try:
            updated = await profile_service.save_settings(
                Adapter(other_session),
                profile_input(
                    first["version"], instructions="Another editor's change."
                ),
            )
        finally:
            other_session.close()
        with self.assertRaises(profile_service.Conflict):
            await profile_service.save_settings(
                self.db, profile_input(first["version"], instructions="Stale window.")
            )
        self.assertEqual(await profile_service.get_settings(self.db), updated)

    async def test_initial_and_subsequent_stale_saves_preserve_current_profile(self):
        with self.assertRaises(profile_service.Conflict):
            await profile_service.save_settings(self.db, profile_input(1))
        self.assertIsNone(await q.research_settings(self.db))
        saved = await profile_service.save_settings(self.db, profile_input())
        for version in (0, 2):
            with self.subTest(stale_version=version):
                with self.assertRaises(profile_service.Conflict):
                    await profile_service.save_settings(
                        self.db, profile_input(version, instructions="Stale change.")
                    )
                self.assertEqual(await profile_service.get_settings(self.db), saved)

    async def test_get_and_put_require_admin_authentication(self):
        with self.client() as client:
            self.assertEqual(
                client.get("/v1/admin/content-research-settings").status_code, 401
            )
            self.assertEqual(
                client.put(
                    "/v1/admin/content-research-settings",
                    json=profile_input().model_dump(),
                ).status_code,
                401,
            )
        self.assertIsNone(await q.research_settings(self.db))

    async def test_http_roundtrip_conflicts_and_validation(self):
        endpoint = "/v1/admin/content-research-settings"
        with self.client(authenticated=True) as client:
            defaults = client.get(endpoint)
            self.assertEqual(defaults.status_code, 200)
            self.assertEqual(defaults.json()["version"], 0)
            payload = profile_input().model_dump()
            saved = client.put(endpoint, json=payload)
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.json()["version"], 1)
            self.assertEqual(client.get(endpoint).json(), saved.json())
            self.assertEqual(client.put(endpoint, json=payload).status_code, 409)
            invalid = {**payload, "expected_version": 1, "instructions": "   "}
            self.assertEqual(client.put(endpoint, json=invalid).status_code, 422)
            self.assertEqual(client.get(endpoint).json(), saved.json())

    async def test_brief_without_extra_urls_queues_research_with_defaults(self):
        topic = await self.topic()
        self.assertEqual(topic.brief["source_urls"], [])
        self.assertIn("Business leaders", topic.brief["audience"])
        job = await workflow.start(
            self.db, topic.topic_id,
            RunInput(
                stage="research", expected_version=topic.version,
                request_key="default-profile-research",
            ), 1,
        )
        self.assertEqual(
            job["inputs"]["research_settings"], default_research_settings()
        )
        self.assertEqual(job["inputs"]["brief"]["source_urls"], [])
        self.assertIsNone(await q.research_settings(self.db))

    async def test_profile_edits_do_not_change_queued_or_later_stage_snapshots(self):
        first_profile = await profile_service.save_settings(self.db, profile_input())
        topic = await self.topic(source_urls=[EXTRA_URL])
        data = await workflow.start(
            self.db, topic.topic_id,
            RunInput(
                stage="research", expected_version=topic.version,
                request_key="snapshot-profile-research", provider="gemini",
            ), 1,
        )
        research_id = data["id"]
        later_profile = await profile_service.save_settings(
            self.db, profile_input(1, instructions="Policy for future research.")
        )
        self.reload_session()
        research = await q.run(self.db, research_id)
        self.assertEqual(research.inputs["research_settings"], first_profile)
        self.assertEqual(research.inputs["brief"]["source_urls"], [EXTRA_URL])

        future_topic = await self.topic(" future")
        future = await workflow.start(
            self.db, future_topic.topic_id,
            RunInput(
                stage="research", expected_version=future_topic.version,
                request_key="future-profile-research",
            ), 1,
        )
        self.assertEqual(future["inputs"]["research_settings"], later_profile)

        research.status = "running"
        research.lease_token = "research-lease"
        await finish(self.db, research.id, research.lease_token, deepcopy(RESEARCH))
        topic = await q.topic(self.db, research.topic_id)
        generation = await workflow.start(
            self.db, topic.topic_id,
            RunInput(
                stage="generate", expected_version=topic.version,
                request_key="snapshot-profile-generate",
            ), 1,
        )
        self.assertEqual(generation["inputs"]["research_settings"], first_profile)
        generate_job = await q.run(self.db, generation["id"])
        generate_job.status = "running"
        generate_job.lease_token = "generate-lease"
        await finish(
            self.db, generate_job.id, generate_job.lease_token,
            {"payload": deepcopy(PAYLOAD), "usage": []},
        )
        qa = await q.active(self.db, topic.topic_id)
        self.assertEqual(qa.stage, "qa")
        self.assertEqual(qa.inputs["research_settings"], first_profile)
        qa.status = "running"
        qa.lease_token = "qa-lease"
        await finish(self.db, qa.id, qa.lease_token, {"findings": []})
        version = (await q.versions(self.db, topic.topic_id))[0]
        for stage in ("qa", "fix"):
            job = await workflow.start(
                self.db, topic.topic_id,
                RunInput(
                    stage=stage, expected_version=topic.version, version_id=version.id,
                    request_key=f"snapshot-profile-{stage}-manual",
                ), 1,
            )
            self.assertEqual(job["inputs"]["research_settings"], first_profile)
            await workflow.cancel(self.db, job["id"], 1)

    async def test_legacy_research_generation_uses_defaults_not_current_profile(self):
        await profile_service.save_settings(self.db, profile_input())
        topic = await self.topic()
        research = ContentRun(
            id="legacy-research", topic_id=topic.topic_id, stage="research",
            request_key="legacy-research-request", status="completed",
            inputs={"brief_version": topic.brief_version}, result=deepcopy(RESEARCH),
        )
        await q.add(self.db, research)
        await q.commit(self.db)
        generation = await workflow.start(
            self.db, topic.topic_id,
            RunInput(
                stage="generate", expected_version=topic.version,
                request_key="legacy-research-generate",
            ), 1,
        )
        self.assertEqual(
            generation["inputs"]["research_settings"], default_research_settings()
        )


class ResearchSettingsSchemaTests(unittest.TestCase):
    def test_duplicates_merge_group_names_and_keep_first_url_occurrence(self):
        payload = profile_input(source_groups=[
            {"name": " Primary ", "urls": [
                " https://example.com/one ", "https://example.com/one",
            ]},
            {"name": "primary", "urls": ["https://example.com/two"]},
            {"name": "Secondary", "urls": [
                "https://example.com/one", "https://example.com/three",
            ]},
            {"name": "Empty", "urls": []},
        ])
        self.assertEqual([group.model_dump() for group in payload.source_groups], [
            {"name": "Primary", "urls": [
                "https://example.com/one", "https://example.com/two",
            ]},
            {"name": "Secondary", "urls": ["https://example.com/three"]},
        ])

    def test_rejects_unsafe_or_malformed_source_urls(self):
        for url in (
            "http://example.com/docs", "https://127.0.0.1",
            "https://169.254.169.254", "https://example.internal/docs",
            "https://user:password@example.com", "https://example.com:9000",
            "javascript:alert(1)", "https://exa mple.com/docs",
            "https://example.com/a\nb", "https://example.com/a\x00b",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    profile_input(source_groups=[{"name": "Invalid", "urls": [url]}])

    def test_rejects_field_and_collection_overflows(self):
        invalid_changes = (
            {"expected_version": -1},
            {"instructions": ""},
            {"instructions": " "},
            {"instructions": "x" * 20001},
            {"source_groups": [{"name": "", "urls": []}]},
            {"source_groups": [{"name": "x" * 101, "urls": []}]},
            {"source_groups": [{"name": str(i), "urls": []} for i in range(21)]},
            {"source_groups": [{"name": "Too many", "urls": [
                f"https://example.com/{i}" for i in range(51)
            ]}]},
            {"source_groups": [{"name": "Too long", "urls": [
                "https://example.com/" + "x" * 2048
            ]}]},
            {"source_groups": [
                {"name": str(group), "urls": [
                    f"https://example.com/{group}/{i}" for i in range(34)
                ]} for group in range(3)
            ]},
            {"source_groups": [
                {"name": "Same", "urls": [
                    f"https://example.com/{group}/{i}" for i in range(30)
                ]} for group in range(2)
            ]},
        )
        for index, changes in enumerate(invalid_changes):
            with self.subTest(case=index):
                with self.assertRaises(ValidationError):
                    profile_input(**changes)

    def test_accepts_empty_groups_and_upper_bounds_after_deduplication(self):
        self.assertEqual(profile_input(source_groups=[]).source_groups, [])
        empty = profile_input(source_groups=[{"name": "Empty", "urls": []}])
        self.assertEqual(empty.source_groups, [])
        groups = [
            {"name": str(group), "urls": [
                f"https://example.com/{group}/{i}" for i in range(5)
            ]} for group in range(20)
        ]
        accepted = profile_input(instructions="x" * 20000, source_groups=groups)
        self.assertEqual(sum(len(g.urls) for g in accepted.source_groups), 100)
        url = "https://example.com/" + "x" * (2048 - len("https://example.com/"))
        accepted = profile_input(source_groups=[{"name": "x" * 100, "urls": [url]}])
        self.assertEqual(len(accepted.source_groups[0].urls[0]), 2048)
        # Cross-group duplicates should not consume the total unique-URL budget.
        duplicated = groups[:2] + [
            {"name": str(group), "urls": list(groups[0]["urls"])}
            for group in range(2, 20)
        ]
        normalized = profile_input(source_groups=duplicated)
        self.assertEqual(sum(len(g.urls) for g in normalized.source_groups), 10)

    def test_research_context_deepcopies_legacy_defaults_and_explicit_snapshot(self):
        legacy = {"title": "Warehouse", "question": "Need one?", "brief": {}}
        context = research_context(legacy)
        self.assertEqual(context["research_settings"], default_research_settings())
        context["research_settings"]["source_groups"][0]["urls"].clear()
        self.assertEqual(
            research_context(legacy)["research_settings"], default_research_settings()
        )
        snapshot = {
            "version": 7, "instructions": CUSTOM_INSTRUCTIONS,
            "source_groups": deepcopy(CUSTOM_GROUPS),
        }
        supplied = {**legacy, "research_settings": snapshot}
        context = research_context(supplied)
        context["research_settings"]["instructions"] = "Caller mutation"
        self.assertEqual(supplied["research_settings"], snapshot)
        self.assertEqual(snapshot["instructions"], CUSTOM_INSTRUCTIONS)


class ResearchSettingsProviderTests(unittest.IsolatedAsyncioTestCase):
    def ai(self, provider):
        ledger = {
            "ready": True, "summary": "Supported research", "gaps": [],
            "claims": [{
                "claim": "Documented behavior", "evidence": "Primary documentation",
                "qualification": "", "source_urls": [CITED_URL],
            }],
        }
        if provider == "openai":
            ai = ContentAI.__new__(ContentAI)
            output = SimpleNamespace(model_dump=lambda: {
                "content": [{"annotations": [{"url": CITED_URL, "title": "Evidence"}]}]
            })
            response = SimpleNamespace(
                output=[output], output_text="Supported research", id="fixture",
                model="fixture-model", usage=None,
            )
            call = AsyncMock(return_value=response)
            ai.client = SimpleNamespace(responses=SimpleNamespace(create=call))
        else:
            ai = GeminiContentAI.__new__(GeminiContentAI)
            response = SimpleNamespace(
                text="Supported research", usage_metadata=None,
                candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(
                    web_search_queries=["primary documentation"],
                    grounding_chunks=[SimpleNamespace(web=SimpleNamespace(
                        uri=CITED_URL, title="Evidence",
                    ))],
                ))],
            )
            call = AsyncMock(return_value=response)
            ai.client = SimpleNamespace(
                aio=SimpleNamespace(models=SimpleNamespace(generate_content=call))
            )
        ai.usage = []
        ai.structured = AsyncMock(return_value=deepcopy(ledger))
        return ai, call

    async def test_both_providers_receive_policy_profile_and_optional_sources(self):
        snapshot = {
            "version": 3, "instructions": CUSTOM_INSTRUCTIONS,
            "source_groups": deepcopy(CUSTOM_GROUPS),
        }
        inputs = {
            "title": "Warehouse", "question": "Need one?",
            "brief": {"scope": "Our operating decision", "source_urls": [EXTRA_URL]},
            "research_settings": snapshot,
        }
        for provider in ("openai", "gemini"):
            with self.subTest(provider=provider):
                ai, call = self.ai(provider)
                result = await ai.research(inputs)
                args = call.call_args.kwargs
                policy = " ".join(RESEARCH_INSTRUCTIONS.lower().split())
                self.assertIn("official pricing pages", policy)
                self.assertIn("read relevant direct pages", policy)
                self.assertIn(
                    "community discussions provide experiences and opinions, "
                    "not verified technical facts", policy,
                )
                if provider == "openai":
                    self.assertEqual(args["instructions"], RESEARCH_INSTRUCTIONS)
                    sent = json.loads(args["input"])
                    self.assertEqual(args["tools"], [{"type": "web_search"}])
                else:
                    self.assertEqual(
                        args["config"]["system_instruction"], RESEARCH_INSTRUCTIONS
                    )
                    sent = json.loads(args["contents"])
                    self.assertEqual(args["config"]["tools"], [{"google_search": {}}])
                self.assertEqual(sent["research_settings"], snapshot)
                self.assertEqual(sent["brief"]["source_urls"], [EXTRA_URL])
                self.assertEqual(
                    [source["url"] for source in result["sources"]], [CITED_URL]
                )
                self.assertEqual(result["claims"][0]["source_urls"], [CITED_URL])
                self.assertEqual(
                    ai.structured.call_args.args[2]["allowed_sources"], [CITED_URL]
                )
                self.assertTrue(result["ready"])
                self.assertTrue(result["usage"])

    async def test_both_providers_support_jobs_without_a_profile_or_extra_urls(self):
        inputs = {"title": "Warehouse", "question": "Need one?", "brief": {}}
        for provider in ("openai", "gemini"):
            with self.subTest(provider=provider):
                ai, call = self.ai(provider)
                await ai.research(inputs)
                args = call.call_args.kwargs
                sent = json.loads(args["input" if provider == "openai" else "contents"])
                self.assertEqual(sent["research_settings"], default_research_settings())
                self.assertEqual(sent["brief"], {})

    async def test_both_providers_preserve_an_explicitly_cleared_source_pool(self):
        snapshot = {
            "version": 4, "instructions": CUSTOM_INSTRUCTIONS, "source_groups": [],
        }
        inputs = {
            "title": "Warehouse", "question": "Need one?",
            "brief": {"source_urls": []}, "research_settings": snapshot,
        }
        for provider in ("openai", "gemini"):
            with self.subTest(provider=provider):
                ai, call = self.ai(provider)
                await ai.research(inputs)
                args = call.call_args.kwargs
                sent = json.loads(args["input" if provider == "openai" else "contents"])
                self.assertEqual(sent["research_settings"], snapshot)


class ResearchSettingsMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        root = Path(__file__).resolve().parents[1]
        path = root / "alembic" / "versions" / "c02_research_settings.py"
        spec = importlib.util.spec_from_file_location("research_migration", path)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        self.sql_path = (
            root / "migrations" / "history_sql_mig"
            / "010_content_research_settings.sql"
        )

    def apply(self, function):
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                function()

    def assert_current_schema(self):
        metadata = MetaData()
        ContentResearchSettings.__table__.to_metadata(metadata)
        with self.engine.connect() as connection:
            self.assertEqual(
                compare_metadata(MigrationContext.configure(connection), metadata), []
            )
        for invalid in ({"id": 2, "version": 1}, {"id": 1, "version": 0}):
            with self.subTest(invalid=invalid), self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.execute(insert(ContentResearchSettings).values(
                        **invalid, instructions=CUSTOM_INSTRUCTIONS, source_groups=[],
                    ))

    def test_alembic_upgrade_constraints_downgrade_and_recreate(self):
        self.assertEqual(self.migration.down_revision, "c01_content_workflow")
        self.apply(self.migration.upgrade)
        self.assert_current_schema()
        self.apply(self.migration.downgrade)
        self.assertEqual(inspect(self.engine).get_table_names(), [])
        self.apply(self.migration.upgrade)
        self.assert_current_schema()

    def test_sql_migration_matches_model_and_enforces_singleton_version(self):
        with self.engine.begin() as connection:
            connection.execute(text(self.sql_path.read_text(encoding="utf-8")))
        self.assert_current_schema()

    def prepare_sql_runner(self):
        # Explicit BEGIN models PostgreSQL transactional DDL on SQLite.
        @event.listens_for(self.engine, "connect")
        def configure_transaction(connection, record):
            connection.isolation_level = None

        @event.listens_for(self.engine, "begin")
        def begin_transaction(connection):
            connection.exec_driver_sql("BEGIN")

        self.enterContext(patch.object(migration_script, "engine", self.engine))
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE schema_migrations "
                "(filename TEXT PRIMARY KEY, applied_at TIMESTAMP)"
            ))

    def test_sql_runner_commits_exact_migration_table_and_history_together(self):
        self.prepare_sql_runner()
        migration_script.run_sql_file(self.sql_path)
        self.assertIn(
            "content_research_settings", inspect(self.engine).get_table_names()
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(text(
                    "SELECT filename FROM schema_migrations"
                )).scalars().all(),
                [self.sql_path.name],
            )
        self.assertTrue(migration_script.has_migration_run(self.sql_path.name))

    def test_sql_runner_history_failure_rolls_back_exact_migration_table(self):
        self.prepare_sql_runner()
        with self.engine.begin() as connection:
            migration_script.record_migration(self.sql_path.name, connection)
        with self.assertRaises(IntegrityError):
            migration_script.run_sql_file(self.sql_path)
        self.assertEqual(
            inspect(self.engine).get_table_names(), ["schema_migrations"]
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(text(
                    "SELECT filename FROM schema_migrations"
                )).scalars().all(),
                [self.sql_path.name],
            )
