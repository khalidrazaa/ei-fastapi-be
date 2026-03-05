# app/db/session.py

import os
from typing import AsyncGenerator
from dotenv import load_dotenv

from app.core.config import settings

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
  # Import your declarative base

# Load environment variables
load_dotenv()

# Convert DATABASE_URL for async usage with asyncpg
DATABASE_URL = settings.ASYNC_DATABASE_URL

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
