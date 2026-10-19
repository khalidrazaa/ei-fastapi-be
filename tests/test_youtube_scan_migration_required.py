"""Missing PostgreSQL scan-control columns yield actionable, safe service errors."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from sqlalchemy.exc import ProgrammingError

from app.services import popular_scan_settings as service


class DriverError(Exception):
    def __init__(self, message, sqlstate="42703", pgcode=None, diagnostic=None):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.pgcode = pgcode
        self.diag = diagnostic


def database_error(message, **changes):
    return ProgrammingError(
        "SELECT popular_scan_settings.youtube_scan_enabled, "
        "popular_scan_settings.popular_scan_enabled, "
        "popular_scan_settings.niche_scan_enabled, "
        "popular_scan_settings.region_codes FROM popular_scan_settings",
        {"private_parameter": "must not reach the API"},
        DriverError(message, **changes),
    )


def failing_database(error):
    return SimpleNamespace(
        execute=AsyncMock(side_effect=error), rollback=AsyncMock(),
        commit=AsyncMock(), add=Mock(),
    )


class YouTubeScanMigrationRequiredTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_reads_and_writes_map_only_missing_controls(self):
        entrypoints = (
            (service.get_or_create_popular_scan_settings, {}),
            (service.save_popular_scan_settings, {
                "region_codes": ["IN"], "max_results": 25,
                "youtube_scan_enabled": False,
            }),
            (service.save_popular_scan_regions, {
                "available_regions": [{"code": "IN", "name": "India"}],
            }),
        )
        for function, arguments in entrypoints:
            for column in (
                "youtube_scan_enabled", "popular_scan_enabled", "niche_scan_enabled"
            ):
                with self.subTest(function=function.__name__, column=column):
                    db = failing_database(database_error(
                        "<class 'asyncpg.exceptions.UndefinedColumnError'>: "
                        f"column popular_scan_settings.{column} does not exist"
                    ))
                    with self.assertRaises(
                        service.YouTubeScanMigrationRequiredError
                    ) as raised:
                        await function(db, **arguments)
                    self.assertEqual(
                        str(raised.exception),
                        "Apply the YouTube scan controls database migration "
                        "(011_youtube_scan_controls.sql or c03_youtube_scan_controls), "
                        "then reload.",
                    )
                    self.assertNotIn("SELECT", str(raised.exception))
                    self.assertNotIn("must not reach the API", str(raised.exception))
                    db.rollback.assert_awaited_once()
                    db.commit.assert_not_awaited()
                    db.add.assert_not_called()
                    # No automatic schema repair, default row or retry occurs.
                    db.execute.assert_awaited_once()

    async def test_postgresql_diagnostic_and_psycopg_pgcode_are_supported(self):
        for original in (
            database_error(
                'column "popular_scan_settings"."niche_scan_enabled" does not exist'
            ),
            database_error(
                'column "popular_scan_enabled" of relation "popular_scan_settings" '
                'does not exist', sqlstate=None, pgcode="42703",
            ),
            database_error(
                "Localized driver message", diagnostic=SimpleNamespace(
                    column_name="youtube_scan_enabled",
                    table_name="popular_scan_settings",
                ),
            ),
        ):
            with self.subTest(original=original.orig):
                db = failing_database(original)
                with self.assertRaises(service.YouTubeScanMigrationRequiredError):
                    await service.get_or_create_popular_scan_settings(db)
                db.rollback.assert_awaited_once()

    async def test_unrelated_database_errors_are_not_misclassified(self):
        for original in (
            database_error("column popular_scan_settings.region_codes does not exist"),
            database_error("column unrelated.youtube_scan_enabled does not exist"),
            database_error(
                "column popular_scan_settings.youtube_scan_enabled does not exist",
                sqlstate="42501",
            ),
            database_error(
                "column popular_scan_settings.youtube_scan_enabled does not exist",
                sqlstate=None,
            ),
            database_error(
                'column "region_codes" does not exist\nLINE 1: SELECT '
                'popular_scan_settings.youtube_scan_enabled FROM popular_scan_settings'
            ),
        ):
            with self.subTest(original=original.orig):
                db = failing_database(original)
                with self.assertRaises(ProgrammingError) as raised:
                    await service.get_or_create_popular_scan_settings(db)
                self.assertIs(raised.exception, original)
                db.rollback.assert_not_awaited()

    async def test_scan_guards_fail_closed_when_migration_is_missing(self):
        for scan_type in ("popular", "niche"):
            with self.subTest(scan_type=scan_type):
                db = failing_database(database_error(
                    "column popular_scan_settings.youtube_scan_enabled does not exist"
                ))
                with self.assertRaises(service.YouTubeScanMigrationRequiredError):
                    await service.ensure_youtube_scan_enabled(db, scan_type)
                db.rollback.assert_awaited_once()
                db.commit.assert_not_awaited()
