import contextlib
import logging
from typing import AsyncGenerator, Any, Dict

from sqlalchemy import text, MetaData, event, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import asyncpg
import os

from .config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Naming convention for database constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Base class for SQLAlchemy models
Base = declarative_base(metadata=MetaData(naming_convention=convention))
    
# Create async engine with connection pooling
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    echo_pool=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    poolclass=NullPool if 'pytest' in os.environ else None,
    connect_args={
        "server_settings": {
            "application_name": "soulseer_backend",
            "timezone": "UTC",
        },
        "command_timeout": 60,
    },
)

# Create async session factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
    twophase=False,
    join_transaction_mode="create_savepoint",
)

# Helper function to get database URL without asyncpg scheme
def get_database_url() -> str:
    if settings.DATABASE_URL.startswith("postgresql+asyncpg://"):
        return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    return settings.DATABASE_URL

# Event listeners for connection handling
@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, asyncpg.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET timezone='UTC';")
        cursor.execute("SET application_name = %s;", ("soulseer_backend",))
        cursor.close()

# Context manager for database sessions
@contextlib.asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    session: AsyncSession = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        await session.close()

# Function to check database connectivity
async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False

# Function to initialize the database
async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

# Function to drop all tables
async def drop_all() -> None:
    if settings.ENVIRONMENT != "test":
        raise RuntimeError("Cannot drop tables in non-test environment")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("Dropped all database tables")

# Dependency to get DB session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

# Configure testing session
TestingSessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    class_=AsyncSession
)

async def get_test_db():
    async with TestingSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

