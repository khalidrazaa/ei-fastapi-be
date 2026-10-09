"""Contact contract, persistence boundaries and isolated email transport tests."""

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.contact.public_contact_routes import router, send_public_contact_message
from app.core.public_api_security import get_db
from app.schemas.contact import ContactRequest
from app.services import contact_service
from app.utils import email as email_client


CONTACT_PATH = "/v1/public/contact"


class ContactRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router, prefix=CONTACT_PATH)
        self.db = AsyncMock()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.payload = {
            "name": " Visitor ",
            "email": " visitor@example.com ",
            "message": " A question about dashboards. ",
        }
        self.headers = {"X-Public-App-Key": "test-app-key"}
        self.path = f"{CONTACT_PATH}?host_site=explainit.tech"
        self.auth = self.enterContext(
            patch(
                "app.core.public_api_security.validate_public_api_key",
                new_callable=AsyncMock,
                return_value=True,
            )
        )
        self.enterContext(
            patch("app.core.public_api_security._public_key_map", return_value={})
        )
        self.now = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
        self.window = self.enterContext(
            patch.object(
                contact_service.lead_query,
                "get_submission_window",
                new_callable=AsyncMock,
                return_value=(self.now, 0, None, None),
            )
        )
        self.add = self.enterContext(
            patch.object(
                contact_service.lead_query,
                "add_lead",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=42),
            )
        )
        self.send = self.enterContext(
            patch.object(contact_service, "send_contact_email", new_callable=AsyncMock)
        )

    def post(self, payload=None, path=None, headers=None):
        return self.client.post(
            path or self.path,
            json=self.payload if payload is None else payload,
            headers=self.headers if headers is None else headers,
        )

    def test_authorized_success_has_exact_response_and_trimmed_input(self):
        with patch.object(
            contact_service, "send_contact_message", new_callable=AsyncMock
        ) as service:
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": True, "message": "Your message has been submitted."},
        )
        payload, host, db = service.call_args.args
        self.assertEqual(
            payload.model_dump(exclude_none=True),
            {
                "name": "Visitor",
                "email": "visitor@example.com",
                "message": "A question about dashboards.",
            },
        )
        self.assertEqual(host, "explainit.tech")
        self.assertIs(db, self.db)
        self.auth.assert_awaited_once()

    def test_optional_phone_is_normalized_and_forwarded(self):
        cases = [
            (None, None),
            ("", None),
            ("   ", None),
            ("  +1 (202) 555-0198  ", "+12025550198"),
            ("+91 98765-43210", "+919876543210"),
            ("+44 020-7946-0018", "+442079460018"),
            ("+39 02-3661-8300", "+390236618300"),
        ]
        for supplied, expected in cases:
            with self.subTest(phone=supplied):
                response = self.post({**self.payload, "phone": supplied})
                self.assertEqual(response.status_code, 200)
                db, values = self.add.call_args.args
                self.assertIs(db, self.db)
                self.assertEqual(values["phone"], expected)
                self.assertEqual(values["name"], "Visitor")
                self.assertEqual(values["email"], "visitor@example.com")
                self.assertEqual(values["message"], "A question about dashboards.")

    def test_malformed_and_oversized_phone_never_reaches_service(self):
        invalid = [
            12025550198,
            True,
            {},
            [],
            "2025550198",
            "0012025550198",
            "+01234567",
            "+123456",
            "+1234567890123456",
            "++12025550198",
            "+1+2025550198",
            "(+1)2025550198",
            "+12025550198 ext 4",
            "+12025550198a",
            "+12025550198\n",
            "\n+12025550198",
            "+1\t2025550198",
            "+12025550198\x00",
            "+１２０２５５５０１９８",
            "+1–2025550198",
            " " * 41,
            "+12025550198" + " " * 29,
        ]
        with patch.object(
            contact_service, "send_contact_message", new_callable=AsyncMock
        ) as service:
            for phone in invalid:
                with self.subTest(phone=phone):
                    self.assertEqual(
                        self.post({**self.payload, "phone": phone}).status_code, 422
                    )
        service.assert_not_awaited()

    def test_country_metadata_accepts_fixed_and_mobile_numbers(self):
        fixtures = [
            "+919876543210",
            "+12025550123",
            "+16045550123",
            "+442079460018",
            "+390236618300",
            "+4930123456",
            "+971501234567",
            "+61412345678",
            "+6581234567",
            "+33123456789",
            "+966501234567",
            "+27821234567",
            "+358401234567",
            "+80012345678",
        ]
        with patch.object(
            contact_service, "send_contact_message", new_callable=AsyncMock
        ) as service:
            for phone in fixtures:
                with self.subTest(phone=phone):
                    self.assertEqual(
                        self.post({**self.payload, "phone": phone}).status_code, 200
                    )
                    self.assertEqual(service.call_args.args[0].phone, phone)

    def test_country_metadata_rejects_invalid_lengths_prefixes_and_codes(self):
        fixtures = [
            "+91987654321",
            "+9198765432101",  # India length
            "+1202555012",
            "+120255501234",  # US length
            "+11234567890",
            "+12001230101",  # invalid NANP area code
            "+44207946001",
            "+4420794600181",  # UK length
            "+4930",
            "+1911",  # short national/service numbers
            "+999123456789",
            "+1234567",
            "+123456789012345",
        ]
        with patch.object(
            contact_service, "send_contact_message", new_callable=AsyncMock
        ) as service:
            for phone in fixtures:
                with self.subTest(phone=phone):
                    self.assertEqual(
                        self.post({**self.payload, "phone": phone}).status_code, 422
                    )
        service.assert_not_awaited()

    def test_missing_and_invalid_app_keys_cannot_send_email(self):
        self.assertEqual(self.post(headers={}).status_code, 401)
        self.auth.return_value = False
        self.assertEqual(self.post().status_code, 403)
        self.add.assert_not_awaited()
        self.send.assert_not_awaited()

    def test_other_authorized_host_is_still_rejected(self):
        response = self.post(path=f"{CONTACT_PATH}?host_site=other.example")
        self.assertEqual(response.status_code, 403)
        self.window.assert_not_awaited()
        self.add.assert_not_awaited()
        self.send.assert_not_awaited()

    def test_invalid_key_for_a_configured_host_is_unauthorized(self):
        self.auth.return_value = False
        with patch(
            "app.core.public_api_security._public_key_map",
            return_value={"explainit.tech": "different-key"},
        ):
            self.assertEqual(self.post().status_code, 401)
        self.add.assert_not_awaited()

    def test_full_route_commits_lead_before_email_and_preserves_success_contract(self):
        operations = []

        async def add(db, values):
            operations.append("lead")
            self.assertNotIn("website", values)
            self.assertEqual(values["host_site"], "explainit.tech")
            self.assertEqual(values["submitted_at"], self.now)
            self.assertEqual(values["updated_at"], self.now)
            return SimpleNamespace(id=42)

        async def commit():
            operations.append("commit")

        async def send(**content):
            operations.append("email")
            self.assertEqual(
                content,
                {
                    "name": "Visitor",
                    "email": "visitor@example.com",
                    "message": "A question about dashboards.",
                    "phone": None,
                    "subject": None,
                },
            )

        self.add.side_effect = add
        self.db.commit.side_effect = commit
        self.send.side_effect = send
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": True, "message": "Your message has been submitted."},
        )
        self.assertEqual(operations, ["lead", "commit", "email"])
        self.send.assert_awaited_once()
        self.db.rollback.assert_not_awaited()

    def test_email_failures_keep_success_and_never_log_private_details(self):
        private = "PRIVATE_PROVIDER_BODY_AND_CONTACT_EMAIL"
        for error in (
            email_client.ContactEmailProviderError(private),
            email_client.ContactEmailConfigurationError(private),
            email_client.ContactEmailTimeoutError(private),
            TimeoutError(private),
            RuntimeError(private),
        ):
            with self.subTest(error=type(error).__name__):
                self.db.commit.reset_mock()
                self.send.reset_mock()
                self.send.side_effect = error
                with self.assertLogs(contact_service.logger, level="WARNING") as logs:
                    response = self.post()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json(),
                    {"status": True, "message": "Your message has been submitted."},
                )
                self.db.commit.assert_awaited_once()
                self.db.rollback.assert_not_awaited()
                self.send.assert_awaited_once()
                self.assertIn("lead=42", " ".join(logs.output))
                self.assertNotIn(private, " ".join(logs.output))
                self.assertNotIn("visitor@example.com", " ".join(logs.output))

    def test_stalled_email_is_cancelled_without_undoing_the_saved_enquiry(self):
        operations = []
        wait_for = asyncio.wait_for

        async def stall(**content):
            operations.append("email")
            try:
                await asyncio.Future()
            finally:
                operations.append("cancelled")

        async def short_deadline(awaitable, *, timeout):
            self.assertEqual(timeout, 10)
            return await wait_for(awaitable, timeout=0.01)

        self.send.side_effect = stall
        with (
            patch.object(contact_service.asyncio, "wait_for", new=short_deadline),
            self.assertLogs(contact_service.logger, level="WARNING"),
        ):
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(operations, ["email", "cancelled"])
        self.db.commit.assert_awaited_once()
        self.db.rollback.assert_not_awaited()

    def test_source_fields_are_trimmed_sanitized_and_persisted(self):
        response = self.post(
            {
                **self.payload,
                "subject": " Consulting ",
                "landing_page": "https://explainit.tech/consulting?token=PRIVATE#private",
                "referrer": "https://example.com/page?email=PRIVATE#private",
                "utm_source": " newsletter ",
                "utm_medium": "email",
                "utm_campaign": "consulting",
                "utm_term": "dashboards",
                "utm_content": "footer",
                "website": "",
            }
        )
        self.assertEqual(response.status_code, 200)
        values = self.add.call_args.args[1]
        self.assertEqual(values["subject"], "Consulting")
        self.assertEqual(values["landing_page"], "https://explainit.tech/consulting")
        self.assertEqual(values["referrer"], "https://example.com/page")
        self.assertEqual(values["utm_source"], "newsletter")
        self.assertEqual(values["utm_content"], "footer")
        self.assertNotIn("PRIVATE", repr(values))
        self.assertNotIn("website", values)
        self.assertEqual(self.send.call_args.kwargs["subject"], "Consulting")

    def test_invalid_source_subject_and_honeypot_do_not_create_leads(self):
        invalid = [
            {"subject": "a" * 201},
            {"subject": 1},
            {"subject": "line\nline"},
            {"landing_page": "/contact"},
            {"landing_page": "javascript:alert(1)"},
            {"landing_page": "https://user:password@example.com/"},
            {"landing_page": "https://example.com/" + "a" * 2048},
            {"referrer": "https://example.com:invalid/page"},
            {"referrer": {}},
            {"utm_source": "a" * 201},
            {"utm_medium": "line\nline"},
            {"utm_campaign": []},
            {"utm_term": "\x00"},
            {"utm_content": "\x7f"},
            {"website": "bot"},
            {"website": " "},
            {"website": 1},
            {"website": "a" * 201},
            {"message": "A question\x00"},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.assertEqual(
                    self.post({**self.payload, **changes}).status_code, 422
                )
        self.add.assert_not_awaited()

    def test_invalid_fields_and_recipient_override_are_rejected(self):
        invalid = [
            {"name": " "},
            {"name": "n" * 81},
            {"name": 5},
            {"name": "Visitor\nBcc: attacker@example.com"},
            {"email": "not-an-email"},
            {"email": 5},
            {"email": "v@example.com\r\nBcc: attacker@example.com"},
            {"message": "\n\t"},
            {"message": "m" * 5001},
            {"message": {}},
            {"to": "attacker@example.com"},
            {"recipient": "attacker@example.com"},
        ]
        with patch.object(
            contact_service, "send_contact_message", new_callable=AsyncMock
        ) as service:
            for changes in invalid:
                with self.subTest(changes=changes):
                    self.assertEqual(
                        self.post({**self.payload, **changes}).status_code, 422
                    )
            for missing in self.payload:
                payload = dict(self.payload)
                del payload[missing]
                self.assertEqual(self.post(payload).status_code, 422)
            self.assertEqual(self.post(path=CONTACT_PATH).status_code, 422)
        service.assert_not_awaited()

    def test_maximum_lengths_are_valid(self):
        payload = {
            "name": "n" * 80,
            "email": "e" * 64
            + "@"
            + "a" * 63
            + "."
            + "b" * 63
            + "."
            + "c" * 57
            + ".com",
            "message": "m" * 5000,
        }
        self.assertEqual(len(payload["email"]), 254)
        with patch.object(
            contact_service, "send_contact_message", new_callable=AsyncMock
        ):
            self.assertEqual(self.post(payload).status_code, 200)
            payload["email"] = payload["email"].replace("c" * 57, "c" * 58)
            self.assertEqual(self.post(payload).status_code, 422)

    def test_insert_failure_rolls_back_and_never_reports_success_or_private_details(
        self,
    ):
        self.add.side_effect = SQLAlchemyError("private-database-data")
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-database-data", response.text)
        self.assertNotIn("status", response.json())
        self.db.commit.assert_not_awaited()
        self.db.rollback.assert_awaited_once()
        self.send.assert_not_awaited()

    def test_commit_failure_rolls_back_and_never_reports_success(self):
        self.db.commit.side_effect = SQLAlchemyError("private-database-data")
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-database-data", response.text)
        self.assertNotIn("status", response.json())
        self.add.assert_awaited_once()
        self.db.commit.assert_awaited_once()
        self.db.rollback.assert_awaited_once()
        self.send.assert_not_awaited()

    def test_rapid_repeated_enquiry_is_blocked_before_persistence(self):
        self.assertEqual(self.post().status_code, 200)
        self.window.return_value = (self.now, 1, self.now, self.now)
        response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(int(response.headers["Retry-After"]), 60)
        self.add.assert_awaited_once()
        self.db.commit.assert_awaited_once()
        self.db.rollback.assert_awaited_once()


class ContactEmailTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            BREVO_API_KEY="test-brevo-key",
            BREVO_URL="https://api.brevo.com/v3/smtp/email",
            EMAIL_USERNAME="verified@example.com",
            CONTACT_EMAIL_TO="core@explainit.tech",
        )
        self.enterContext(patch.object(email_client, "settings", self.config))
        self.transport = AsyncMock()
        self.transport.post.return_value = httpx.Response(
            201, json={"messageId": "provider-message-id"}
        )
        factory = self.enterContext(patch.object(email_client.httpx, "AsyncClient"))
        factory.return_value.__aenter__.return_value = self.transport
        self.factory = factory

    async def send(self):
        await email_client.send_contact_email(
            name="Visitor",
            email="visitor@example.com",
            message="<script>bad()</script>\nA normal question.",
        )

    async def test_provider_payload_has_fixed_recipient_and_plaintext_reply_to(self):
        await self.send()
        call = self.transport.post.call_args
        self.assertEqual(call.args, (self.config.BREVO_URL,))
        self.assertEqual(call.kwargs["headers"]["api-key"], "test-brevo-key")
        payload = call.kwargs["json"]
        self.assertEqual(
            payload["sender"], {"email": "verified@example.com", "name": "explainit"}
        )
        self.assertEqual(payload["to"], [{"email": "core@explainit.tech"}])
        self.assertEqual(
            payload["replyTo"], {"email": "visitor@example.com", "name": "Visitor"}
        )
        self.assertEqual(
            payload["textContent"],
            "Name: Visitor\nEmail: visitor@example.com\n\n"
            "<script>bad()</script>\nA normal question.",
        )
        self.assertNotIn("htmlContent", payload)
        self.assertEqual(self.factory.call_args.kwargs["timeout"], 10.0)

    async def test_configured_server_recipient_can_be_changed(self):
        self.config.CONTACT_EMAIL_TO = "inbox@example.com"
        await self.send()
        self.assertEqual(
            self.transport.post.call_args.kwargs["json"]["to"],
            [{"email": "inbox@example.com"}],
        )

    async def test_phone_is_included_only_as_plaintext_contact_details(self):
        await email_client.send_contact_email(
            name="Visitor",
            email="visitor@example.com",
            message="A question.",
            phone="+12025550198",
        )
        payload = self.transport.post.call_args.kwargs["json"]
        self.assertEqual(
            payload["textContent"],
            "Name: Visitor\nEmail: visitor@example.com\n"
            "Phone: +12025550198\n\nA question.",
        )
        self.assertEqual(payload["to"], [{"email": "core@explainit.tech"}])
        self.assertEqual(payload["replyTo"]["email"], "visitor@example.com")
        self.assertNotIn("htmlContent", payload)

    async def test_null_phone_preserves_existing_email_body(self):
        await email_client.send_contact_email(
            name="Visitor",
            email="visitor@example.com",
            message="A question.",
            phone=None,
        )
        self.assertEqual(
            self.transport.post.call_args.kwargs["json"]["textContent"],
            "Name: Visitor\nEmail: visitor@example.com\n\nA question.",
        )

    async def test_missing_configuration_never_contacts_provider(self):
        for field in vars(self.config):
            original = getattr(self.config, field)
            setattr(self.config, field, " ")
            with self.subTest(field=field):
                with self.assertRaises(email_client.ContactEmailConfigurationError):
                    await self.send()
            setattr(self.config, field, original)
        self.transport.post.assert_not_awaited()

    async def test_invalid_configuration_never_contacts_provider(self):
        for field, value in (
            ("EMAIL_USERNAME", "invalid"),
            ("CONTACT_EMAIL_TO", "invalid"),
            ("BREVO_URL", "http://api.brevo.com/v3/smtp/email"),
        ):
            original = getattr(self.config, field)
            setattr(self.config, field, value)
            with self.subTest(field=field):
                with self.assertRaises(email_client.ContactEmailConfigurationError):
                    await self.send()
            setattr(self.config, field, original)
        self.transport.post.assert_not_awaited()

    async def test_provider_rejection_and_malformed_acceptance_are_failures(self):
        responses = [
            httpx.Response(400, json={"message": "private-provider-data"}),
            httpx.Response(401),
            httpx.Response(429),
            httpx.Response(500),
            httpx.Response(200, json={"messageId": "id"}),
            httpx.Response(201, json={}),
            httpx.Response(201, json=[]),
            httpx.Response(201, json={"messageId": " "}),
            httpx.Response(201, json={"messageId": 12}),
            httpx.Response(201, text="invalid json"),
        ]
        for response in responses:
            with self.subTest(response=response):
                self.transport.post.return_value = response
                with self.assertRaises(email_client.ContactEmailProviderError):
                    await self.send()

    async def test_network_and_timeout_errors_are_classified(self):
        for error, expected in (
            (
                httpx.ReadTimeout("private-provider-data"),
                email_client.ContactEmailTimeoutError,
            ),
            (
                httpx.ConnectError("private-provider-data"),
                email_client.ContactEmailProviderError,
            ),
        ):
            with self.subTest(error=error):
                self.transport.post.side_effect = error
                with self.assertRaises(expected) as caught:
                    await self.send()
                self.assertNotIn("private-provider-data", str(caught.exception))


class ContactRateLimitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = AsyncMock()
        self.now = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
        self.payload = ContactRequest(
            name="Visitor", email="visitor@example.com", message="Consulting enquiry."
        )
        self.window = self.enterContext(
            patch.object(
                contact_service.lead_query,
                "get_submission_window",
                new_callable=AsyncMock,
            )
        )
        self.add = self.enterContext(
            patch.object(
                contact_service.lead_query,
                "add_lead",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=42),
            )
        )
        self.send = self.enterContext(
            patch.object(contact_service, "send_contact_email", new_callable=AsyncMock)
        )

    async def test_window_expiry_allows_multiple_enquiries_from_same_email(self):
        self.window.side_effect = [
            (self.now, 0, None, None),
            (self.now + timedelta(seconds=60), 0, None, None),
        ]
        await contact_service.send_contact_message(
            self.payload, "explainit.tech", self.db
        )
        await contact_service.send_contact_message(
            self.payload, "explainit.tech", self.db
        )
        self.assertEqual(self.add.await_count, 2)
        self.assertEqual(self.db.commit.await_count, 2)
        self.assertEqual(self.send.await_count, 2)
        self.assertEqual(
            [call.args[1]["email"] for call in self.add.await_args_list],
            ["visitor@example.com", "visitor@example.com"],
        )

    async def test_global_cap_prevents_new_leads_and_reports_remaining_window(self):
        self.window.return_value = (
            self.now,
            20,
            self.now - timedelta(seconds=20),
            None,
        )
        with self.assertRaises(contact_service.ContactRateLimitError) as caught:
            await contact_service.send_contact_message(
                self.payload, "explainit.tech", self.db
            )
        self.assertEqual(caught.exception.retry_after, 40)
        self.add.assert_not_awaited()
        self.db.commit.assert_not_awaited()
        self.db.rollback.assert_awaited_once()
        self.send.assert_not_awaited()

    async def test_email_and_global_windows_use_the_longer_delay(self):
        self.window.return_value = (
            self.now,
            20,
            self.now - timedelta(seconds=50),
            self.now - timedelta(seconds=10, milliseconds=500),
        )
        with self.assertRaises(contact_service.ContactRateLimitError) as caught:
            await contact_service.send_contact_message(
                self.payload, "explainit.tech", self.db
            )
        self.assertEqual(caught.exception.retry_after, 50)
        self.add.assert_not_awaited()
        self.send.assert_not_awaited()


class ContactAppRoutingTests(unittest.TestCase):
    def test_production_app_registers_the_versioned_contact_endpoint(self):
        # Inspect the real app without running startup jobs or external services.
        from app.main import app

        contact_routes = [
            route
            for route in app.routes
            if getattr(route, "endpoint", None) is send_public_contact_message
        ]
        self.assertEqual(len(contact_routes), 1)
        self.assertEqual(contact_routes[0].path, CONTACT_PATH)
        self.assertEqual(contact_routes[0].methods, {"POST"})
        registered_paths = {getattr(route, "path", None) for route in app.routes}
        self.assertNotIn("/public/contact", registered_paths)
        self.assertNotIn("/v1/contact", registered_paths)


if __name__ == "__main__":
    unittest.main()
