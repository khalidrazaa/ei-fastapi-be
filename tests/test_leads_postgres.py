"""Opt-in PostgreSQL checks against a disposable local *_test database.

Never uses DATABASE_URL or the configured deployment database. Each test owns a
random schema; the lead migration chain is applied only inside that schema.
Email delivery is mocked throughout these tests.
"""

import asyncio
import importlib.util
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import MetaData, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models.lead import Lead
from app.db.query import lead as lead_query
from app.schemas.contact import ContactRequest
from app.services import contact_service

TEST_URL = os.getenv("LEAD_TEST_DATABASE_URL", "")
VERSIONS_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions"
MIGRATION_PATHS = (
    VERSIONS_PATH / "7d2a4c9e81b0_add_leads_and_notification_outbox.py",
    VERSIONS_PATH / "b6f3e94d2a10_remove_lead_notification_outbox.py",
)


@unittest.skipUnless(TEST_URL, "Set LEAD_TEST_DATABASE_URL to a local *_test database.")
class LeadPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = make_url(TEST_URL)
        if url.host not in {"127.0.0.1", "localhost", "::1"} or not (
            url.database and url.database.endswith("_test")
        ):
            raise ValueError("Lead integration tests require a local *_test database.")
        self.email_patch = patch.object(
            contact_service, "send_contact_email", AsyncMock(return_value=None)
        )
        self.email = self.email_patch.start()
        self.addCleanup(self.email_patch.stop)
        self.schema = f"lead_test_{uuid4().hex}"
        self.admin_engine = create_async_engine(url, poolclass=NullPool)
        async with self.admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.engine = create_async_engine(
            url,
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": self.schema}},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.migrations = []
        for index, path in enumerate(MIGRATION_PATHS):
            spec = importlib.util.spec_from_file_location(
                f"lead_migration_{index}", path
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            self.migrations.append(migration)
            await self.run_migration(migration.upgrade)

    async def asyncTearDown(self):
        await self.engine.dispose()
        async with self.admin_engine.begin() as conn:
            # Only the random schema created in setUp is removed.
            await conn.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        await self.admin_engine.dispose()

    async def run_migration(self, migration):
        def apply(conn):
            with Operations.context(MigrationContext.configure(conn)):
                migration()

        async with self.engine.begin() as conn:
            await conn.run_sync(apply)

    async def submit(self, email="visitor@example.com"):
        async with self.sessions() as db:
            await contact_service.send_contact_message(
                ContactRequest(
                    name="Visitor", email=email, message="Consulting enquiry"
                ),
                "explainit.tech",
                db,
            )

    async def count(self):
        async with self.sessions() as db:
            return (
                await db.execute(select(func.count()).select_from(Lead))
            ).scalar_one()

    async def assert_schema_matches_model(self):
        metadata = MetaData()
        Lead.__table__.to_metadata(metadata)
        async with self.engine.connect() as conn:
            diffs = await conn.run_sync(
                lambda sync_conn: compare_metadata(
                    MigrationContext.configure(sync_conn),
                    metadata,
                )
            )
        self.assertEqual(diffs, [])

    async def test_fresh_migration_chain_matches_model_and_round_trips(self):
        self.assertEqual(self.migrations[1].down_revision, self.migrations[0].revision)
        await self.assert_schema_matches_model()
        for migration in reversed(self.migrations):
            await self.run_migration(migration.downgrade)
        for migration in self.migrations:
            await self.run_migration(migration.upgrade)
        await self.assert_schema_matches_model()
        await self.submit()
        self.assertEqual(await self.count(), 1)

    async def test_outbox_cleanup_and_rollback_preserve_existing_leads(self):
        await self.submit()
        await self.run_migration(self.migrations[1].downgrade)
        async with self.sessions() as db:
            await db.execute(
                text("INSERT INTO lead_notification_outbox (lead_id) VALUES (1)")
            )
            await db.commit()
        await self.run_migration(self.migrations[1].upgrade)
        self.assertEqual(await self.count(), 1)
        await self.assert_schema_matches_model()
        await self.run_migration(self.migrations[1].downgrade)
        async with self.sessions() as db:
            notifications = (
                await db.execute(text("SELECT COUNT(*) FROM lead_notification_outbox"))
            ).scalar_one()
        self.assertEqual(notifications, 0)
        self.assertEqual(await self.count(), 1)
        await self.run_migration(self.migrations[1].upgrade)
        self.assertEqual(await self.count(), 1)
        await self.assert_schema_matches_model()

    async def test_parallel_same_email_and_unicode_cannot_bypass_rate_limit(self):
        for email in ("visitor@example.com", "visitorß@example.com"):
            results = await asyncio.gather(
                self.submit(email),
                self.submit(email),
                return_exceptions=True,
            )
            self.assertEqual(sum(result is None for result in results), 1)
            self.assertEqual(
                sum(
                    isinstance(result, contact_service.ContactRateLimitError)
                    for result in results
                ),
                1,
            )
        self.assertEqual(await self.count(), 2)
        self.assertEqual(self.email.await_count, 2)

    async def test_multiple_enquiries_are_allowed_after_window_expiry(self):
        await self.submit()
        async with self.sessions() as db:
            await db.execute(
                update(Lead).values(
                    submitted_at=datetime.now(timezone.utc) - timedelta(seconds=61),
                )
            )
            await db.commit()
        await self.submit("VISITOR@example.com")
        self.assertEqual(await self.count(), 2)

    async def test_global_cap_is_shared_across_parallel_sessions(self):
        results = await asyncio.gather(
            *(self.submit(f"visitor{index}@example.com") for index in range(25)),
            return_exceptions=True,
        )
        self.assertEqual(sum(result is None for result in results), 20)
        self.assertEqual(
            sum(
                isinstance(result, contact_service.ContactRateLimitError)
                for result in results
            ),
            5,
        )
        self.assertEqual(await self.count(), 20)
        self.assertEqual(self.email.await_count, 20)

    async def test_failed_persistence_rolls_back_lead_without_sending_email(self):
        original = lead_query.add_lead

        async def fail_after_flush(db, values):
            await original(db, values)
            await db.execute(text("SELECT 1 / 0"))

        with patch.object(lead_query, "add_lead", fail_after_flush):
            with self.assertRaises(contact_service.ContactPersistenceError):
                await self.submit()
        self.assertEqual(await self.count(), 0)
        self.email.assert_not_awaited()
        # Failed persistence consumes no quota, so the same enquiry can be retried.
        await self.submit()
        self.assertEqual(await self.count(), 1)
        self.email.assert_awaited_once()

    async def test_email_failure_leaves_committed_enquiry_available(self):
        self.email.side_effect = RuntimeError("Email provider unavailable")
        await self.submit()
        self.assertEqual(await self.count(), 1)
        self.email.assert_awaited_once()
