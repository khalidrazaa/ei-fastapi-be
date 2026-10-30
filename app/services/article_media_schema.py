"""Identify only missing article-media schema, without exposing SQL or parameters."""

import re
import sqlite3

from sqlalchemy.exc import DBAPIError

from app.db.models.article_image import ArticleImage, ArticleImport

_MEDIA_COLUMNS = {
    model.__tablename__: set(model.__table__.columns.keys())
    for model in (ArticleImage, ArticleImport)
}
_IDENTIFIER = r'(?:"[^"]+"|[A-Za-z_][\w$]*)'
_QUALIFIED_IDENTIFIER = rf'{_IDENTIFIER}(?:\.{_IDENTIFIER})*'
_MISSING_TABLE = re.compile(
    rf'\brelation\s+(?P<table>{_QUALIFIED_IDENTIFIER})\s+does not exist\b', re.I,
)
_MISSING_COLUMN = re.compile(
    rf'\bcolumn\s+(?P<table>{_QUALIFIED_IDENTIFIER})\.'
    rf'(?P<column>{_IDENTIFIER})\s+does not exist\b', re.I,
)
_MISSING_RELATION_COLUMN = re.compile(
    rf'\bcolumn\s+(?P<column>{_IDENTIFIER})\s+of\s+relation\s+'
    rf'(?P<table>{_QUALIFIED_IDENTIFIER})\s+does not exist\b', re.I,
)
_SQLITE_MISSING_TABLE = re.compile(
    rf'\bno such table:\s*(?P<table>{_QUALIFIED_IDENTIFIER})\s*$', re.I,
)
_SQLITE_MISSING_COLUMN = re.compile(
    rf'\bno such column:\s*(?P<table>{_QUALIFIED_IDENTIFIER})\.'
    rf'(?P<column>{_IDENTIFIER})\s*$', re.I,
)
_SQLITE_MISSING_INSERT_COLUMN = re.compile(
    rf'\btable\s+(?P<table>{_QUALIFIED_IDENTIFIER})\s+has no column named\s+'
    rf'(?P<column>{_IDENTIFIER})\s*$', re.I,
)


class ArticleMediaMigrationRequiredError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Apply the article image upload database migration "
            "(012_article_images.sql or c04_article_images) to the database "
            "used by this API, then retry."
        )


def _table_name(identifier: str) -> str:
    # Drivers may qualify a missing relation with its schema.
    return identifier.replace('"', '').rsplit('.', 1)[-1]


def _owned_column(table: str, column: str) -> bool:
    return column.strip('"') in _MEDIA_COLUMNS.get(_table_name(table), set())


def is_missing_article_media_schema(error: DBAPIError) -> bool:
    original = error.orig
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    # Do not inspect str(error): it includes query text and parameter values,
    # which can mention our schema even when the actual error is unrelated.
    diagnosis = str(original).partition("\n")[0]
    diagnostic = getattr(original, "diag", None)
    table = getattr(diagnostic, "table_name", None)
    column = getattr(diagnostic, "column_name", None)
    if sqlstate == "42P01":
        match = _MISSING_TABLE.search(diagnosis)
        return (table in _MEDIA_COLUMNS or
                (match is not None and _table_name(match["table"]) in _MEDIA_COLUMNS))
    if sqlstate == "42703":
        if table and column and _owned_column(table, column):
            return True
        for pattern in (_MISSING_COLUMN, _MISSING_RELATION_COLUMN):
            match = pattern.search(diagnosis)
            if match is not None and _owned_column(match["table"], match["column"]):
                return True
        return False
    if isinstance(original, sqlite3.OperationalError):
        match = _SQLITE_MISSING_TABLE.search(diagnosis)
        if match is not None:
            return _table_name(match["table"]) in _MEDIA_COLUMNS
        for pattern in (_SQLITE_MISSING_COLUMN, _SQLITE_MISSING_INSERT_COLUMN):
            match = pattern.search(diagnosis)
            if match is not None and _owned_column(match["table"], match["column"]):
                return True
    return False
