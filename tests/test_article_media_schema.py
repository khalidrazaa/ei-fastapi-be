"""Only missing article-media schema becomes an actionable migration error."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy.exc import ProgrammingError

from app.services import article_media_service
from app.services.article_media_schema import (
    ArticleMediaMigrationRequiredError,
    is_missing_article_media_schema,
)


class DriverError(Exception):
    def __init__(self, message, *, sqlstate="42P01", pgcode=None, diagnostic=None):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.pgcode = pgcode
        self.diag = diagnostic


def database_error(message, **changes):
    return ProgrammingError(
        "SELECT article_imports.response, article_images.mime_type FROM article_imports, article_images",
        {"private_parameter": "must not reach the API"}, DriverError(message, **changes),
    )


class ArticleMediaSchemaTests(unittest.IsolatedAsyncioTestCase):
    def missing_errors(self):
        return (
            database_error('<class \'asyncpg.exceptions.UndefinedTableError\'>: relation "article_imports" does not exist'),
            database_error('relation "public"."article_images" does not exist'),
            database_error('column article_imports.response does not exist', sqlstate="42703"),
            database_error('column "public"."article_images"."storage_name" does not exist', sqlstate="42703"),
            database_error('column "mime_type" of relation "article_images" does not exist', sqlstate=None, pgcode="42703"),
            database_error("Localized table diagnosis", diagnostic=SimpleNamespace(table_name="article_imports")),
            database_error("Localized column diagnosis", sqlstate="42703", diagnostic=SimpleNamespace(table_name="article_images", column_name="original_article_id")),
        )

    def unrelated_errors(self):
        return (
            database_error('relation "unrelated" does not exist'),
            database_error('column unrelated.response does not exist', sqlstate="42703"),
            database_error('column article_imports.typo_in_query does not exist', sqlstate="42703"),
            database_error('relation "article_imports" does not exist', sqlstate="42501"),
            database_error('relation "article_imports" does not exist', sqlstate=None),
            database_error('permission denied for table article_images', sqlstate="42501"),
            database_error('column "unrelated_column" does not exist\nLINE 1: SELECT article_imports.response FROM article_imports', sqlstate="42703"),
            database_error("Localized unrelated column", sqlstate="42703", diagnostic=SimpleNamespace(table_name="articles", column_name="id")),
        )

    async def test_postgresql_missing_tables_columns_and_diagnostics_are_recognized(self):
        for error in self.missing_errors():
            with self.subTest(diagnosis=str(error.orig)):
                self.assertTrue(is_missing_article_media_schema(error))

    async def test_unrelated_failures_are_not_inferred_from_query_or_parameters(self):
        for error in self.unrelated_errors():
            with self.subTest(diagnosis=str(error.orig)):
                self.assertFalse(is_missing_article_media_schema(error))

    async def test_import_rolls_back_and_translates_missing_postgresql_schema(self):
        for error in self.missing_errors():
            with self.subTest(diagnosis=str(error.orig)):
                db = SimpleNamespace(execute=AsyncMock(side_effect=error), rollback=AsyncMock())
                with self.assertRaises(ArticleMediaMigrationRequiredError) as raised:
                    await article_media_service.import_article(db,
                        payload={"title": "Draft", "slug": "draft", "content": "Body"},
                        manifest={}, request_id=str(uuid4()), images=[], admin_id="admin")
                self.assertIn("012_article_images.sql or c04_article_images", str(raised.exception))
                self.assertNotIn("SELECT", str(raised.exception))
                self.assertNotIn("must not reach the API", str(raised.exception))
                db.rollback.assert_awaited_once()
                db.execute.assert_awaited_once()

    async def test_public_media_read_rolls_back_only_for_matching_schema_errors(self):
        for error in self.missing_errors():
            with self.subTest(diagnosis=str(error.orig)):
                db = SimpleNamespace(execute=AsyncMock(side_effect=error), rollback=AsyncMock())
                with self.assertRaises(ArticleMediaMigrationRequiredError):
                    await article_media_service.get_public_image(db, 1, uuid4().hex + ".svg")
                db.rollback.assert_awaited_once()
        for error in self.unrelated_errors():
            with self.subTest(diagnosis=str(error.orig)):
                db = SimpleNamespace(execute=AsyncMock(side_effect=error), rollback=AsyncMock())
                with self.assertRaises(ProgrammingError) as raised:
                    await article_media_service.get_public_image(db, 1, uuid4().hex + ".svg")
                self.assertIs(raised.exception, error)
                db.rollback.assert_not_awaited()

    async def test_import_preserves_nonmatching_database_error_after_rollback(self):
        for error in self.unrelated_errors():
            with self.subTest(diagnosis=str(error.orig)):
                db = SimpleNamespace(execute=AsyncMock(side_effect=error), rollback=AsyncMock())
                with self.assertRaises(ProgrammingError) as raised:
                    await article_media_service.import_article(db,
                        payload={"title": "Draft", "slug": "draft", "content": "Body"},
                        manifest={}, request_id=str(uuid4()), images=[], admin_id="admin")
                self.assertIs(raised.exception, error)
                db.rollback.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
