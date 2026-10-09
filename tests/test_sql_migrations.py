"""Verify SQL migration changes and history commit together in an isolated DB."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from migrations import migration_script


class SqlMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.enterContext(patch.object(migration_script, "engine", self.engine))
        self.directory = self.enterContext(TemporaryDirectory())
        self.path = Path(self.directory) / "009_test.sql"
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY)"))
            connection.execute(text(
                "CREATE TABLE schema_migrations "
                "(filename TEXT PRIMARY KEY, applied_at TIMESTAMP)"
            ))

    def sample_ids(self):
        with self.engine.connect() as connection:
            return list(connection.execute(text("SELECT id FROM sample")).scalars())

    def test_success_commits_changes_and_records_filename(self):
        self.path.write_text("INSERT INTO sample VALUES (1);", encoding="utf-8")
        migration_script.run_sql_file(self.path)
        self.assertEqual(self.sample_ids(), [1])
        self.assertTrue(migration_script.has_migration_run(self.path.name))

    def test_statement_failure_rolls_back_changes_and_history(self):
        self.path.write_text(
            "INSERT INTO sample VALUES (1); INSERT INTO missing_table VALUES (2);",
            encoding="utf-8",
        )
        with self.assertRaises(SQLAlchemyError):
            migration_script.run_sql_file(self.path)
        self.assertEqual(self.sample_ids(), [])
        self.assertFalse(migration_script.has_migration_run(self.path.name))

    def test_history_failure_rolls_back_migration_changes(self):
        with self.engine.begin() as connection:
            migration_script.record_migration(self.path.name, connection)
        self.path.write_text("INSERT INTO sample VALUES (1);", encoding="utf-8")
        with self.assertRaises(IntegrityError):
            migration_script.run_sql_file(self.path)
        self.assertEqual(self.sample_ids(), [])
