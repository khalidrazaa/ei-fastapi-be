"""Scan switches cover manual, scheduled and direct service execution offline."""

import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.youtube import youtube_routes
from app.core.admin_security import require_admin
from app.db.models.popular_scan_setting import PopularScanSetting
from app.db.session import get_db
from app.scheduler import jobs
from app.services.popular_scan_settings import (
    YouTubeScanDisabledError,
    YouTubeScanMigrationRequiredError,
)
from app.services.scanner import youtube_scan_service as scans


class Adapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def commit(self):
        self.session.commit()

    async def refresh(self, value):
        self.session.refresh(value)


class YouTubeScanExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        PopularScanSetting.__table__.create(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.session.close)
        self.row = PopularScanSetting(
            key="default", region_codes=["US", "IN"], available_regions=[],
            max_results=10, youtube_scan_enabled=True,
            popular_scan_enabled=True, niche_scan_enabled=True,
        )
        self.session.add(self.row)
        self.session.commit()
        self.db = Adapter(self.session)
        self.youtube = SimpleNamespace(**{
            name: AsyncMock(return_value={"items": []}) for name in (
                "search_videos", "get_video_details", "get_video_categories",
                "get_channel_details", "get_trending_videos",
            )
        })
        self.service = scans.YouTubeScanService(self.db, self.youtube)
        self.keyword_lookup = self.enterContext(patch.object(
            scans, "get_keyword_by_id", new_callable=AsyncMock,
            return_value=SimpleNamespace(id=1, niche_id=1, keyword="science"),
        ))
        self.enterContext(patch.object(
            scans, "get_niche_by_id", new_callable=AsyncMock,
            return_value=SimpleNamespace(region_code="US"),
        ))
        self.keywords_lookup = self.enterContext(patch.object(
            scans, "get_keywords_by_niche", new_callable=AsyncMock,
            return_value=[SimpleNamespace(id=1), SimpleNamespace(id=2)],
        ))

        @asynccontextmanager
        async def session_local():
            yield self.db

        self.enterContext(patch.object(jobs, "SessionLocal", session_local))

    def flags(self, master=True, popular=True, niche=True):
        self.row.youtube_scan_enabled = master
        self.row.popular_scan_enabled = popular
        self.row.niche_scan_enabled = niche
        self.session.commit()

    def client(self, authenticated=True):
        app = FastAPI()
        app.include_router(youtube_routes.router, prefix="/v1/admin/yt-scan")
        app.dependency_overrides[get_db] = lambda: self.db
        if authenticated:
            app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
        return TestClient(app)

    async def test_direct_scans_honor_master_and_independent_switches(self):
        for master, popular, niche in (
            (True, True, True), (False, True, True),
            (True, False, True), (True, True, False), (True, False, False),
        ):
            self.flags(master, popular, niche)
            for scan_type, operation in (
                ("popular", lambda: self.service.scan_popular("US")),
                ("niche", lambda: self.service.scan_keyword(1)),
                ("niche", lambda: self.service.scan_youtube_niche(1)),
            ):
                for call in vars(self.youtube).values():
                    call.reset_mock()
                with self.subTest(master=master, popular=popular, niche=niche,
                                  scan_type=scan_type, operation=operation):
                    enabled = master and (popular if scan_type == "popular" else niche)
                    if enabled:
                        self.assertEqual(await operation(), 0)
                        request = (self.youtube.get_trending_videos
                                   if scan_type == "popular" else self.youtube.search_videos)
                        self.assertGreater(request.await_count, 0)
                    else:
                        with self.assertRaises(YouTubeScanDisabledError):
                            await operation()
                        for call in vars(self.youtube).values():
                            call.assert_not_awaited()

    async def test_disable_during_keyword_search_prevents_detail_requests(self):
        async def search(**kwargs):
            self.flags(master=False)
            return {"items": [{"id": {"videoId": "video"}}]}

        self.youtube.search_videos.side_effect = search
        with self.assertRaises(YouTubeScanDisabledError):
            await self.service.scan_keyword(1)
        self.youtube.get_video_details.assert_not_awaited()
        self.youtube.get_channel_details.assert_not_awaited()

    async def test_disable_during_popular_fetch_prevents_detail_requests(self):
        async def trending(**kwargs):
            self.flags(popular=False)
            return {"items": [{"id": "video"}]}

        self.youtube.get_trending_videos.side_effect = trending
        with self.assertRaises(YouTubeScanDisabledError):
            await self.service.scan_popular("US")
        self.youtube.get_video_details.assert_not_awaited()
        self.youtube.get_channel_details.assert_not_awaited()

    async def test_niche_loop_does_not_swallow_disabled_scan(self):
        with patch.object(self.service, "scan_keyword", new_callable=AsyncMock) as scan:
            scan.side_effect = YouTubeScanDisabledError("Disabled")
            with self.assertRaises(YouTubeScanDisabledError):
                await self.service.scan_youtube_niche(1)
        scan.assert_awaited_once_with(1)

    async def test_scheduled_scans_skip_before_creating_youtube_clients(self):
        self.flags(master=False)
        with patch.object(jobs, "YouTubeClient") as client, patch.object(
            jobs, "get_all_niches", new_callable=AsyncMock,
        ) as niches:
            await jobs.scan_all_niches()
            result = await jobs.scan_popular_videos()
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["total_processed"], 0)
        niches.assert_not_awaited()
        client.assert_not_called()

    async def test_scheduled_niche_loop_stops_when_disabled(self):
        scan = AsyncMock(side_effect=YouTubeScanDisabledError("Disabled"))
        with patch.object(jobs, "get_all_niches", new_callable=AsyncMock) as niches, \
             patch.object(jobs, "NicheScanner", return_value=SimpleNamespace(scan_niche=scan)):
            niches.return_value = [SimpleNamespace(id=i, name=str(i)) for i in (1, 2)]
            await jobs.scan_all_niches()
        scan.assert_awaited_once_with(1)

    async def test_scheduled_popular_loop_stops_when_disabled(self):
        scan = AsyncMock(side_effect=[1, YouTubeScanDisabledError("Disabled")])
        with patch.object(jobs, "YouTubeScanService", return_value=SimpleNamespace(scan_popular=scan)):
            result = await jobs.scan_popular_videos(region_codes=["US", "IN", "GB"])
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["total_processed"], 1)
        self.assertEqual(scan.await_count, 2)

    async def test_manual_routes_and_debug_reject_disabled_scans(self):
        self.flags(master=False)
        with patch.object(youtube_routes, "YouTubeClient", return_value=self.youtube), \
             patch.object(jobs, "YouTubeClient", return_value=self.youtube), self.client() as client:
            for method, path, kwargs in (
                ("GET", "/niches/1", {}),
                ("POST", "/keywords/1", {}),
                ("POST", "/popular/scan", {}),
                ("POST", "/popular/scan", {"json": {
                    "region_codes": ["US"], "max_results": 10,
                    "youtube_scan_enabled": True, "popular_scan_enabled": True,
                }}),
                ("GET", "/debug-trending", {}),
            ):
                with self.subTest(path=path, kwargs=kwargs):
                    response = client.request(method, "/v1/admin/yt-scan" + path, **kwargs)
                    self.assertEqual(response.status_code, 409, response.text)
                    self.assertIn("disabled", response.json()["detail"].lower())
        self.assertFalse(self.row.youtube_scan_enabled)
        for call in vars(self.youtube).values():
            call.assert_not_awaited()

    async def test_enabled_manual_routes_still_scan(self):
        with patch.object(youtube_routes, "YouTubeClient", return_value=self.youtube), \
             patch.object(jobs, "YouTubeClient", return_value=self.youtube), self.client() as client:
            for method, path in (("GET", "/niches/1"), ("POST", "/keywords/1"),
                                 ("POST", "/popular/scan"), ("GET", "/debug-trending")):
                response = client.request(method, "/v1/admin/yt-scan" + path)
                self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(self.youtube.search_videos.await_count, 0)
        self.assertGreater(self.youtube.get_trending_videos.await_count, 0)

    async def test_admin_settings_roundtrip_controls_manual_scans(self):
        with self.client() as client:
            response = client.put("/v1/admin/yt-scan/popular/settings", json={
                "region_codes": ["US"], "max_results": 15,
                "youtube_scan_enabled": False, "popular_scan_enabled": False,
                "niche_scan_enabled": True,
            })
            self.assertEqual(response.status_code, 200, response.text)
            saved = client.get("/v1/admin/yt-scan/popular/settings").json()
            self.assertFalse(saved["youtube_scan_enabled"])
            self.assertFalse(saved["popular_scan_enabled"])
            self.assertTrue(saved["niche_scan_enabled"])
            blocked = client.post("/v1/admin/yt-scan/popular/scan")
            self.assertEqual(blocked.status_code, 409, blocked.text)

            # An existing region-only client cannot accidentally reenable scans.
            response = client.put("/v1/admin/yt-scan/popular/settings", json={
                "region_codes": ["IN"], "max_results": 20,
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(response.json()["youtube_scan_enabled"])
            self.assertFalse(response.json()["popular_scan_enabled"])

    async def test_missing_migration_returns_actionable_503(self):
        missing = YouTubeScanMigrationRequiredError()
        with patch.object(youtube_routes, "get_or_create_popular_scan_settings", new_callable=AsyncMock) as load, \
             patch.object(youtube_routes, "save_popular_scan_settings", new_callable=AsyncMock) as save, \
             patch.object(youtube_routes, "scan_popular_videos", new_callable=AsyncMock) as popular, \
             patch.object(scans, "ensure_youtube_scan_enabled", new_callable=AsyncMock) as guard, \
             self.client() as client:
            for operation in (load, save, popular, guard):
                operation.side_effect = missing
            for method, path, kwargs in (
                ("GET", "/popular/settings", {}),
                ("PUT", "/popular/settings", {"json": {"region_codes": ["US"]}}),
                ("POST", "/popular/scan", {}),
                ("GET", "/debug-trending", {}),
                ("GET", "/niches/1", {}),
                ("POST", "/keywords/1", {}),
            ):
                with self.subTest(path=path):
                    response = client.request(method, "/v1/admin/yt-scan" + path, **kwargs)
                    self.assertEqual(response.status_code, 503, response.text)
                    self.assertIn("011_youtube_scan_controls.sql", response.json()["detail"])
                    self.assertNotIn("SELECT", response.text)

    async def test_niche_loop_does_not_swallow_missing_migration(self):
        with patch.object(self.service, "scan_keyword", new_callable=AsyncMock) as scan:
            scan.side_effect = YouTubeScanMigrationRequiredError()
            with self.assertRaises(YouTubeScanMigrationRequiredError):
                await self.service.scan_youtube_niche(1)
        scan.assert_awaited_once_with(1)

    async def test_scan_settings_and_scans_require_admin(self):
        with self.client(authenticated=False) as client:
            for method, path, kwargs in (
                ("GET", "/popular/settings", {}),
                ("PUT", "/popular/settings", {"json": {
                    "region_codes": ["US"], "youtube_scan_enabled": False,
                }}),
                ("POST", "/popular/scan", {}),
                ("GET", "/niches/1", {}),
                ("POST", "/keywords/1", {}),
                ("GET", "/debug-trending", {}),
            ):
                response = client.request(method, "/v1/admin/yt-scan" + path, **kwargs)
                self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()
