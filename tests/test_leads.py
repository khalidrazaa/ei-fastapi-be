"""Lead query, service and admin API integration using isolated real SQLite."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, StatementError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.admin.lead_routes import router
from app.core.admin_security import require_admin
from app.db.models.lead import Lead
from app.db.query import lead as lead_query
from app.db.session import get_db
from app.schemas.contact import ContactRequest
from app.schemas.lead import LeadStatus, LeadUpdate
from app.services import contact_service, lead_service
from app.utils.email import ContactEmailProviderError


class AsyncSessionAdapter:
    """Run production SQL against SQLite without adding an async SQLite driver."""

    def __init__(self, session):
        self.session = session

    async def execute(self, query):
        return self.session.execute(query)

    def add(self, instance):
        self.session.add(instance)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def refresh(self, instance):
        self.session.refresh(instance)


class LeadDatabaseFixture:
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Lead.__table__.create(self.engine)
        self.session = Session(self.engine)
        self.db = AsyncSessionAdapter(self.session)
        self.submitted_at = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def values(self, identifier=1, **changes):
        values = dict(
            id=identifier,
            name=f"Visitor {identifier}",
            email="visitor@example.com",
            phone="+12025550198",
            subject="Consulting",
            message="Please discuss my project.",
            host_site="explainit.tech",
            landing_page="https://explainit.tech/start",
            referrer="https://example.com/guide",
            utm_source="newsletter",
            utm_medium="email",
            utm_campaign="consulting",
            utm_term="automation",
            utm_content="footer",
            submitted_at=self.submitted_at,
            updated_at=self.submitted_at,
        )
        values.update(changes)
        return values

    def add_lead(self, identifier=1, **changes):
        lead = Lead(**self.values(identifier, **changes))
        self.session.add(lead)
        self.session.commit()
        return lead

    def count(self, model):
        return self.session.execute(select(func.count(model.id))).scalar_one()


class LeadQueryTests(LeadDatabaseFixture, unittest.IsolatedAsyncioTestCase):
    async def test_lead_commits_with_default_status_and_notes(self):
        async with lead_query.submission_transaction(self.db):
            lead = await lead_query.add_lead(self.db, self.values())
        self.assertEqual(self.count(Lead), 1)
        self.assertEqual(lead.status, "new")
        self.assertEqual(lead.internal_notes, "")

    async def test_failure_after_flush_rolls_back_the_lead(self):
        original_flush = self.db.flush

        async def fail_after_flush():
            await original_flush()
            raise SQLAlchemyError("Simulated lead insert failure")

        with patch.object(
            self.db, "flush", new=AsyncMock(side_effect=fail_after_flush)
        ):
            with self.assertRaises(SQLAlchemyError):
                async with lead_query.submission_transaction(self.db):
                    await lead_query.add_lead(self.db, self.values())
        self.assertEqual(self.count(Lead), 0)

    async def test_email_failure_leaves_committed_enquiry_visible_to_admin(self):
        async def fail_email(**content):
            self.assertFalse(self.session.in_transaction())
            with Session(self.engine) as reader:
                lead = reader.execute(select(Lead)).scalar_one()
                self.assertEqual(lead.email, content["email"])
                self.assertEqual(lead.message, content["message"])
            raise ContactEmailProviderError()

        with (
            patch.object(
                lead_query, "get_submission_window", new_callable=AsyncMock,
                return_value=(self.submitted_at, 0, None, None),
            ),
            patch.object(
                contact_service, "send_contact_email",
                new_callable=AsyncMock, side_effect=fail_email,
            ) as send,
            self.assertLogs(contact_service.logger, level="WARNING"),
        ):
            await contact_service.send_contact_message(
                ContactRequest(
                    name="Visitor", email="visitor@example.com",
                    message="Please discuss my project.", subject="Consulting",
                ),
                "explainit.tech", self.db,
            )
        send.assert_awaited_once()
        results = await lead_service.list_leads(self.db, page=1, size=20)
        self.assertEqual(results["total"], 1)
        self.assertEqual(results["items"][0].subject, "Consulting")

    async def test_newest_first_pagination_has_stable_ties_and_shared_envelope(self):
        for identifier in range(1, 5):
            self.add_lead(identifier)
        first = await lead_query.list_leads(self.db, page=1, size=2)
        second = await lead_query.list_leads(self.db, page=2, size=2)
        self.assertEqual([lead.id for lead in first["items"]], [4, 3])
        self.assertEqual([lead.id for lead in second["items"]], [2, 1])
        self.assertEqual(first["total"], 4)
        self.assertEqual(first["total_pages"], 2)
        self.assertTrue(first["has_next"])
        self.assertFalse(first["has_previous"])
        self.assertTrue(second["has_previous"])
        self.assertFalse(second["has_next"])
        self.add_lead(5, submitted_at=self.submitted_at - timedelta(days=1))
        all_items = await lead_query.list_leads(self.db, page=1, size=20)
        self.assertEqual([lead.id for lead in all_items["items"]], [4, 3, 2, 1, 5])

    async def test_search_matches_each_contact_field_case_insensitively(self):
        for field, value in (
            ("name", "NEEDLE"),
            ("email", "needle@example.com"),
            ("phone", "+12025550123"),
            ("subject", "Needle proposal"),
            ("message", "Project needle details"),
        ):
            with self.subTest(field=field):
                self.session.query(Lead).delete()
                self.session.commit()
                self.add_lead(1, **{field: value})
                self.add_lead(2)
                term = "5550123" if field == "phone" else "needle"
                result = await lead_query.list_leads(
                    self.db, page=1, size=20, search=term
                )
                self.assertEqual([lead.id for lead in result["items"]], [1])
                self.assertEqual(result["total"], 1)

    async def test_search_treats_percent_underscore_and_backslash_as_literal_text(self):
        self.add_lead(1, name="Budget 100%_\\done")
        self.add_lead(2, name="Budget 100abXdone")
        for term in ("%", "_", "\\", "100%_\\"):
            with self.subTest(term=term):
                result = await lead_query.list_leads(
                    self.db, page=1, size=20, search=term
                )
                self.assertEqual([lead.id for lead in result["items"]], [1])
                self.assertEqual(result["total"], 1)

    async def test_service_combines_trimmed_search_status_and_exact_source(self):
        self.add_lead(1, status="qualified")
        self.add_lead(2, status="qualified", utm_source="ads")
        self.add_lead(3, status="new")
        self.add_lead(4, status="qualified", message="No matching text here.")
        result = await lead_service.list_leads(
            self.db,
            page=1,
            size=20,
            search=" project ",
            status=LeadStatus.qualified,
            source=" newsletter ",
        )
        self.assertEqual([lead.id for lead in result["items"]], [1])
        self.assertEqual(result["total"], 1)

    async def test_empty_and_out_of_range_results_keep_pagination_structure(self):
        empty = await lead_query.list_leads(self.db, page=1, size=20)
        self.assertEqual(
            empty,
            dict(
                items=[],
                total=0,
                page=1,
                size=20,
                total_pages=0,
                has_next=False,
                has_previous=False,
            ),
        )
        self.add_lead()
        beyond = await lead_query.list_leads(self.db, page=2, size=20)
        self.assertEqual(beyond["items"], [])
        self.assertEqual(beyond["total"], 1)
        self.assertFalse(beyond["has_next"])
        self.assertTrue(beyond["has_previous"])

    async def test_get_and_update_persist_all_supported_statuses_and_notes(self):
        self.add_lead()
        found = await lead_service.get_lead(self.db, 1)
        self.assertEqual(found.email, "visitor@example.com")
        self.assertEqual(found.utm_campaign, "consulting")
        for status in LeadStatus:
            with self.subTest(status=status):
                updated = await lead_service.update_lead(
                    self.db,
                    1,
                    LeadUpdate(status=status, internal_notes="Call\nFollow up"),
                )
                self.assertEqual(updated.status, status.value)
                self.assertEqual(updated.internal_notes, "Call\nFollow up")
                self.assertEqual(updated.message, "Please discuss my project.")
                self.assertEqual(updated.email, "visitor@example.com")
        cleared = await lead_service.update_lead(
            self.db, 1, LeadUpdate(internal_notes="")
        )
        self.assertEqual(cleared.internal_notes, "")
        self.assertEqual(cleared.status, "spam")

    async def test_missing_lead_get_and_update_raise_lookup_errors(self):
        with self.assertRaisesRegex(LookupError, "Lead not found"):
            await lead_service.get_lead(self.db, 999)
        with self.assertRaisesRegex(LookupError, "Lead not found"):
            await lead_service.update_lead(
                self.db, 999, LeadUpdate(status=LeadStatus.won)
            )

    async def test_database_status_constraint_rejects_unsupported_values(self):
        lead = self.add_lead()
        with self.assertRaises(IntegrityError):
            await lead_query.update_lead(self.db, lead, {"status": "invalid"})
        self.session.rollback()
        self.assertEqual((await lead_query.get_lead(self.db, 1)).status, "new")


class LeadRouteTests(LeadDatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(router, prefix="/v1/admin/leads")

        async def database():
            return self.db

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[require_admin] = lambda: {"id": 1}
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.path = "/v1/admin/leads"

    def test_list_returns_existing_pagination_contract_and_private_lead_details(self):
        self.add_lead(1)
        self.add_lead(2)
        response = self.client.get(self.path, params={"page": 1, "size": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        body = response.json()
        self.assertEqual(
            set(body),
            {
                "items",
                "total",
                "page",
                "size",
                "total_pages",
                "has_next",
                "has_previous",
            },
        )
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["total_pages"], 2)
        self.assertTrue(body["has_next"])
        self.assertEqual(body["items"][0]["id"], 2)
        self.assertEqual(
            set(body["items"][0]),
            {
                "id",
                "name",
                "email",
                "phone",
                "subject",
                "message",
                "host_site",
                "landing_page",
                "referrer",
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_term",
                "utm_content",
                "status",
                "internal_notes",
                "submitted_at",
                "updated_at",
            },
        )
        self.assertEqual(body["items"][0]["status"], "new")
        self.assertEqual(body["items"][0]["internal_notes"], "")

    def test_list_filters_search_status_and_source_through_real_service_and_sql(self):
        self.add_lead(1, status="qualified")
        self.add_lead(2, status="qualified", utm_source="ads")
        self.add_lead(3, status="new")
        response = self.client.get(
            self.path,
            params={
                "search": " PROJECT ",
                "status": "qualified",
                "source": " newsletter ",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["items"]], [1])
        self.assertEqual(response.json()["total"], 1)

    def test_get_and_patch_return_detail_contract_with_no_store(self):
        self.add_lead()
        detail = self.client.get(f"{self.path}/1")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.headers["Cache-Control"], "no-store")
        self.assertEqual(detail.json()["landing_page"], "https://explainit.tech/start")
        updated = self.client.patch(
            f"{self.path}/1",
            json={
                "status": "proposal",
                "internal_notes": "Prepare proposal.\nOwner: consulting",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.headers["Cache-Control"], "no-store")
        self.assertEqual(updated.json()["status"], "proposal")
        self.assertEqual(
            updated.json()["internal_notes"], "Prepare proposal.\nOwner: consulting"
        )
        after = self.client.get(f"{self.path}/1").json()
        self.assertEqual(after, updated.json())
        self.assertEqual(after["email"], detail.json()["email"])
        self.assertEqual(after["submitted_at"], detail.json()["submitted_at"])

    def test_missing_details_and_updates_return_404(self):
        for method in ("get", "patch"):
            with self.subTest(method=method):
                kwargs = {"json": {"status": "won"}} if method == "patch" else {}
                response = getattr(self.client, method)(f"{self.path}/999", **kwargs)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "Lead not found."})

    def test_invalid_pagination_filters_and_identifiers_are_rejected(self):
        for params in (
            {"page": 0},
            {"size": 0},
            {"size": 101},
            {"page": "invalid"},
            {"status": "invalid"},
            {"search": "a" * 201},
            {"source": "a" * 201},
        ):
            with self.subTest(params=params):
                self.assertEqual(
                    self.client.get(self.path, params=params).status_code, 422
                )
        for identifier in ("0", "-1", "invalid"):
            self.assertEqual(
                self.client.get(f"{self.path}/{identifier}").status_code, 422
            )

    def test_invalid_updates_cannot_change_notes_status_or_contact_details(self):
        self.add_lead()
        for payload in (
            {},
            {"status": "invalid"},
            {"status": 1},
            {"status": None},
            {"internal_notes": None},
            {"internal_notes": 1},
            {"internal_notes": "a" * 10001},
            {"internal_notes": "note\x00"},
            {"email": "attacker@example.com"},
            {"message": "Overwritten"},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(f"{self.path}/1", json=payload)
                self.assertEqual(response.status_code, 422)
        result = self.client.get(f"{self.path}/1").json()
        self.assertEqual(result["status"], "new")
        self.assertEqual(result["internal_notes"], "")
        self.assertEqual(result["email"], "visitor@example.com")

    def test_notes_allow_the_documented_maximum_and_can_be_cleared(self):
        self.add_lead()
        response = self.client.patch(
            f"{self.path}/1", json={"internal_notes": "a" * 10000}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["internal_notes"]), 10000)
        cleared = self.client.patch(f"{self.path}/1", json={"internal_notes": ""})
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["internal_notes"], "")

    def test_database_errors_return_private_503_without_query_or_bound_data(self):
        self.add_lead()
        private = "PRIVATE_INTERNAL_NOTES_AND_EMAIL"
        for method, path, query_name in (
            ("get", self.path, "list_leads"),
            ("get", f"{self.path}/1", "get_lead"),
            ("patch", f"{self.path}/1", "get_lead"),
            ("patch", f"{self.path}/1", "update_lead"),
        ):
            with self.subTest(method=method, query=query_name):
                error = StatementError(
                    "Private database failure",
                    "UPDATE leads SET internal_notes = :internal_notes",
                    {"internal_notes": private},
                    RuntimeError(private),
                )
                with patch.object(
                    lead_query, query_name, new_callable=AsyncMock, side_effect=error,
                ):
                    kwargs = (
                        {"json": {"internal_notes": private}}
                        if method == "patch" else {}
                    )
                    response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(response.json(), {
                    "detail": "The lead service is temporarily unavailable."
                })
                self.assertNotIn(private, response.text)
                self.assertNotIn("UPDATE leads", response.text)

        after = self.client.get(f"{self.path}/1")
        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.json()["internal_notes"], "")


if __name__ == "__main__":
    unittest.main()
