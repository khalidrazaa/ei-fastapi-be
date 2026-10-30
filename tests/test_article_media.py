"""Exercise real batch persistence and filesystem failures using isolated SQLite."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import zlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from markdown_it import MarkdownIt
from sqlalchemy import JSON, MetaData, create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.article import article_media_routes, article_routes
from app.core.admin_security import require_admin
from app.core import security
from app.db.models.article import Article
from app.db.models.article_image import ArticleImage, ArticleImport
from app.db.session import get_db
from app.services import admin_auth_service, article_media_service
from app.services.article_image_validation import validate_png, validate_svg
from app.services.article_markdown_images import markdown_images, resolve_images, rewrite_images
from app.services.article_media_reconcile import reconciliation_candidates

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50" viewBox="0 0 100 50"><defs><marker id="arrow" markerWidth="4" markerHeight="4"><path d="M0 0 L4 2 L0 4"/></marker><linearGradient id="g"><stop offset="0" stop-color="red"/></linearGradient></defs><style>.label { font-size: 12px; fill: #123; }</style><path style="stroke: black; marker-end: url(#arrow)" d="M0 0 L40 40"/><text class="label" x="2" y="20">Hello &amp; diagram</text></svg>'


def png(width=1, height=1):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress((b"\0" + b"\0\0\0\xff" * width) * height)) + chunk(b"IEND", b"")


class AsyncSessionAdapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def flush(self):
        self.session.flush()

    async def refresh(self, value):
        self.session.refresh(value)

    def add(self, value):
        self.session.add(value)


class ImageValidationTests(unittest.TestCase):
    def test_native_svg_retains_text_styles_and_internal_references(self):
        result = validate_svg(SVG, 1_000_000)
        self.assertIn(b"Hello &amp; diagram", result)
        self.assertIn(b"url(#arrow)", result)
        self.assertIn(b"linearGradient", result)
        self.assertIn(b"font-size: 12px", result)

    def test_svg_rejects_active_external_and_unsupported_content(self):
        for element in (
            '<script>alert(1)</script>', '<foreignObject><div>Label</div></foreignObject>',
            '<path onload="x"/>', '<path ONLOAD="x"/>', '<use href="https://evil.example/x"/>',
            '<image href="data:image/svg+xml;base64,AAAA"/>',
            '<style>@import "https://evil.example/x";</style>',
            '<path style="fill: url(https://evil.example/x)"/>',
            '<path style="fill: u\\72l(https://evil.example/x)"/>',
            '<path style="fill: u/**/rl(https://evil.example/x)"/>',
            '<text xmlns="http://www.w3.org/1999/xhtml">HTML</text>',
        ):
            with self.subTest(element=element), self.assertRaises(ValueError):
                validate_svg(f'<svg xmlns="http://www.w3.org/2000/svg">{element}</svg>'.encode(), 1_000_000)
        for document in (
            b'<!DOCTYPE svg [<!ENTITY x "x">]><svg xmlns="http://www.w3.org/2000/svg"/>',
            b'<?xml-stylesheet href="https://evil.example/x"?><svg xmlns="http://www.w3.org/2000/svg"/>',
            b'<svg xmlns="http://www.w3.org/2000/svg" width="999999" height="999999"/>',
            '<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>'.encode("utf-16"),
        ):
            with self.subTest(document=document), self.assertRaises(ValueError):
                validate_svg(document, 1_000_000)

    def test_png_signature_crc_dimensions_and_pixel_stream_are_validated(self):
        valid = png()
        self.assertEqual(validate_png(valid, 1_000_000), valid)
        for data in (b"not png", valid[:-1], valid[:-9] + b"x" + valid[-8:], png(2, 2) + b"trailing"):
            with self.subTest(data=data[:12]), self.assertRaises(ValueError):
                validate_png(data, 1_000_000)
        with self.assertRaises(ValueError):
            validate_png(png(2, 2), 3)


class MarkdownImageTests(unittest.TestCase):
    def rewrite(self, source, files, manifest=None):
        text, resolved = resolve_images(source, files, manifest or {})
        return rewrite_images(text, resolved, {name: f"https://api.example/v1/{name}" for name in files})

    def test_inline_reference_collapsed_and_shortcut_images_preserve_code_and_links(self):
        source = '''![one](images/flow.svg "Flow")
![two][diagram]
![diagram][] and ![diagram]
[ordinary](images/flow.svg)
`![example](images/missing.svg)`
```markdown
![example](images/missing.svg)
```
[diagram]: images/flow.svg "Reference"
'''
        result = self.rewrite(source, ["flow.svg"])
        self.assertEqual(result.count("https://api.example/v1/flow.svg"), 4)
        self.assertIn('[ordinary](images/flow.svg)', result)
        self.assertIn('`![example](images/missing.svg)`', result)
        self.assertIn('```markdown\n![example](images/missing.svg)\n```', result)
        self.assertIn('![two](<https://api.example/v1/flow.svg> "Reference")', result)

    def test_quotes_lists_tables_spaces_and_balanced_parentheses(self):
        source = '> ![a](<folder/a b.svg>)\n\n- ![b](folder/flow(1).png)\n\n| Diagram | Again |\n|---|---|\n| ![a](<folder/a b.svg>) | ![a](<folder/a b.svg>) |\n'
        result = self.rewrite(source, ["a b.svg", "flow(1).png"])
        self.assertEqual(result.count("https://api.example/v1/a b.svg"), 3)
        self.assertIn('- ![b](<https://api.example/v1/flow(1).png>)', result)

    def test_explicit_manifest_can_replace_external_and_root_images(self):
        source = '![a](https://old.example/a.svg) ![b](/images/a.svg)'
        result = self.rewrite(source, ["new.svg"], {"https://old.example/a.svg": "new.svg", "/images/a.svg": "new.svg"})
        self.assertEqual(result.count("https://api.example/v1/new.svg"), 2)

    def test_svg_png_formats_match_same_diagram_name_without_manifest(self):
        for reference, filename in (
            ("diagrams/flow.png", "flow.svg"),
            ("diagrams/flow.svg", "flow.png"),
            ("diagrams/flow.PNG", "flow.SVG"),
            ("diagrams/flow.SVG", "flow.PNG"),
        ):
            with self.subTest(reference=reference, filename=filename):
                result = self.rewrite(f'![Diagram]({reference})', [filename])
                self.assertEqual(result, f'![Diagram](<https://api.example/v1/{filename}>)')

    def test_exact_filenames_and_paths_take_priority_over_format_fallback(self):
        for source, files, expected in (
            (
                '![primary](diagrams/flow.png) ![other](flow.svg)',
                ["flow.png", "flow.svg"], "flow.png",
            ),
            (
                '![primary](diagrams/flow.png) ![other](other/flow.png)',
                ["diagrams/flow.png", "other/flow.png"], "diagrams/flow.png",
            ),
            (
                '![primary](diagrams/flow.png) ![other](diagrams/flow.svg)',
                ["flow.png", "diagrams/flow.svg"], "flow.png",
            ),
            (
                '![primary](diagrams/flow.png) ![other](other/flow.svg)',
                ["diagrams/flow.svg", "other/flow.svg"], "diagrams/flow.svg",
            ),
        ):
            with self.subTest(files=files):
                _, resolved = resolve_images(source, files, {})
                self.assertEqual(resolved[0][1], expected)

    def test_format_fallback_rejects_ambiguity_and_unrelated_names(self):
        for reference, files in (
            ("diagrams/flow.png", ["one/flow.svg", "two/flow.svg"]),
            ("flow.png", ["flow.svg", "flow.SVG"]),
            ("diagrams/flow.png", ["one/flow.png", "two/flow.png", "diagrams/flow.svg"]),
            ("flow.jpg", ["flow.svg"]),
            ("flow.png", ["different.svg"]),
        ):
            with self.subTest(reference=reference, files=files), self.assertRaises(ValueError):
                resolve_images(f'![Diagram]({reference})', files, {})

    def test_manifest_overrides_automatic_matching_and_external_images_remain(self):
        source = '![chosen](diagrams/flow.png) ![other](flow.png) ![external](https://images.example/flow.png)'
        result = self.rewrite(source, ["flow.png", "replacement.svg"], {"diagrams/flow.png": "replacement.svg"})
        self.assertIn('![chosen](<https://api.example/v1/replacement.svg>)', result)
        self.assertIn('![other](<https://api.example/v1/flow.png>)', result)
        self.assertIn('![external](https://images.example/flow.png)', result)

    def test_table_code_cell_is_not_mistaken_for_matching_real_image_cell(self):
        source = '| Code | Image |\n|---|---|\n| `![a](flow.svg)` | ![a](flow.svg) |\n'
        result = self.rewrite(source, ["flow.svg"])
        self.assertIn('`![a](flow.svg)`', result)
        self.assertIn('| ![a](<https://api.example/v1/flow.svg>) |', result)

    def test_table_image_preserves_escaped_pipes_in_alt_and_title(self):
        source = '| Diagram |\n|---|\n| ![left\\|right](flow.svg "left\\|right") |\n'
        result = self.rewrite(source, ["flow.svg"])
        self.assertIn('![left\\|right](<https://api.example/v1/flow.svg> "left\\|right")', result)
        rendered = MarkdownIt("commonmark").enable("table").render(result)
        self.assertEqual(rendered.count("<td>"), 1)
        self.assertIn('alt="left|right" title="left|right"', rendered)

    def test_missing_unreferenced_traversal_and_false_manifest_rejected(self):
        for source, files, manifest in (
            ('![a](missing.svg)', [], {}), ('Nothing', ['a.svg'], {}),
            ('![a](../a.svg)', ['a.svg'], {}), ('Nothing', ['a.svg'], {'a.svg': 'a.svg'}),
            ('![a](a.svg)', ['a.svg'], {'a.svg': 'missing.svg'}),
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.rewrite(source, files, manifest)


class ArticleMediaTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(TemporaryDirectory())
        self.root = Path(self.directory)
        self.enterContext(patch.object(article_media_service.settings, "MEDIA_ROOT", self.directory))
        self.enterContext(patch.object(article_media_service.settings, "MEDIA_PUBLIC_BASE_URL", "https://api.example/v1"))
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "connect")
        def enable_fk(connection, _):
            connection.execute("PRAGMA foreign_keys = ON")

        metadata = MetaData()
        # These tests insert through the real ORM, so replace the bind types too.
        self.enterContext(patch.object(Article.__table__.c.tags, "type", JSON()))
        self.enterContext(patch.object(Article.__table__.c.keywords, "type", JSON()))
        article_table = Article.__table__.to_metadata(metadata)
        article_table.c.tags.type = JSON()
        article_table.c.keywords.type = JSON()
        ArticleImage.__table__.to_metadata(metadata)
        ArticleImport.__table__.to_metadata(metadata)
        metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.session.close)
        self.db = AsyncSessionAdapter(self.session)
        app = FastAPI()
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id="test-admin")
        app.dependency_overrides[get_db] = lambda: self.db
        app.include_router(article_routes.router, prefix="/v1/admin/articles")
        app.include_router(article_media_routes.router, prefix="/v1/media")
        self.app = app
        self.client = self.enterContext(TestClient(app))

    def submit(self, *, source='![diagram](images/flow.svg)', images=None, manifest=None, request_id=None, path="/v1/admin/articles/import", payload=None, method="POST", headers=None):
        body = {"title": "Diagram article", "slug": "diagram-article", "content": source, **(payload or {})}
        data = {"article": json.dumps(body), "manifest": json.dumps(manifest or {}), "request_id": request_id or str(uuid4())}
        files = [("images", image) for image in (images if images is not None else [("flow.svg", SVG, "image/svg+xml")])]
        return self.client.request(method, path, data=data, files=files, headers=headers)

    def stored_files(self):
        return list((self.root / "articles").glob("*/*"))

    def test_import_saves_associated_images_canonical_markdown_and_public_media(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.text)
        article = response.json()
        self.assertEqual(article["status"], "draft")
        image = self.session.scalars(select(ArticleImage)).one()
        self.assertEqual(image.article_id, article["id"])
        url = f'https://api.example/v1/media/articles/{article["id"]}/{image.storage_name}'
        self.assertIn(url, article["content"])
        media = self.client.get(url.replace("https://api.example", ""))
        self.assertEqual(media.status_code, 200)
        self.assertIn("image/svg+xml", media.headers["content-type"])
        self.assertEqual(media.headers["x-content-type-options"], "nosniff")
        self.assertIn("sandbox", media.headers["content-security-policy"])
        self.assertIn("immutable", media.headers["cache-control"])
        self.assertIn(b"Hello &amp; diagram", media.content)
        self.assertEqual(list((self.root / ".staging").iterdir()), [])

    def test_svg_and_png_save_together_in_one_article_import(self):
        response = self.submit(
            source='![Architecture](diagrams/flow.svg)\n\n![Workflow](workflow.png)',
            images=[("flow.svg", SVG, "image/svg+xml"), ("workflow.png", png(), "image/png")],
        )
        self.assertEqual(response.status_code, 201, response.text)
        article = response.json()
        records = list(self.session.scalars(select(ArticleImage)))
        self.assertEqual(len(records), 2)
        self.assertEqual({image.article_id for image in records}, {article["id"]})
        self.assertEqual(len(list(self.session.scalars(select(Article)))), 1)
        for image in records:
            path = f'/v1/media/articles/{article["id"]}/{image.storage_name}'
            self.assertIn(f'https://api.example{path}', article["content"])
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(len(self.stored_files()), 2)

    def test_png_markdown_reference_can_save_and_serve_matching_svg(self):
        response = self.submit(source='![Diagram](images/flow.png)')
        self.assertEqual(response.status_code, 201, response.text)
        article = response.json()
        image = self.session.scalars(select(ArticleImage)).one()
        self.assertTrue(image.storage_name.endswith(".svg"))
        self.assertEqual(image.mime_type, "image/svg+xml")
        path = f'/v1/media/articles/{article["id"]}/{image.storage_name}'
        self.assertEqual(article["content"], f'![Diagram](<https://api.example{path}>)')
        media = self.client.get(path)
        self.assertEqual(media.status_code, 200)
        self.assertIn("image/svg+xml", media.headers["content-type"])
        self.assertIn(b"Hello &amp; diagram", media.content)

    def test_same_request_replays_exact_response_without_duplicate_article_or_files(self):
        key = str(uuid4())
        first = self.submit(request_id=key)
        second = self.submit(request_id=key)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(len(list(self.session.scalars(select(Article)))), 1)
        self.assertEqual(len(self.stored_files()), 1)
        changed = self.submit(request_id=key, source='Changed ![diagram](images/flow.svg)')
        self.assertEqual(changed.status_code, 409)

    def test_bad_second_image_does_not_save_article_receipt_or_any_files(self):
        response = self.submit(source='![a](flow.svg) ![b](bad.png)', images=[("flow.svg", SVG, "image/svg+xml"), ("bad.png", b"not png", "image/png")])
        self.assertEqual(response.status_code, 400)
        self.assertIn("PNG", response.json()["detail"])
        self.assertEqual(list(self.session.scalars(select(Article))), [])
        self.assertEqual(list(self.session.scalars(select(ArticleImport))), [])
        self.assertEqual(self.stored_files(), [])

    def test_missing_import_table_returns_migration_error_and_cleans_staging(self):
        ArticleImport.__table__.drop(self.engine)
        response = self.submit()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("012_article_images.sql or c04_article_images", response.json()["detail"])
        self.assertNotIn("SELECT", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(list(self.session.scalars(select(Article))), [])
        self.assertEqual(self.stored_files(), [])
        self.assertEqual(list((self.root / ".staging").iterdir()), [])

    def test_missing_image_table_rolls_back_article_and_receipt(self):
        ArticleImage.__table__.drop(self.engine)
        response = self.submit()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("article image upload database migration", response.json()["detail"])
        self.assertEqual(list(self.session.scalars(select(Article))), [])
        self.assertEqual(list(self.session.scalars(select(ArticleImport))), [])
        self.assertEqual(self.stored_files(), [])
        self.assertEqual(list((self.root / ".staging").iterdir()), [])

    def test_missing_import_column_returns_migration_error(self):
        self.session.execute(text("ALTER TABLE article_imports DROP COLUMN response"))
        self.session.commit()
        response = self.submit()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("c04_article_images", response.json()["detail"])
        self.assertEqual(list(self.session.scalars(select(Article))), [])
        self.assertEqual(self.stored_files(), [])

    def test_missing_image_insert_column_rolls_back_without_finalizing_files(self):
        self.session.execute(text("ALTER TABLE article_images DROP COLUMN sha256"))
        self.session.commit()
        response = self.submit()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(list(self.session.scalars(select(Article))), [])
        self.assertEqual(list(self.session.scalars(select(ArticleImport))), [])
        self.assertEqual(self.stored_files(), [])

    def test_public_media_missing_table_or_column_returns_uncached_migration_error(self):
        self.session.execute(text("ALTER TABLE article_images DROP COLUMN mime_type"))
        self.session.commit()
        path = '/v1/media/articles/1/' + uuid4().hex + '.svg'
        missing_column = self.client.get(path)
        self.assertEqual(missing_column.status_code, 503, missing_column.text)
        self.assertIn("c04_article_images", missing_column.json()["detail"])
        self.assertEqual(missing_column.headers["cache-control"], "no-store")
        self.assertNotIn("SELECT", missing_column.text)
        ArticleImage.__table__.drop(self.engine)
        missing_table = self.client.get(path)
        self.assertEqual(missing_table.status_code, 503, missing_table.text)
        self.assertEqual(missing_table.headers["cache-control"], "no-store")

    def test_markdown_json_larger_than_one_mib_is_accepted(self):
        source = "A" * (1024 * 1024 + 100) + '\n![diagram](flow.svg)'
        response = self.submit(source=source)
        self.assertEqual(response.status_code, 201, response.text[:1000])
        self.assertGreater(len(response.json()["content"]), 1024 * 1024)

    def test_total_limit_includes_reviewed_markdown_and_metadata(self):
        with patch.object(article_media_service.settings, "MEDIA_MAX_BATCH_BYTES", len(SVG) + 20):
            response = self.submit()
        self.assertEqual(response.status_code, 400)
        self.assertIn("total upload limit", response.json()["detail"])
        self.assertEqual(self.stored_files(), [])

    def test_missing_image_duplicate_names_and_limits_are_rejected(self):
        for options in (
            {"images": []},
            {"images": [("flow.svg", SVG, "image/svg+xml")] * 2},
            {"source": '![a](flow.jpg)', "images": [("flow.jpg", png(), "image/jpeg")]},
            {"request_id": "not-a-uuid"},
            {"manifest": {"wrong.svg": "flow.svg"}},
        ):
            with self.subTest(options=options):
                response = self.submit(**options)
                self.assertEqual(response.status_code, 400, response.text)
        with patch.object(article_media_service.settings, "MEDIA_MAX_IMAGE_BYTES", 10):
            self.assertEqual(self.submit().status_code, 400)
        self.assertEqual(self.stored_files(), [])

    def test_database_commit_failure_rolls_back_and_compensates_finalized_files(self):
        with patch.object(self.db, "commit", new_callable=AsyncMock, side_effect=RuntimeError("commit failure")):
            with self.assertRaisesRegex(RuntimeError, "commit failure"):
                self.submit()
        self.assertEqual(list(self.session.scalars(select(Article))), [])
        self.assertEqual(list(self.session.scalars(select(ArticleImage))), [])
        self.assertEqual(self.stored_files(), [])

    def test_uncertain_successful_commit_retains_files_for_idempotent_retry(self):
        original_commit = self.db.commit

        async def ambiguous_commit():
            await original_commit()
            raise RuntimeError("response lost")

        key = str(uuid4())
        with patch.object(self.db, "commit", side_effect=ambiguous_commit):
            with self.assertRaisesRegex(RuntimeError, "response lost"):
                self.submit(request_id=key)
        self.assertEqual(len(self.stored_files()), 1)
        retried = self.submit(request_id=key)
        self.assertEqual(retried.status_code, 201, retried.text)
        self.assertEqual(len(self.stored_files()), 1)

    def test_failed_rename_leaves_no_saved_article_or_image(self):
        with self.assertLogs(article_routes.logger, level="ERROR"), patch.object(article_media_service.os, "replace", side_effect=OSError("disk unavailable")):
            response = self.submit()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(list(self.session.scalars(select(Article))), [])
        self.assertEqual(self.stored_files(), [])

    def test_update_import_is_atomic_and_preserves_optimistic_lock(self):
        first = self.submit().json()
        path = f'/v1/admin/articles/{first["id"]}/import'
        payload = {"expected_updated_at": first["updated_at"], "status": "published"}
        updated = self.submit(source='Updated ![new](new.png)', images=[("new.png", png(), "image/png")], path=path, method="PUT", payload=payload)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["status"], "published")
        self.assertIn(".png", updated.json()["content"])
        stale = self.submit(source='Stale ![new](new.png)', images=[("new.png", png(), "image/png")], path=path, method="PUT", payload={"expected_updated_at": "2000-01-01T00:00:00Z"})
        self.assertEqual(stale.status_code, 400)
        self.assertEqual(len(self.stored_files()), 2)
        self.assertEqual(self.session.get(Article, first["id"]).content, updated.json()["content"])

    def test_deleted_article_keeps_media_records_files_and_receipt(self):
        first = self.submit().json()
        image = self.session.scalars(select(ArticleImage)).one()
        media_path = f'/v1/media/articles/{first["id"]}/{image.storage_name}'
        self.assertEqual(self.client.delete(f'/v1/admin/articles/{first["id"]}').status_code, 200)
        self.session.expire_all()
        self.assertIsNone(self.session.get(ArticleImage, image.id).article_id)
        self.assertEqual(self.client.get(media_path).status_code, 200)
        self.assertEqual(len(self.stored_files()), 1)

    def test_import_requires_admin_and_public_path_cannot_escape_root(self):
        del self.app.dependency_overrides[require_admin]
        self.assertEqual(self.submit().status_code, 401)
        self.assertEqual(self.client.get('/v1/media/articles/1/not-a-uuid.svg').status_code, 404)

    def test_cookie_import_checks_origin_before_accepting_upload(self):
        del self.app.dependency_overrides[require_admin]
        secret = "isolated-media-auth-test-secret"
        token = jwt.encode({"sub": "admin@example.com", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, secret, algorithm="HS256")
        self.client.cookies.set("access_token", token)
        with patch.object(security, "SECRET_KEY", secret), patch.object(security, "ALGORITHM", "HS256"), patch.object(admin_auth_service, "settings", SimpleNamespace(CORS_ORIGINS="https://admin.example")), patch.object(admin_auth_service, "get_admin_user_by_email", new_callable=AsyncMock, return_value=SimpleNamespace(id="test-admin", is_active=True)):
            self.assertEqual(self.submit().status_code, 403)
            self.assertEqual(self.submit(headers={"Origin": "https://evil.example"}).status_code, 403)
            accepted = self.submit(headers={"Origin": "https://admin.example"})
            self.assertEqual(accepted.status_code, 201, accepted.text)

    def test_reconciliation_retains_recorded_media_and_fresh_files(self):
        self.submit()
        retained = self.stored_files()[0]
        orphan = retained.with_name(uuid4().hex + ".svg")
        orphan.write_bytes(SVG)
        fresh = retained.with_name(uuid4().hex + ".png")
        fresh.write_bytes(png())
        stage = self.root / ".staging" / uuid4().hex
        stage.mkdir()
        for path in (retained, orphan, stage):
            os.utime(path, (1, 1))
        recorded = {retained.relative_to(self.root).as_posix()}
        candidates = reconciliation_candidates(self.root, recorded, cutoff=100)
        self.assertEqual(set(candidates), {orphan, stage})


if __name__ == "__main__":
    unittest.main()
