# app/db/session.py

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Convert DATABASE_URL for async usage with asyncpg
DATABASE_URL = os.getenv("DATABASE_URL", "").replace(
    "postgresql://", "postgresql+asyncpg://"
)

# Create the async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"prepared_statement_cache_size": 0},  # <-- Disable statement caching
    poolclass=NullPool,  # <-- Disable pooling (let PgBouncer handle it)
)

# Create the session factory
SessionLocal = async_sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, class_=AsyncSession
)


# Base class for models
class Base(DeclarativeBase):
    pass


# Dependency for FastAPI routes
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
