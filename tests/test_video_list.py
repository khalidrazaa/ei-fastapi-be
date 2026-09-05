"""Exercise shared list routes and real SQL against an isolated SQLite database."""
import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.videos.video_routes import router
from app.db.models.niche import Niche, NicheKeyword
from app.db.models.trend_video import TrendVideo
from app.db.session import get_db
from app.services.yt_video_service.yt_video import get_video_list


class AsyncSessionAdapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, query):
        return self.session.execute(query)


class VideoQueryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        for model in (Niche, NicheKeyword, TrendVideo):
            model.__table__.create(self.engine)
        self.session = Session(self.engine)
        self.db = AsyncSessionAdapter(self.session)
        self.session.add_all([
            Niche(id=1, name="tech", display_name="Tech", region_code="IN"),
            Niche(id=2, name="games", display_name="Games", region_code="US"),
            NicheKeyword(id=1, niche_id=1, keyword="tech"),
            NicheKeyword(id=2, niche_id=1, keyword="science"),
            NicheKeyword(id=3, niche_id=2, keyword="games"),
        ])
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def add_video(self, identifier, **changes):
        values = dict(
            id=identifier, youtube_video_id=f"video-{identifier}",
            title=f"Video {identifier}", channel_title="Channel",
            view_count=10000, virality_score=8, speed_score=8,
            breakout_score=8, engagement_score=8, confidence_score=8,
            trend_stage="trending", category_title="Education", source="POPULAR",
            region_code="US", thumbnail_url="https://example.com/image.jpg",
            published_at=datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
        )
        values.update(changes)
        self.session.add(TrendVideo(**values))
        self.session.flush()

    async def test_deduplication_precedes_pagination_and_ties_are_stable(self):
        self.add_video(1, youtube_video_id="same", region_code="US")
        self.add_video(2, youtube_video_id="same", region_code="IN")
        self.add_video(3, virality_score=7)
        first = await get_video_list(self.db, page=1, size=1)
        second = await get_video_list(self.db, page=2, size=1)
        self.assertEqual(first["total"], 2)
        self.assertEqual(first["total_pages"], 2)
        self.assertEqual([v.id for v in first["items"]], [2])
        self.assertEqual([v.id for v in second["items"]], [3])
        self.assertTrue(first["has_next"])
        self.assertTrue(second["has_previous"])
        self.assertFalse(second["has_next"])

    async def test_each_filter_excludes_nonmatching_rows_in_both_scopes(self):
        cases = [
            ({"min_views": 1000}, {"view_count": 10}),
            ({"trend_stages": ["trending"]}, {"trend_stage": "watchlist"}),
            ({"sources": ["POPULAR"]}, {"source": "MANUAL"}),
            ({"category_titles": ["Education"]}, {"category_title": "Gaming"}),
            ({"min_score": 5}, {"virality_score": 4}),
            ({"min_speed_score": 5}, {"speed_score": 4}),
            ({"min_breakout_score": 5}, {"breakout_score": 4}),
            ({"min_engagement_score": 5}, {"engagement_score": 4}),
            ({"min_confidence_score": 5}, {"confidence_score": 4}),
        ]
        for filters, changes in cases:
            with self.subTest(filters=filters):
                self.session.query(TrendVideo).delete()
                self.add_video(1, keyword_id=1)
                self.add_video(2, keyword_id=2, **changes)
                for niche_id in (None, 1):
                    result = await get_video_list(self.db, niche_id=niche_id, **filters)
                    self.assertEqual([v.id for v in result["items"]], [1])
                    self.assertEqual(result["total"], 1)

    async def test_date_bounds_include_whole_end_day_and_accept_reversed_range(self):
        for identifier, day in enumerate((1, 2, 3, 4), start=1):
            self.add_video(identifier, published_at=datetime(2026, 9, day, 23, 59))
        result = await get_video_list(
            self.db, published_from=date(2026, 9, 3), published_to=date(2026, 9, 2)
        )
        self.assertEqual({v.id for v in result["items"]}, {2, 3})
        result = await get_video_list(self.db, published_from=date(2026, 9, 4))
        self.assertEqual([v.id for v in result["items"]], [4])
        result = await get_video_list(self.db, published_to=date(2026, 9, 1))
        self.assertEqual([v.id for v in result["items"]], [1])

    async def test_niche_scope_and_region_semantics_are_preserved(self):
        self.add_video(1, keyword_id=1, region_code="US")
        self.add_video(2, keyword_id=3, region_code="US")
        self.add_video(3, region_code="IN")
        niche = await get_video_list(self.db, niche_id=1, region_codes=["in"])
        popular = await get_video_list(self.db, region_codes=["in"])
        self.assertEqual([v.id for v in niche["items"]], [1])
        self.assertEqual([v.id for v in popular["items"]], [3])

    async def test_empty_results_keep_pagination_structure(self):
        result = await get_video_list(self.db)
        self.assertEqual(result, dict(
            items=[], total=0, page=1, size=20, total_pages=0,
            has_next=False, has_previous=False,
        ))


class VideoRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: None
        self.client = TestClient(app)

    def test_both_routes_normalize_filters_and_return_identical_envelopes(self):
        response = dict(
            items=[], total=0, page=2, size=10, total_pages=0,
            has_next=False, has_previous=True,
        )
        params = [
            ("page", "2"), ("size", "10"), ("min_views", "1000"),
            ("published_from", "2026-09-01"), ("published_to", "2026-09-03"),
            ("trend_stage", "trending,breakout"), ("trend_stage", "emerging"),
            ("source", "POPULAR"), ("region_code", "US, IN"),
            ("category_title", "Education"), ("min_score", "5"),
            ("min_speed_score", "5"), ("min_breakout_score", "5"),
            ("min_engagement_score", "5"), ("min_confidence_score", "5"),
        ]
        calls = []
        for path in ("/popular", "/niches/1"):
            with patch(
                "app.api.videos.video_routes.get_video_list",
                new_callable=AsyncMock, return_value=response,
            ) as service:
                result = self.client.get(path, params=params)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json(), response)
                calls.append(service.call_args.kwargs)
        self.assertEqual(calls[1].pop("niche_id"), 1)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(calls[0]["trend_stages"], ["trending", "breakout", "emerging"])
        self.assertEqual(calls[0]["region_codes"], ["US", "IN"])
        self.assertEqual(calls[0]["published_from"], date(2026, 9, 1))
        self.assertEqual(calls[0]["page"], 2)
        self.assertEqual(calls[0]["size"], 10)

    def test_both_routes_reject_invalid_pagination_and_filters(self):
        for path in ("/popular", "/niches/1"):
            for params in (
                {"page": 0}, {"size": 0}, {"size": 101}, {"min_views": -1},
                {"min_score": -1}, {"published_from": "invalid"},
            ):
                with self.subTest(path=path, params=params):
                    self.assertEqual(self.client.get(path, params=params).status_code, 422)


if __name__ == "__main__":
    unittest.main()
