"""Exercise Alembic URL handling without connecting to deployment databases."""

import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine


ROOT = Path(__file__).resolve().parents[1]
ENCODED_URL = (
    "postgresql+psycopg2://test:test%2Bvalue%3D%25%40@localhost/example_test"
)


class AlembicEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.config = Config(output_buffer=self.output, stdout=io.StringIO())
        self.config.set_main_option("script_location", str(ROOT / "alembic"))
        self.enterContext(patch.dict(os.environ, {"ALEMBIC_DATABASE_URL": ENCODED_URL}))
        self.enterContext(patch("dotenv.load_dotenv"))

    def test_current_preserves_encoded_url_when_creating_engine(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        observed_urls = []

        def isolated_engine(configuration, **kwargs):
            observed_urls.append(configuration["sqlalchemy.url"])
            return engine

        with patch("sqlalchemy.engine_from_config", side_effect=isolated_engine):
            command.current(self.config)

        self.assertEqual(observed_urls, [ENCODED_URL])

    def test_offline_upgrade_accepts_encoded_url_without_opening_connection(self):
        with patch("sqlalchemy.engine_from_config") as engine_factory:
            command.upgrade(
                self.config,
                "c03_youtube_scan_controls:c04_article_images",
                sql=True,
            )

        engine_factory.assert_not_called()
        self.assertEqual(self.config.get_main_option("sqlalchemy.url"), ENCODED_URL)
        self.assertIn("CREATE TABLE article_images", self.output.getvalue())
        self.assertIn("CREATE TABLE article_imports", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
