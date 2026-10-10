"""Exercise article deletion, comments, and authentication in an isolated database."""

import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import JSON, MetaData, create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.article import article_routes
from app.core import security
from app.db.models.admin_user import AdminUser
from app.db.models.article import Article
from app.db.models.article_comment import ArticleComment
from app.db.session import get_db
from app.services import admin_auth_service

_SECRET = "isolated-article-delete-test-key"
_BASE_PATH = "/v1/admin/articles"


class AsyncSessionAdapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()


class ArticleDeleteTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(security, "SECRET_KEY", _SECRET))
        self.enterContext(patch.object(security, "ALGORITHM", "HS256"))
        self.enterContext(
            patch.object(
                admin_auth_service,
                "settings",
                SimpleNamespace(CORS_ORIGINS="https://admin.example.com"),
            )
        )
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys = ON")

        # SQLite needs only a DDL substitute for the unused PostgreSQL arrays.
        metadata = MetaData()
        article_table = Article.__table__.to_metadata(metadata)
        article_table.c.tags.type = JSON()
        article_table.c.keywords.type = JSON()
        ArticleComment.__table__.to_metadata(metadata)
        AdminUser.__table__.to_metadata(metadata)
        metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        self.db = AsyncSessionAdapter(self.session)
        for identifier in (1, 2, 3):
            self.session.add(
                Article(
                    id=identifier,
                    title=f"Article {identifier}",
                    slug=f"article-{identifier}",
                    host_site="explainit.tech",
                    status="published" if identifier == 2 else "draft",
                )
            )
        self.session.flush()
        for identifier, article_id in ((1, 1), (2, 1), (3, 2), (4, 3)):
            self.session.add(
                ArticleComment(
                    id=identifier,
                    article_id=article_id,
                    host_site="explainit.tech",
                    author_name="Reader",
                    content="A comment.",
                )
            )
        for identifier, active in (("active", True), ("inactive", False)):
            self.session.add(
                AdminUser(
                    id=identifier,
                    email=f"{identifier}@example.com",
                    phone=identifier,
                    full_name="Admin",
                    gender="other",
                    dob=date(1990, 1, 1),
                    is_active=active,
                )
            )
        self.session.commit()

        app = FastAPI()
        app.dependency_overrides[get_db] = lambda: self.db
        app.include_router(article_routes.router, prefix=_BASE_PATH)
        self.client = self.enterContext(TestClient(app))

    def token(self, email="active@example.com"):
        return jwt.encode(
            {
                "sub": email,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            _SECRET,
            algorithm="HS256",
        )

    def headers(self, email="active@example.com"):
        return {"Authorization": f"Bearer {self.token(email)}"}

    def article_ids(self):
        return list(self.session.scalars(select(Article.id).order_by(Article.id)))

    def comment_ids(self):
        return list(
            self.session.scalars(select(ArticleComment.id).order_by(ArticleComment.id))
        )

    def test_single_delete_removes_article_and_its_comments_only(self):
        response = self.client.delete(f"{_BASE_PATH}/1", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted_ids": [1], "deleted_count": 1})
        self.assertEqual(self.article_ids(), [2, 3])
        self.assertEqual(self.comment_ids(), [3, 4])

    def test_bulk_delete_is_atomic_and_deduplicates_ids(self):
        response = self.client.post(
            f"{_BASE_PATH}/bulk-delete",
            json={"article_ids": [2, 1, 2]},
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted_ids": [2, 1], "deleted_count": 2})
        self.assertEqual(self.article_ids(), [3])
        self.assertEqual(self.comment_ids(), [4])

    def test_missing_bulk_id_returns_404_without_deleting_existing_articles(self):
        response = self.client.post(
            f"{_BASE_PATH}/bulk-delete",
            json={"article_ids": [1, 99]},
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {
            "detail": "Articles not found: 99. No articles were deleted."
        })
        self.assertEqual(self.article_ids(), [1, 2, 3])
        self.assertEqual(self.comment_ids(), [1, 2, 3, 4])

    def test_missing_single_id_returns_404(self):
        response = self.client.delete(f"{_BASE_PATH}/99", headers=self.headers())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.article_ids(), [1, 2, 3])

    def test_failed_commit_rolls_back_articles_and_cascaded_comments(self):
        with patch.object(
            self.db, "commit", new_callable=AsyncMock,
            side_effect=RuntimeError("isolated commit failure"),
        ), patch.object(
            self.db, "rollback", wraps=self.db.rollback,
        ) as rollback:
            with self.assertRaisesRegex(RuntimeError, "isolated commit failure"):
                self.client.post(
                    f"{_BASE_PATH}/bulk-delete",
                    json={"article_ids": [1, 2]},
                    headers=self.headers(),
                )
            rollback.assert_awaited_once()
        self.assertEqual(self.article_ids(), [1, 2, 3])
        self.assertEqual(self.comment_ids(), [1, 2, 3, 4])

    def test_invalid_bulk_ids_and_single_ids_are_rejected(self):
        for article_ids in (
            [], [0], [-1], [True], [1.5], ["1"], [None], list(range(1, 502)),
        ):
            with self.subTest(article_ids=article_ids[:2]):
                response = self.client.post(
                    f"{_BASE_PATH}/bulk-delete",
                    json={"article_ids": article_ids},
                    headers=self.headers(),
                )
                self.assertEqual(response.status_code, 422)
        for identifier in ("0", "-1", "invalid"):
            with self.subTest(identifier=identifier):
                response = self.client.delete(
                    f"{_BASE_PATH}/{identifier}", headers=self.headers()
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.article_ids(), [1, 2, 3])
        self.assertEqual(self.comment_ids(), [1, 2, 3, 4])

    def test_deletion_requires_active_admin_authentication(self):
        for token, status in (
            (None, 401), ("invalid", 401),
            (self.token("inactive@example.com"), 403),
            (self.token("deleted@example.com"), 403),
        ):
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            for method, path, body in (
                ("DELETE", f"{_BASE_PATH}/1", None),
                ("POST", f"{_BASE_PATH}/bulk-delete", {"article_ids": [1, 2]}),
            ):
                with self.subTest(method=method, status=status):
                    response = self.client.request(
                        method, path, json=body, headers=headers
                    )
                    self.assertEqual(response.status_code, status)
        self.assertEqual(self.article_ids(), [1, 2, 3])

    def test_cookie_deletion_rejects_foreign_origin_and_accepts_allowed_origin(self):
        self.client.cookies.set("access_token", self.token())
        for method, path, body in (
            ("DELETE", f"{_BASE_PATH}/1", None),
            ("POST", f"{_BASE_PATH}/bulk-delete", {"article_ids": [2]}),
        ):
            for origin in (None, "https://evil.example"):
                headers = {"Origin": origin} if origin else {}
                with self.subTest(method=method, origin=origin):
                    response = self.client.request(
                        method, path, json=body, headers=headers
                    )
                    self.assertEqual(response.status_code, 403)
            response = self.client.request(
                method, path, json=body,
                headers={"Origin": "https://admin.example.com"},
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.article_ids(), [3])
        self.assertEqual(self.comment_ids(), [4])


if __name__ == "__main__":
    unittest.main()
