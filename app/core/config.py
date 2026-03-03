import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY")
    # ... other settings

settings = Settings()