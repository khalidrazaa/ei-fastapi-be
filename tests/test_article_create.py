"""Exercise manual draft creation without a database or an AI provider."""

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api.article import article_routes
from app.core.admin_security import require_admin
from app.db.models.article import Article
from app.db.session import get_db
from app.services import article_service

_BASE_PATH = "/v1/admin/articles"


class ArticleCreateTests(unittest.TestCase):
    def setUp(self):
        self.db = AsyncMock()
        self.lookup = self.enterContext(
            patch.object(
                article_service.article_query,
                "get_article_by_slug",
                new_callable=AsyncMock,
                return_value=None,
            )
        )
        self.create = self.enterContext(
            patch.object(
                article_service.article_query,
                "create_article",
                new_callable=AsyncMock,
                side_effect=lambda db, **values: Article(
                    id=7,
                    created_at=datetime.now(timezone.utc),
                    updated_at=None,
                    **values,
                ),
            )
        )
        self.app = FastAPI()
        self.app.dependency_overrides[require_admin] = lambda: object()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.include_router(article_routes.router, prefix=_BASE_PATH)
        self.client = self.enterContext(TestClient(self.app))

    def payload(self, **changes):
        return {
            "title": " A manual draft ",
            "slug": "A Manual Draft",
            "content": " First paragraph. ",
            **changes,
        }

    def test_creates_normalized_unpublished_draft_with_defaults(self):
        before = datetime.now(timezone.utc)
        response = self.client.post(_BASE_PATH, json=self.payload())
        after = datetime.now(timezone.utc)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], 7)
        self.assertEqual(data["title"], "A manual draft")
        self.assertEqual(data["slug"], "a-manual-draft")
        self.assertEqual(data["content"], "First paragraph.")
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["host_site"], "explainit.tech")
        self.assertEqual(data["language"], "en")
        self.assertEqual(data["schema_type"], "Article")
        self.assertEqual(data["tags"], [])
        self.assertEqual(data["keywords"], [])
        self.assertFalse(data["is_featured"])
        self.assertIsNone(data["published_at"])
        self.assertEqual(data["reading_time"], 1)
        drafted_at = datetime.fromisoformat(data["drafted_at"].replace("Z", "+00:00"))
        self.assertLessEqual(before, drafted_at)
        self.assertLessEqual(drafted_at, after)
        self.lookup.assert_awaited_once_with(self.db, "a-manual-draft")
        self.create.assert_awaited_once()

    def test_unfinished_draft_can_have_empty_content(self):
        response = self.client.post(_BASE_PATH, json=self.payload(content=""))
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()["content"])
        self.assertIsNone(response.json()["reading_time"])

    def test_editor_metadata_is_preserved_and_draft_timestamp_is_server_owned(self):
        response = self.client.post(
            _BASE_PATH,
            json=self.payload(
                category=" Technology ",
                tags=[" Python ", ""],
                keywords=[" API "],
                seo_title=" Search title ",
                meta_description=" Description ",
                host_site="other.example",
                language="hi",
                is_featured=True,
                featured_image_url="https://example.com/image.jpg",
                drafted_at="2000-01-01T00:00:00Z",
                published_at="2000-01-01T00:00:00Z",
            ),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["category"], "Technology")
        self.assertEqual(data["tags"], ["Python"])
        self.assertEqual(data["keywords"], ["API"])
        self.assertEqual(data["seo_title"], "Search title")
        self.assertEqual(data["meta_description"], "Description")
        self.assertEqual(data["host_site"], "other.example")
        self.assertEqual(data["language"], "hi")
        self.assertTrue(data["is_featured"])
        self.assertEqual(data["featured_image_url"], "https://example.com/image.jpg")
        self.assertFalse(data["drafted_at"].startswith("2000-"))
        self.assertIsNone(data["published_at"])

    def test_content_estimates_reading_time_when_not_explicitly_set(self):
        response = self.client.post(
            _BASE_PATH, json=self.payload(content="word " * 401)
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["reading_time"], 3)

    def test_invalid_required_fields_and_reading_time_return_useful_errors(self):
        for changes, detail in (
            ({"title": " "}, "Title is required."),
            ({"slug": " "}, "Slug is required."),
            ({"slug": "!!!"}, "Slug is invalid."),
            ({"reading_time": -1}, "Reading time must be 0 or greater."),
        ):
            with self.subTest(changes=changes):
                response = self.client.post(_BASE_PATH, json=self.payload(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail": detail})
        self.create.assert_not_awaited()

    def test_missing_fields_invalid_content_and_publish_request_are_rejected(self):
        for payload in (
            {},
            {"title": "Title", "slug": "title"},
            self.payload(content=None),
            self.payload(status="published"),
        ):
            with self.subTest(payload=payload):
                response = self.client.post(_BASE_PATH, json=payload)
                self.assertEqual(response.status_code, 422)
        self.create.assert_not_awaited()

    def test_duplicate_slug_is_rejected_before_creating(self):
        self.lookup.return_value = Article(id=3, slug="a-manual-draft")
        response = self.client.post(_BASE_PATH, json=self.payload())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Slug is already in use."})
        self.create.assert_not_awaited()

    def test_concurrent_slug_collision_rolls_back_and_returns_useful_error(self):
        self.lookup.side_effect = [None, Article(id=3, slug="a-manual-draft")]
        self.create.side_effect = IntegrityError("INSERT", {}, Exception("duplicate"))
        response = self.client.post(_BASE_PATH, json=self.payload())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Slug is already in use."})
        self.db.rollback.assert_awaited_once()

    def test_other_integrity_errors_are_not_misreported_as_duplicate_slugs(self):
        self.create.side_effect = IntegrityError("INSERT", {}, Exception("other failure"))
        with self.assertRaises(IntegrityError):
            self.client.post(_BASE_PATH, json=self.payload())
        self.db.rollback.assert_awaited_once()

    def test_creation_requires_admin_authentication(self):
        del self.app.dependency_overrides[require_admin]
        for headers in ({}, {"Authorization": "Bearer invalid"}):
            with self.subTest(headers=headers):
                response = self.client.post(
                    _BASE_PATH, json=self.payload(), headers=headers
                )
                self.assertEqual(response.status_code, 401)
        self.create.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
