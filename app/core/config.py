# app/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    DATABASE_URL : str
    DB_NAME : str
    ALEMBIC_DATABASE_URL : str

    ALGORITHM : str
    ACCESS_TOKEN_EXPIRE_MINUTES : int

    SECRET_KEY : str
    CORS_ORIGINS : str


    EMAIL_HOST : str
    EMAIL_PORT : int
    EMAIL_USERNAME : str
    EMAIL_PASSWORD : str

    MONGODB_URI : str
    MONGO_DB_NAME : str
    PORT : int
    BREVO_API_KEY : str
    BREVO_URL : str
    GOOGLE_AI_STUDIO_API_KEY : str
    OPENAI_API_KEY: str | None = None
    OPENAI_DRAFT_MODEL: str = "gpt-5-mini"
    YOUTUBE_API_KEY : str
    YOUTUBE_BASE_URL: str
    PUBLIC_APP_KEYS: str = ""
    
    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL.replace(
            "postgresql://", "postgresql+asyncpg://"
        )

settings = Settings()
