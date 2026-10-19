"""Persist scan controls and verify both migration histories in isolated SQLite."""

import importlib.util
import unittest
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import (
    JSON, Column, DateTime, Integer, MetaData, String, Table, create_engine,
    func, inspect, select, text, update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.popular_scan_setting import PopularScanSetting
from app.db.query import popular_scan_setting as query
from app.schemas.youtube import PopularScanSettingsOut, PopularScanSettingsUpdate
from app.services import popular_scan_settings as service


CONTROL_FIELDS = (
    "youtube_scan_enabled", "popular_scan_enabled", "niche_scan_enabled"
)


class Adapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, value):
        self.session.add(value)

    async def commit(self):
        self.session.commit()

    async def refresh(self, value):
        self.session.refresh(value)


class YouTubeScanSettingsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        PopularScanSetting.__table__.create(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.addCleanup(lambda: self.session.close())
        self.db = Adapter(self.session)

    async def save(self, **changes):
        return await service.save_popular_scan_settings(
            self.db, region_codes=["IN"], max_results=25, **changes
        )

    def assert_controls(self, result, **changes):
        expected = {field: True for field in CONTROL_FIELDS} | changes
        self.assertEqual({field: result[field] for field in CONTROL_FIELDS}, expected)

    async def test_default_creation_enables_all_scan_types(self):
        result = await service.get_or_create_popular_scan_settings(self.db)
        self.assert_controls(result)
        self.assertEqual(result["region_codes"], ["US"])
        self.assertEqual(result["max_results"], 10)
        self.assertEqual(PopularScanSettingsOut(**result).model_dump(), result)
        await service.ensure_youtube_scan_enabled(self.db, "popular")
        await service.ensure_youtube_scan_enabled(self.db, "niche")

    async def test_first_save_and_new_session_preserve_disabled_flags(self):
        disabled = {field: False for field in CONTROL_FIELDS}
        saved = await self.save(**disabled)
        self.assert_controls(saved, **disabled)
        self.session.close()
        self.session = Session(self.engine, expire_on_commit=False)
        self.db = Adapter(self.session)
        self.assertEqual(
            await service.get_or_create_popular_scan_settings(self.db), saved
        )

    async def test_legacy_save_preserves_flags_and_explicit_save_reenables(self):
        disabled = {field: False for field in CONTROL_FIELDS}
        await self.save(**disabled)
        legacy_payload = PopularScanSettingsUpdate(region_codes=["IN"], max_results=25)
        self.assert_controls(
            await service.save_popular_scan_settings(
                self.db, **legacy_payload.model_dump()
            ),
            **disabled,
        )
        for field in CONTROL_FIELDS:
            disabled[field] = True
            self.assert_controls(await self.save(**{field: True}), **disabled)

    async def test_region_refresh_and_normalization_preserve_controls(self):
        disabled = {field: False for field in CONTROL_FIELDS}
        await self.save(**disabled)
        await service.save_popular_scan_regions(
            self.db, available_regions=[{"code": "in", "name": "India"}]
        )
        current = await service.get_or_create_popular_scan_settings(self.db)
        self.assert_controls(current, **disabled)
        self.assertEqual(current["available_regions"], [{"code": "IN", "name": "India"}])

        # Exercise fallback refresh and legacy malformed settings normalization.
        setting = await query.get_popular_scan_setting(self.db)
        setting.region_codes = [" in ", "IN"]
        setting.available_regions = []
        setting.max_results = 80
        self.session.commit()
        await service.save_popular_scan_regions(self.db, available_regions=[])
        normalized = await service.get_or_create_popular_scan_settings(self.db)
        self.assert_controls(normalized, **disabled)
        self.assertEqual(normalized["region_codes"], ["IN"])
        self.assertEqual(normalized["max_results"], 50)

        setting.region_codes = [" us ", "US"]
        self.session.commit()
        normalized = await service.get_or_create_popular_scan_settings(self.db)
        self.assertEqual(normalized["region_codes"], ["US"])
        self.assert_controls(normalized, **disabled)

    async def test_global_switch_overrides_each_scan_type_without_resetting_them(self):
        await self.save(youtube_scan_enabled=False, niche_scan_enabled=False)
        for scan_type in ("popular", "niche"):
            with self.subTest(scan_type=scan_type), self.assertRaisesRegex(
                service.YouTubeScanDisabledError, "All YouTube video scanning"
            ):
                await service.ensure_youtube_scan_enabled(self.db, scan_type)

        await self.save(youtube_scan_enabled=True)
        await service.ensure_youtube_scan_enabled(self.db, "popular")
        with self.assertRaisesRegex(service.YouTubeScanDisabledError, "niche scanning"):
            await service.ensure_youtube_scan_enabled(self.db, "niche")
        await self.save(niche_scan_enabled=True, popular_scan_enabled=False)
        await service.ensure_youtube_scan_enabled(self.db, "niche")
        with self.assertRaisesRegex(service.YouTubeScanDisabledError, "popular scanning"):
            await service.ensure_youtube_scan_enabled(self.db, "popular")

    async def test_long_lived_session_observes_control_changes_in_other_session(self):
        await self.save()
        # Keep the ORM object alive in the first session's identity map.
        cached = await query.get_popular_scan_setting(self.db)
        self.assertTrue(cached.youtube_scan_enabled)
        with Session(self.engine) as admin_session:
            admin_session.execute(
                update(PopularScanSetting).values(youtube_scan_enabled=False)
            )
            admin_session.commit()
        with self.assertRaisesRegex(service.YouTubeScanDisabledError, "All YouTube"):
            await service.ensure_youtube_scan_enabled(self.db, "popular")
        self.assertFalse(cached.youtube_scan_enabled)
        with Session(self.engine) as admin_session:
            admin_session.execute(
                update(PopularScanSetting).values(youtube_scan_enabled=True)
            )
            admin_session.commit()
        await service.ensure_youtube_scan_enabled(self.db, "popular")
        self.assertTrue(cached.youtube_scan_enabled)

    def test_update_contract_allows_omitted_flags_but_output_requires_flags(self):
        self.assertEqual(
            PopularScanSettingsUpdate(region_codes=["US"]).model_dump(),
            {"region_codes": ["US"], "max_results": 10,
             **{field: None for field in CONTROL_FIELDS}},
        )
        with self.assertRaises(ValidationError):
            PopularScanSettingsOut(region_codes=["US"], max_results=10)


class YouTubeScanControlsMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.legacy_metadata = MetaData()
        self.legacy_table = Table(
            "popular_scan_settings", self.legacy_metadata,
            Column("key", String, primary_key=True),
            Column("region_codes", JSON, nullable=False),
            Column("available_regions", JSON, nullable=False),
            Column("max_results", Integer, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False,
                   server_default=func.now()),
            Column("updated_at", DateTime(timezone=True), nullable=False,
                   server_default=func.now()),
        )
        self.legacy_metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(self.legacy_table.insert().values(
                key="default", region_codes=["IN"],
                available_regions=[{"code": "IN", "name": "India"}], max_results=25,
            ))
        root = Path(__file__).resolve().parents[1]
        path = root / "alembic" / "versions" / "c03_youtube_scan_controls.py"
        spec = importlib.util.spec_from_file_location("scan_controls_migration", path)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        self.sql_path = (
            root / "migrations" / "history_sql_mig" / "011_youtube_scan_controls.sql"
        )

    def apply(self, function):
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                function()

    def assert_current_schema_and_data(self):
        metadata = MetaData()
        PopularScanSetting.__table__.to_metadata(metadata)
        with self.engine.connect() as connection:
            self.assertEqual(
                compare_metadata(MigrationContext.configure(connection), metadata), []
            )
            row = connection.execute(select(PopularScanSetting.__table__)).mappings().one()
            self.assertEqual(row["region_codes"], ["IN"])
            self.assertEqual(row["max_results"], 25)
            self.assertTrue(all(row[field] for field in CONTROL_FIELDS))
        columns = {column["name"]: column for column in inspect(self.engine).get_columns(
            "popular_scan_settings"
        )}
        for field in CONTROL_FIELDS:
            self.assertFalse(columns[field]["nullable"])
            self.assertIsNotNone(columns[field]["default"])
            with self.subTest(field=field), self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.execute(text(
                        f"UPDATE popular_scan_settings SET {field} = NULL"
                    ))
        # Verify server defaults apply to a future raw insert too.
        with self.engine.begin() as connection:
            connection.execute(self.legacy_table.insert().values(
                key="future", region_codes=["US"], available_regions=[], max_results=10
            ))
            row = connection.execute(
                select(PopularScanSetting.__table__).where(PopularScanSetting.key == "future")
            ).mappings().one()
            self.assertTrue(all(row[field] for field in CONTROL_FIELDS))
            connection.execute(self.legacy_table.delete().where(
                self.legacy_table.c.key == "future"
            ))

    def test_alembic_upgrade_backfills_and_downgrade_preserves_original_settings(self):
        self.assertEqual(self.migration.down_revision, "c02_research_settings")
        self.apply(self.migration.upgrade)
        self.assert_current_schema_and_data()
        self.apply(self.migration.downgrade)
        with self.engine.connect() as connection:
            self.assertEqual(compare_metadata(
                MigrationContext.configure(connection), self.legacy_metadata
            ), [])
            self.assertEqual(connection.execute(select(
                self.legacy_table.c.region_codes
            )).scalar_one(), ["IN"])
        self.apply(self.migration.upgrade)
        self.assert_current_schema_and_data()

    def test_sql_history_backfills_and_matches_current_model(self):
        with self.engine.begin() as connection:
            for statement in self.sql_path.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    connection.execute(text(statement))
        self.assert_current_schema_and_data()
