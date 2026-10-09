"""Exercise lead schema changes locally without connecting to deployment data."""

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import MetaData, create_engine, insert, inspect, select, text

from app.db.models.lead import Lead

VERSIONS_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def load_migration(filename):
    spec = importlib.util.spec_from_file_location(
        filename[:-3], VERSIONS_PATH / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LeadMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.original = load_migration(
            "7d2a4c9e81b0_add_leads_and_notification_outbox.py"
        )
        self.cleanup = load_migration("b6f3e94d2a10_remove_lead_notification_outbox.py")
        self.apply(self.original.upgrade)

    def apply(self, migration):
        with self.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration()

    def assert_current_schema(self):
        metadata = MetaData()
        Lead.__table__.to_metadata(metadata)
        with self.engine.connect() as conn:
            self.assertEqual(
                compare_metadata(MigrationContext.configure(conn), metadata), []
            )

    def test_fresh_chain_matches_model_and_can_be_recreated(self):
        self.assertEqual(self.cleanup.down_revision, self.original.revision)
        self.apply(self.cleanup.upgrade)
        self.assert_current_schema()
        self.apply(self.cleanup.downgrade)
        self.apply(self.original.downgrade)
        self.assertEqual(inspect(self.engine).get_table_names(), [])
        self.apply(self.original.upgrade)
        self.apply(self.cleanup.upgrade)
        self.assert_current_schema()

    def test_cleanup_and_downgrade_preserve_leads_but_do_not_restore_events(self):
        submitted = datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc)
        with self.engine.begin() as conn:
            conn.execute(
                insert(Lead).values(
                    id=1,
                    name="Visitor",
                    email="visitor@example.com",
                    message="Consulting enquiry",
                    host_site="explainit.tech",
                    submitted_at=submitted,
                    updated_at=submitted,
                )
            )
            conn.execute(
                text(
                    "INSERT INTO lead_notification_outbox "
                    "(lead_id, available_at, created_at) "
                    "VALUES (1, :submitted, :submitted)"
                ),
                {"submitted": submitted.isoformat()},
            )
        self.apply(self.cleanup.upgrade)
        self.assert_current_schema()
        with self.engine.connect() as conn:
            self.assertEqual(
                conn.execute(select(Lead.id, Lead.message)).one(),
                (1, "Consulting enquiry"),
            )
        self.apply(self.cleanup.downgrade)
        inspector = inspect(self.engine)
        self.assertIn("lead_notification_outbox", inspector.get_table_names())
        self.assertEqual(
            {
                index["name"]
                for index in inspector.get_indexes("lead_notification_outbox")
            },
            {"ix_lead_notification_ready", "ix_lead_notification_lease"},
        )
        with self.engine.connect() as conn:
            self.assertEqual(
                conn.execute(
                    text("SELECT COUNT(*) FROM lead_notification_outbox")
                ).scalar_one(),
                0,
            )
            self.assertEqual(conn.execute(select(Lead.id)).scalar_one(), 1)
        self.apply(self.cleanup.upgrade)
        self.assert_current_schema()
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(Lead.id)).scalar_one(), 1)
