"""Validate dotenv compatibility without depending on local configuration values."""

import os
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir
from unittest.mock import patch

from pydantic import ValidationError

_REQUIRED_VALUES = {
    "DATABASE_URL": "postgresql://test:test@localhost/test",
    "DB_NAME": "test",
    "ALEMBIC_DATABASE_URL": "postgresql://test:test@localhost/test",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
    "SECRET_KEY": "isolated-config-test-key",
    "CORS_ORIGINS": "http://localhost:3000",
    "EMAIL_HOST": "mail.example.com",
    "EMAIL_PORT": "587",
    "EMAIL_USERNAME": "test@example.com",
    "EMAIL_PASSWORD": "isolated-email-test-value",
    "MONGODB_URI": "mongodb://localhost:27017",
    "MONGO_DB_NAME": "test",
    "PORT": "8000",
    "BREVO_API_KEY": "isolated-brevo-test-value",
    "BREVO_URL": "https://example.com/email",
    "GOOGLE_AI_STUDIO_API_KEY": "isolated-google-test-value",
    "YOUTUBE_API_KEY": "isolated-youtube-test-value",
    "YOUTUBE_BASE_URL": "https://example.com/youtube",
}

# config.py constructs its singleton at import, so seed discovery as well as tests.
with patch.dict(os.environ, _REQUIRED_VALUES):
    from app.core.config import Settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = gettempdir()
        self.enterContext(patch.dict(os.environ))
        # Isolate declared values while preserving OS and sandbox environment keys.
        for key in tuple(os.environ):
            if key.upper() in Settings.model_fields:
                del os.environ[key]
        self.values = _REQUIRED_VALUES.copy()

    def load_settings(self):
        with NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".env", dir=self.temp_dir, delete=False
        ) as file:
            file.write("\n".join(f"{key}={value}" for key, value in self.values.items()))
            path = Path(file.name)
        self.addCleanup(path.unlink)
        return Settings(_env_file=path)

    def test_unrelated_dotenv_key_does_not_prevent_startup(self):
        self.values["CHAT_GPT"] = "legacy-shared-setting"
        settings = self.load_settings()
        self.assertEqual(settings.PORT, 8000)
        self.assertEqual(settings.DB_NAME, "test")
        self.assertNotIn("CHAT_GPT", settings.model_dump())

    def test_required_settings_are_still_required(self):
        del self.values["DATABASE_URL"]
        with self.assertRaises(ValidationError) as raised:
            self.load_settings()
        self.assertIn(
            ("DATABASE_URL",),
            [error["loc"] for error in raised.exception.errors()],
        )

    def test_declared_setting_types_are_still_validated(self):
        self.values["PORT"] = "invalid-port"
        with self.assertRaises(ValidationError) as raised:
            self.load_settings()
        self.assertIn(
            ("PORT",),
            [error["loc"] for error in raised.exception.errors()],
        )


if __name__ == "__main__":
    unittest.main()
