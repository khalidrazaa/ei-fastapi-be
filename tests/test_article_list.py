"""Exercise article list filters through the route and real isolated SQL."""

import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.article import article_routes, public_article_routes
from app.core.admin_security import require_admin
from app.core.public_api_security import verify_public_app_access
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
        app.dependency_overrides[require_admin] = lambda: object()
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[verify_public_app_access] = lambda: "explainit.tech"
        app.include_router(article_routes.router, prefix=_BASE_PATH)
        app.include_router(public_article_routes.router, prefix="/v1/public/articles")
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

    def test_category_options_combine_statuses_and_hosts_without_loading_articles(self):
        for identifier, category in ((1, " Technology "), (2, "Guides"), (3, "Technology"), (4, ""), (5, None)):
            self.session.get(Article, identifier).category = category
        self.session.commit()
        with patch.object(self.db, "execute", wraps=self.db.execute) as execute:
            response = self.client.get(f"{_BASE_PATH}/categories")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["Guides", "Technology"])
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(list(execute.call_args.args[0].selected_columns.keys()), ["category"])

    def test_category_options_allow_an_empty_collection_and_preserve_numeric_detail_route(self):
        response = self.client.get(f"{_BASE_PATH}/categories")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        detail = self.client.get(f"{_BASE_PATH}/1")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], 1)
        self.assertEqual(self.client.get(f"{_BASE_PATH}/999").status_code, 404)

    def test_category_options_require_admin_authentication(self):
        app = FastAPI()
        app.dependency_overrides[get_db] = lambda: self.db
        app.include_router(article_routes.router, prefix=_BASE_PATH)
        with TestClient(app) as client:
            self.assertEqual(client.get(f"{_BASE_PATH}/categories").status_code, 401)

    def page(self, path=_BASE_PATH, **params):
        response = self.client.get(path, params={"page": 1, "size": 2, **params})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_page_envelope_counts_all_matches_and_slices_in_database(self):
        first = self.page(status="published")
        second = self.page(status="published", page=2)
        self.assertEqual([article["id"] for article in first["items"]], [4, 3])
        self.assertEqual([article["id"] for article in second["items"]], [1])
        self.assertEqual(
            {key: first[key] for key in ("total", "page", "size", "total_pages", "has_next", "has_previous")},
            {"total": 3, "page": 1, "size": 2, "total_pages": 2, "has_next": True, "has_previous": False},
        )
        self.assertFalse(second["has_next"])
        self.assertTrue(second["has_previous"])
        self.assertEqual(first["categories"], [{"name": "Uncategorized", "count": 3}])
        self.assertEqual(first["category_total"], 3)

    def test_page_size_defaults_and_validation(self):
        for params in ({"page": 1}, {"size": 1}):
            response = self.client.get(_BASE_PATH, params=params)
            self.assertEqual(response.status_code, 200)
            self.assertIsInstance(response.json(), dict)
        for path in (_BASE_PATH, "/v1/public/articles"):
            for params in ({"page": 0}, {"page": -1}, {"page": "invalid"}, {"size": 0}, {"size": 101}, {"size": "invalid"}):
                with self.subTest(path=path, params=params):
                    self.assertEqual(self.client.get(path, params=params).status_code, 422)

    def test_empty_and_out_of_range_pages_keep_the_envelope(self):
        for params, total in (({"category": "Missing"}, 0), ({"page": 10}, 5)):
            data = self.page(**params)
            self.assertEqual(data["items"], [])
            self.assertEqual(data["total"], total)
            self.assertFalse(data["has_next"])
            self.assertEqual(data["total_pages"], 0 if total == 0 else 3)
            self.assertEqual(data["category_total"], 5)

    def test_category_search_and_counts_span_all_pages(self):
        for identifier, category in ((1, " Alpha "), (2, "Draft only"), (3, "Alpha"), (4, "Beta"), (5, "")):
            article = self.session.get(Article, identifier)
            article.category = category
        self.session.get(Article, 1).title = "A 100% guide_with\\examples"
        self.session.commit()
        data = self.page(status=" Published ", category=" Alpha ", search="100%", size=1)
        self.assertEqual([article["id"] for article in data["items"]], [1])
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["category_total"], 3)
        self.assertEqual(data["categories"], [{"name": "Alpha", "count": 2}, {"name": "Beta", "count": 1}])
        for search in ("%", "_", "\\", "GUIDE"):
            with self.subTest(search=search):
                self.assertEqual([article["id"] for article in self.page(search=search)["items"]], [1])
        self.assertEqual([article["id"] for article in self.page(search="article-3")["items"]], [3])
        self.assertEqual([article["id"] for article in self.page(status="draft", category="Uncategorized")["items"]], [5])
        invalid = self.client.get(_BASE_PATH, params={"page": 1, "status": "archived"})
        self.assertEqual(invalid.status_code, 400)

    def test_public_pages_scope_every_count_and_item_to_published_host(self):
        first = self.page("/v1/public/articles", size=1)
        second = self.page("/v1/public/articles", page=2, size=1)
        self.assertEqual([article["id"] for article in first["items"]], [4])
        self.assertEqual([article["id"] for article in second["items"]], [1])
        self.assertEqual(first["total"], 2)
        self.assertEqual(first["total_pages"], 2)
        self.assertNotIn("categories", first)
        self.assertEqual(first["has_next"], True)
        self.assertEqual(second["has_next"], False)
        legacy = self.client.get("/v1/public/articles", params={"limit": 1})
        self.assertEqual([article["id"] for article in legacy.json()], [4])

    def test_more_than_500_articles_are_reachable_with_stable_timestamp_ties(self):
        timestamp = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.session.add_all([
            Article(id=identifier, title=f"Article {identifier}", slug=f"article-{identifier}",
                    host_site="explainit.tech", status="published", created_at=timestamp)
            for identifier in range(6, 607)
        ])
        self.session.commit()
        identifiers = []
        for page in range(1, 8):
            data = self.page("/v1/public/articles", page=page, size=100)
            identifiers.extend(article["id"] for article in data["items"])
            self.assertEqual(data["total"], 603)
            self.assertEqual(data["total_pages"], 7)
            self.assertEqual(data["has_next"], page < 7)
        self.assertEqual(identifiers, [*range(606, 5, -1), 4, 1])

    def test_pagination_does_not_bypass_route_authentication(self):
        app = FastAPI()
        app.dependency_overrides[get_db] = lambda: self.db
        app.include_router(article_routes.router, prefix=_BASE_PATH)
        app.include_router(public_article_routes.router, prefix="/v1/public/articles")
        with TestClient(app) as client:
            self.assertEqual(client.get(_BASE_PATH, params={"page": 1}).status_code, 401)
            self.assertEqual(client.get("/v1/public/articles", params={"page": 1, "host_site": "explainit.tech"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
