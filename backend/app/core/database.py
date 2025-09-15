import contextlib
import logging
from typing import AsyncGenerator, Optional, Type, TypeVar, Any, Dict

from sqlalchemy import text, MetaData, event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
    AsyncConnection,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session, DeclarativeBase
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

# Create base class with metadata
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    metadata = MetaData(naming_convention=convention)
    
    def dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

# Create async engine with connection pooling
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    echo_pool=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
    pool_recycle=300,  # Recycle connections after 5 minutes
    pool_size=20,      # Number of connections to keep open
    max_overflow=10,   # Max number of connections to create beyond pool_size
    pool_timeout=30,   # Seconds to wait before giving up on getting a connection
    poolclass=NullPool if 'pytest' in os.environ else None,
    connect_args={
        "server_settings": {
            "application_name": "soulseer_backend",
            "timezone": "UTC",
        },
        "command_timeout": 60,  # seconds
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

# Dependency for FastAPI
get_db = async_session_factory

# Helper function to get database URL without asyncpg scheme
def get_database_url() -> str:
    """Get the database URL without the asyncpg scheme for migrations."""
    if settings.DATABASE_URL.startswith("postgresql+asyncpg://"):
        return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    return settings.DATABASE_URL

# Event listeners for connection handling
@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_connection, connection_record):
    """Set up connection-level settings."""
    if isinstance(dbapi_connection, asyncpg.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET timezone='UTC';")
        cursor.execute("SET application_name = %s;", ("soulseer_backend",))
        cursor.close()

# Context manager for database sessions
@contextlib.asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions."""
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
    """Check if the database is accessible."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False

# Function to initialize the database
async def init_db() -> None:
    """Initialize the database with tables."""
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

# Function to drop all tables
async def drop_all() -> None:
    """Drop all database tables (use with caution)."""
    if settings.ENVIRONMENT != "test":
        raise RuntimeError("Cannot drop tables in non-test environment")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("Dropped all database tables")

# Dependency to get DB session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function that yields database sessions.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

# Initialize database
async def init_db():
    ""
    Initialize database tables.
    """
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)

# For testing
TestingSessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    class_=AsyncSession
)

async def get_test_db():
    """
    Get a database session for testing.
    """
    async with TestingSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()
