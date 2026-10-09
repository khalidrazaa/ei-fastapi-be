"""Check protected lead authentication through HTTP and an isolated database."""

import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.admin import admin_routes
from app.api.auth import auth_routes
from app.core import security
from app.core.admin_security import require_admin
from app.db.models.admin_user import AdminUser
from app.db.session import get_db
from app.services import admin_auth_service

_SECRET = "isolated-admin-test-key"


class AsyncSessionAdapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, query):
        return self.session.execute(query)


class LeadAdminAuthTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(security, "SECRET_KEY", _SECRET))
        self.enterContext(patch.object(security, "ALGORITHM", "HS256"))
        self.enterContext(patch.object(security, "ACCESS_TOKEN_EXPIRE_MINUTES", 30))
        self.enterContext(
            patch.object(
                admin_auth_service,
                "settings",
                SimpleNamespace(
                    CORS_ORIGINS="https://admin.example.com,http://localhost:3000,*"
                ),
            )
        )
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        AdminUser.__table__.create(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        for identifier, active in (("active", True), ("inactive", False)):
            self.session.add(
                AdminUser(
                    id=identifier,
                    email=f"{identifier}@example.com",
                    phone=identifier,
                    full_name="Admin",
                    gender="unspecified",
                    dob=date(1990, 1, 1),
                    is_active=active,
                )
            )
        self.session.commit()

        app = FastAPI()
        app.dependency_overrides[get_db] = lambda: AsyncSessionAdapter(self.session)
        app.include_router(admin_routes.router, prefix="/v1/admin")
        app.include_router(auth_routes.router, prefix="/v1/auth")
        self.app = app
        self.create_admin = self.enterContext(
            patch.object(
                admin_routes,
                "create_admin_service",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id="created-admin"),
            )
        )

        @app.get("/v1/admin/leads")
        @app.patch("/v1/admin/leads")
        async def protected(admin: AdminUser = Depends(require_admin)):
            return {"admin_id": admin.id}

        self.client = self.enterContext(TestClient(app))

    def token(self, email="active@example.com", **claims):
        payload = {
            "sub": email,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
        payload.update(claims)
        return jwt.encode(payload, _SECRET, algorithm="HS256")

    def use_cookie(self, token=None):
        self.client.cookies.set("access_token", token or self.token())

    def test_valid_existing_otp_token_cookie_and_bearer(self):
        token = security.create_access_token({"sub": "active@example.com"})
        self.use_cookie(token)
        self.assertEqual(self.client.get("/v1/admin/leads").json(), {
            "admin_id": "active"
        })
        self.client.cookies.clear()
        response = self.client.get(
            "/v1/admin/leads", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"admin_id": "active"})

    def test_otp_login_cookie_authenticates_http_loopback_lead_requests(self):
        for base_url, headers in (
            ("http://localhost", {}),
            ("http://127.0.0.1", {}),
            ("http://localhost", {"Host": "[::1]"}),
        ):
            with self.subTest(base_url=base_url, headers=headers):
                with patch.object(
                    auth_routes, "verify_otp_service", new_callable=AsyncMock,
                    return_value={"access_token": self.token()},
                ), TestClient(self.app, base_url=base_url) as client:
                    response = client.post(
                        "/v1/auth/verify-otp",
                        json={"email": "active@example.com", "otp": "123456"},
                        headers=headers,
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), {
                        "status": True,
                        "token_type": "bearer",
                        "message": "OTP verified successfully",
                    })
                    cookie_header = response.headers["set-cookie"]
                    self.assertNotIn("Secure", cookie_header)
                    self.assertIn("HttpOnly", cookie_header)
                    self.assertIn("SameSite=lax", cookie_header)
                    self.assertIn("Max-Age=1800", cookie_header)
                    self.assertEqual(
                        client.get("/v1/admin/leads", headers=headers).json(),
                        {"admin_id": "active"},
                    )

    def test_otp_cookie_remains_secure_for_remote_http_hosts(self):
        with patch.object(
            auth_routes, "verify_otp_service", new_callable=AsyncMock,
            return_value={"access_token": self.token()},
        ), TestClient(self.app, base_url="http://api.example.com") as client:
            response = client.post(
                "/v1/auth/verify-otp",
                json={"email": "active@example.com", "otp": "123456"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("Secure", response.headers["set-cookie"])
            self.assertEqual(client.get("/v1/admin/leads").status_code, 401)

    def test_https_otp_login_retains_secure_cookie_and_configured_expiry(self):
        with patch.object(security, "ACCESS_TOKEN_EXPIRE_MINUTES", 17), patch.object(
            auth_routes, "verify_otp_service", new_callable=AsyncMock,
            return_value={"access_token": self.token()},
        ), TestClient(self.app, base_url="https://api.example.com") as client:
            response = client.post(
                "/v1/auth/verify-otp",
                json={"email": "active@example.com", "otp": "123456"},
            )
            self.assertEqual(response.status_code, 200)
            cookie_header = response.headers["set-cookie"]
            self.assertIn("Secure", cookie_header)
            self.assertIn("HttpOnly", cookie_header)
            self.assertIn("SameSite=lax", cookie_header)
            self.assertIn("Max-Age=1020", cookie_header)
            self.assertEqual(client.get("/v1/admin/leads").status_code, 200)

    def test_logout_clears_cookie_issued_by_otp_login(self):
        with patch.object(
            auth_routes, "verify_otp_service", new_callable=AsyncMock,
            return_value={"access_token": self.token()},
        ), TestClient(self.app, base_url="http://localhost") as client:
            client.post(
                "/v1/auth/verify-otp",
                json={"email": "active@example.com", "otp": "123456"},
            )
            self.assertEqual(client.get("/v1/admin/leads").status_code, 200)
            self.assertEqual(client.post("/v1/auth/logout").status_code, 200)
            self.assertEqual(client.get("/v1/admin/leads").status_code, 401)

    def test_missing_invalid_expired_and_incomplete_tokens_are_unauthorized(self):
        now = datetime.now(timezone.utc)
        tokens = [
            None,
            "malformed",
            self.token(exp=now - timedelta(seconds=10)),
            jwt.encode({"sub": "active@example.com"}, _SECRET, algorithm="HS256"),
            self.token(sub=""),
            self.token(sub=None),
            self.token(exp=None),
            jwt.encode({"exp": now + timedelta(minutes=1)}, _SECRET, algorithm="HS256"),
            jwt.encode(
                {"sub": "active@example.com", "exp": now + timedelta(minutes=1)},
                "wrong-key",
                algorithm="HS256",
            ),
        ]
        for token in tokens:
            with self.subTest(token_present=token is not None):
                self.client.cookies.clear()
                if token is not None:
                    self.use_cookie(token)
                response = self.client.get("/v1/admin/leads")
                self.assertEqual(response.status_code, 401)
                self.assertEqual(
                    response.json(), {"detail": "Authentication required."}
                )
                self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")

    def test_inactive_and_deleted_admins_are_forbidden(self):
        for email in ("inactive@example.com", "deleted@example.com"):
            with self.subTest(email=email):
                self.use_cookie(self.token(email))
                response = self.client.get("/v1/admin/leads")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"detail": "Admin access required."})

    def test_cookie_mutations_accept_configured_and_same_http_origins(self):
        self.use_cookie()
        for origin in (
            "https://admin.example.com",
            "http://localhost:3000",
            "http://testserver",
            "https://admin.example.com:443",
        ):
            with self.subTest(origin=origin):
                response = self.client.patch(
                    "/v1/admin/leads", headers={"Origin": origin}
                )
                self.assertEqual(response.status_code, 200)

    def test_cookie_mutations_reject_missing_malformed_and_foreign_origins(self):
        self.use_cookie()
        for origin in (
            None,
            "null",
            "https://evil.example",
            "http://admin.example.com",
            "https://admin.example.com:444",
            "https://admin.example.com/path",
            "https://admin.example.com.evil.example",
            "https://admin.example.com@evil.test",
            "https://admin.example.com:bad",
            "*",
        ):
            with self.subTest(origin=origin):
                headers = {} if origin is None else {"Origin": origin}
                response = self.client.patch("/v1/admin/leads", headers=headers)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {
                    "detail": "Request origin is not allowed."
                })

    def test_bearer_mutation_does_not_require_cookie_csrf_origin(self):
        self.use_cookie("invalid-cookie")
        response = self.client.patch(
            "/v1/admin/leads",
            headers={
                "Authorization": f"Bearer {self.token()}",
                "Origin": "https://other.test",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_invalid_authorization_never_falls_back_to_cookie(self):
        self.use_cookie()
        for authorization in ("", "Basic credentials", "Bearer", "Bearer invalid"):
            with self.subTest(authorization=authorization):
                response = self.client.patch(
                    "/v1/admin/leads",
                    headers={
                        "Authorization": authorization,
                        "Origin": "https://admin.example.com",
                    },
                )
                self.assertEqual(response.status_code, 401)

    def test_admin_enrollment_requires_active_auth_before_creation_service(self):
        payload = {
            "email": "new-admin@example.com",
            "phone": "+12025550198",
            "full_name": "New Admin",
            "gender": "other",
            "dob": "1990-01-01",
        }
        cases = (
            (None, "https://admin.example.com", 401),
            (self.token("inactive@example.com"), "https://admin.example.com", 403),
            (self.token(), "https://evil.example", 403),
            (self.token(), None, 403),
        )
        for token, origin, expected_status in cases:
            with self.subTest(origin=origin, status=expected_status):
                self.client.cookies.clear()
                if token is not None:
                    self.use_cookie(token)
                headers = {} if origin is None else {"Origin": origin}
                response = self.client.post(
                    "/v1/admin/create", json=payload, headers=headers,
                )
                self.assertEqual(response.status_code, expected_status)
                self.create_admin.assert_not_awaited()

        self.use_cookie()
        response = self.client.post(
            "/v1/admin/create", json=payload,
            headers={"Origin": "https://admin.example.com"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["admin_id"], "created-admin")
        self.create_admin.assert_awaited_once()

    def test_admin_lookup_failure_is_a_private_503_before_route_execution(self):
        self.use_cookie()
        error = StatementError(
            "Private database failure", "SELECT admin_users WHERE email = :email",
            {"email": "active@example.com"}, RuntimeError("PRIVATE_DATABASE_DETAILS"),
        )
        with patch.object(
            admin_auth_service, "get_admin_user_by_email",
            new_callable=AsyncMock, side_effect=error,
        ):
            response = self.client.get("/v1/admin/leads")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.json(), {
            "detail": "Admin authentication is temporarily unavailable."
        })
        self.assertNotIn("active@example.com", response.text)
        self.assertNotIn("PRIVATE_DATABASE_DETAILS", response.text)


if __name__ == "__main__":
    unittest.main()
