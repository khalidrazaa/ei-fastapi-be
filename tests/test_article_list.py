"""Exercise article list filters through the route and real isolated SQL."""

import asyncio
import unittest
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.article import article_routes
from app.db.models.article import Article
from app.db.session import get_db
from app.services import article_service

_BASE_PATH = "/v1/admin/articles"


class AsyncSessionAdapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)


class ArticleListTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        article_table = Article.__table__.to_metadata(metadata)
        # The list does not use PostgreSQL arrays; substitute JSON for SQLite DDL.
        article_table.c.tags.type = JSON()
        article_table.c.keywords.type = JSON()
        metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        self.db = AsyncSessionAdapter(self.session)
        for identifier, status, host_site in (
            (1, "published", "explainit.tech"),
            (2, "draft", "explainit.tech"),
            (3, "published", "other.example"),
            (4, "published", "explainit.tech"),
            (5, "draft", "other.example"),
        ):
            self.session.add(
                Article(
                    id=identifier,
                    title=f"Article {identifier}",
                    slug=f"article-{identifier}",
                    host_site=host_site,
                    status=status,
                    created_at=datetime(2026, 10, identifier, tzinfo=timezone.utc),
                )
            )
        self.session.commit()

        app = FastAPI()
        app.dependency_overrides[get_db] = lambda: self.db
        app.include_router(article_routes.router, prefix=_BASE_PATH)
        self.client = self.enterContext(TestClient(app))

    def list_ids(self, **params):
        response = self.client.get(_BASE_PATH, params=params)
        self.assertEqual(response.status_code, 200)
        return [article["id"] for article in response.json()]

    def test_published_query_excludes_drafts_and_orders_newest_first(self):
        response = self.client.get(_BASE_PATH, params={"status": "published"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([article["id"] for article in response.json()], [4, 3, 1])
        self.assertTrue(
            all(article["status"] == "published" for article in response.json())
        )

    def test_unfiltered_and_draft_queries_remain_available(self):
        self.assertEqual(self.list_ids(), [5, 4, 3, 2, 1])
        self.assertEqual(self.list_ids(status="draft"), [5, 2])

    def test_status_query_keeps_existing_case_and_whitespace_normalization(self):
        self.assertEqual(self.list_ids(status=" Published "), [4, 3, 1])

    def test_limit_is_applied_after_status_filter_and_ordering(self):
        self.assertEqual(self.list_ids(status="published", limit=2), [4, 3])

    def test_invalid_status_preserves_existing_bad_request_response(self):
        response = self.client.get(_BASE_PATH, params={"status": "archived"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": "Status must be either `draft` or `published`."},
        )

    def test_invalid_limits_remain_rejected(self):
        for limit in (0, 501, "invalid"):
            with self.subTest(limit=limit):
                response = self.client.get(_BASE_PATH, params={"limit": limit})
                self.assertEqual(response.status_code, 422)

    def test_status_host_and_limit_filters_combine_in_shared_query(self):
        articles = asyncio.run(
            article_service.list_articles(
                self.db,
                status="published",
                host_site="https://www.explainit.tech/articles",
                limit=1,
            )
        )
        self.assertEqual([article.id for article in articles], [4])

    def test_public_list_keeps_host_scoped_published_filter(self):
        articles = asyncio.run(
            article_service.list_published_articles_for_host(
                self.db, host_site="explainit.tech"
            )
        )
        self.assertEqual([article.id for article in articles], [4, 1])


if __name__ == "__main__":
    unittest.main()
