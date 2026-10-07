"""Contact contract tests with isolated auth/database and mocked email transport."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.contact.public_contact_routes import router
from app.core.public_api_security import get_db
from app.schemas.contact import ContactRequest
from app.services import contact_service
from app.utils import email as email_client


class ContactRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router, prefix="/v1/public/contact")
        app.dependency_overrides[get_db] = lambda: None
        self.client = TestClient(app)
        self.payload = {
            "name": " Visitor ",
            "email": " visitor@example.com ",
            "message": " A question about dashboards. ",
        }
        self.headers = {"X-Public-App-Key": "test-app-key"}
        self.path = "/v1/public/contact?host_site=explainit.tech"
        self.auth = self.enterContext(patch(
            "app.core.public_api_security.validate_public_api_key",
            new_callable=AsyncMock,
            return_value=True,
        ))
        self.enterContext(patch(
            "app.core.public_api_security._public_key_map", return_value={}
        ))
        self.enterContext(patch.object(
            contact_service, "_rate_limiter", contact_service._ContactRateLimiter()
        ))

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
        self.assertEqual(response.json(), {
            "status": True, "message": "Your message has been submitted."
        })
        payload, host = service.call_args.args
        self.assertEqual(payload.model_dump(), {
            "name": "Visitor", "email": "visitor@example.com",
            "message": "A question about dashboards.", "phone": None,
        })
        self.assertEqual(host, "explainit.tech")
        self.auth.assert_awaited_once()

    def test_optional_phone_is_normalized_and_forwarded(self):
        cases = [
            (None, None), ("", None), ("   ", None),
            ("  +1 (202) 555-0198  ", "+12025550198"),
            ("+1234567", "+1234567"),
            ("+123456789012345", "+123456789012345"),
        ]
        for supplied, expected in cases:
            with self.subTest(phone=supplied), patch.object(
                contact_service, "send_contact_email", new_callable=AsyncMock
            ) as send, patch.object(
                contact_service, "_rate_limiter",
                contact_service._ContactRateLimiter(),
            ):
                response = self.post({**self.payload, "phone": supplied})
                self.assertEqual(response.status_code, 200)
                send.assert_awaited_once_with(
                    name="Visitor", email="visitor@example.com",
                    message="A question about dashboards.", phone=expected,
                )

    def test_malformed_and_oversized_phone_never_reaches_service(self):
        invalid = [
            12025550198, True, {}, [],
            "2025550198", "0012025550198", "+01234567", "+123456",
            "+1234567890123456", "++12025550198", "+1+2025550198",
            "(+1)2025550198", "+12025550198 ext 4", "+12025550198a",
            "+12025550198\n", "\n+12025550198", "+1\t2025550198",
            "+12025550198\x00", "+１２０２５５５０１９８", "+1–2025550198",
            " " * 41, "+12025550198" + " " * 29,
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

    def test_missing_and_invalid_app_keys_cannot_send_email(self):
        with patch.object(
            contact_service, "send_contact_email", new_callable=AsyncMock
        ) as send:
            self.assertEqual(self.post(headers={}).status_code, 401)
            self.auth.return_value = False
            self.assertEqual(self.post().status_code, 403)
        send.assert_not_awaited()

    def test_other_authorized_host_is_still_rejected(self):
        with patch.object(
            contact_service, "send_contact_email", new_callable=AsyncMock
        ) as send:
            response = self.post(path="/v1/public/contact?host_site=other.example")
        self.assertEqual(response.status_code, 403)
        send.assert_not_awaited()

    def test_invalid_key_for_a_configured_host_is_unauthorized(self):
        self.auth.return_value = False
        with patch(
            "app.core.public_api_security._public_key_map",
            return_value={"explainit.tech": "different-key"},
        ), patch.object(
            contact_service, "send_contact_email", new_callable=AsyncMock
        ) as send:
            self.assertEqual(self.post().status_code, 401)
        send.assert_not_awaited()

    def test_full_route_succeeds_only_after_mocked_provider_acceptance(self):
        config = SimpleNamespace(
            BREVO_API_KEY="test-brevo-key",
            BREVO_URL="https://api.brevo.com/v3/smtp/email",
            EMAIL_USERNAME="verified@example.com",
            CONTACT_EMAIL_TO="core@explainit.tech",
        )
        for provider_status, expected_status in ((201, 200), (400, 502)):
            with self.subTest(provider_status=provider_status):
                transport = AsyncMock()
                transport.post.return_value = httpx.Response(
                    provider_status, json={"messageId": "provider-message-id"}
                )
                with patch.object(email_client, "settings", config), patch.object(
                    email_client.httpx, "AsyncClient"
                ) as factory, patch.object(
                    contact_service, "_rate_limiter",
                    contact_service._ContactRateLimiter(),
                ):
                    factory.return_value.__aenter__.return_value = transport
                    response = self.post()
                self.assertEqual(response.status_code, expected_status)
                transport.post.assert_awaited_once()
                self.assertEqual(
                    transport.post.call_args.kwargs["json"]["to"],
                    [{"email": "core@explainit.tech"}],
                )
                if expected_status != 200:
                    self.assertNotIn("status", response.json())

    def test_invalid_fields_and_recipient_override_are_rejected(self):
        invalid = [
            {"name": " "}, {"name": "n" * 81}, {"name": 5},
            {"name": "Visitor\nBcc: attacker@example.com"},
            {"email": "not-an-email"}, {"email": 5},
            {"email": "v@example.com\r\nBcc: attacker@example.com"},
            {"message": "\n\t"}, {"message": "m" * 5001}, {"message": {}},
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
            self.assertEqual(
                self.post(path="/v1/public/contact").status_code, 422
            )
        service.assert_not_awaited()

    def test_maximum_lengths_are_valid(self):
        payload = {
            "name": "n" * 80,
            "email": "e" * 64 + "@" + "a" * 63 + "." + "b" * 63 + "." + "c" * 57 + ".com",
            "message": "m" * 5000,
        }
        self.assertEqual(len(payload["email"]), 254)
        with patch.object(
            contact_service, "send_contact_message", new_callable=AsyncMock
        ):
            self.assertEqual(self.post(payload).status_code, 200)
            payload["email"] = payload["email"].replace("c" * 57, "c" * 58)
            self.assertEqual(self.post(payload).status_code, 422)

    def test_upstream_errors_never_report_success_or_expose_details(self):
        cases = [
            (contact_service.ContactEmailConfigurationError, 503),
            (contact_service.ContactEmailProviderError, 502),
            (contact_service.ContactEmailTimeoutError, 504),
        ]
        for error, expected_status in cases:
            with self.subTest(error=error):
                with patch.object(
                    contact_service, "send_contact_message",
                    new_callable=AsyncMock, side_effect=error("private-provider-data"),
                ):
                    response = self.post()
                self.assertEqual(response.status_code, expected_status)
                self.assertNotIn("private-provider-data", response.text)
                self.assertNotIn("status", response.json())

    def test_rapid_repeated_send_is_blocked_before_provider(self):
        with patch.object(
            contact_service, "send_contact_email", new_callable=AsyncMock
        ) as send:
            self.assertEqual(self.post().status_code, 200)
            response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertGreaterEqual(int(response.headers["Retry-After"]), 1)
        send.assert_awaited_once()


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
            name="Visitor", email="visitor@example.com",
            message="<script>bad()</script>\nA normal question.",
        )

    async def test_provider_payload_has_fixed_recipient_and_plaintext_reply_to(self):
        await self.send()
        call = self.transport.post.call_args
        self.assertEqual(call.args, (self.config.BREVO_URL,))
        self.assertEqual(call.kwargs["headers"]["api-key"], "test-brevo-key")
        payload = call.kwargs["json"]
        self.assertEqual(payload["sender"], {
            "email": "verified@example.com", "name": "explainit"
        })
        self.assertEqual(payload["to"], [{"email": "core@explainit.tech"}])
        self.assertEqual(payload["replyTo"], {
            "email": "visitor@example.com", "name": "Visitor"
        })
        self.assertEqual(payload["textContent"],
            "Name: Visitor\nEmail: visitor@example.com\n\n"
            "<script>bad()</script>\nA normal question."
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
            name="Visitor", email="visitor@example.com", message="A question.",
            phone="+12025550198",
        )
        payload = self.transport.post.call_args.kwargs["json"]
        self.assertEqual(payload["textContent"],
            "Name: Visitor\nEmail: visitor@example.com\n"
            "Phone: +12025550198\n\nA question."
        )
        self.assertEqual(payload["to"], [{"email": "core@explainit.tech"}])
        self.assertEqual(payload["replyTo"]["email"], "visitor@example.com")
        self.assertNotIn("htmlContent", payload)

    async def test_null_phone_preserves_existing_email_body(self):
        await email_client.send_contact_email(
            name="Visitor", email="visitor@example.com", message="A question.",
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
            ("EMAIL_USERNAME", "invalid"), ("CONTACT_EMAIL_TO", "invalid"),
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
            httpx.Response(401), httpx.Response(429), httpx.Response(500),
            httpx.Response(200, json={"messageId": "id"}),
            httpx.Response(201, json={}), httpx.Response(201, json=[]),
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
            (httpx.ReadTimeout("private-provider-data"),
             email_client.ContactEmailTimeoutError),
            (httpx.ConnectError("private-provider-data"),
             email_client.ContactEmailProviderError),
        ):
            with self.subTest(error=error):
                self.transport.post.side_effect = error
                with self.assertRaises(expected) as caught:
                    await self.send()
                self.assertNotIn("private-provider-data", str(caught.exception))


class ContactRateLimitTests(unittest.TestCase):
    def test_window_expiry_allows_another_send_and_discards_old_state(self):
        limiter = contact_service._ContactRateLimiter()
        with patch.object(contact_service, "monotonic", return_value=100):
            limiter.take("visitor@example.com")
            with self.assertRaises(contact_service.ContactRateLimitError):
                limiter.take("VISITOR@example.com")
        with patch.object(contact_service, "monotonic", return_value=160):
            limiter.take("visitor@example.com")
        self.assertEqual(len(limiter._attempts), 1)
        self.assertEqual(len(limiter._emails), 1)

    def test_global_cap_bounds_state_even_with_distinct_emails(self):
        limiter = contact_service._ContactRateLimiter(max_attempts=2)
        with patch.object(contact_service, "monotonic", return_value=100):
            limiter.take("one@example.com")
            limiter.take("two@example.com")
            for index in range(20):
                with self.assertRaises(contact_service.ContactRateLimitError):
                    limiter.take(f"other{index}@example.com")
        self.assertEqual(len(limiter._attempts), 2)
        self.assertEqual(len(limiter._emails), 2)


if __name__ == "__main__":
    unittest.main()
