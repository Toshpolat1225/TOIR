from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Set to True to see SQL queries in logs
)

SessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


async def get_db():
    """Dependency to get a database session."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()