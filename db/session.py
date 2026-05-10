"""Database session and engine setup"""
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

def get_database_url():
    """Get database URL and fix Railway's postgres:// to postgresql+asyncpg://"""
    url = os.getenv("DATABASE_URL", "postgresql+asyncpg://bookmind:bookmind@localhost:5432/bookmind")
    # Railway provides postgres:// but we need postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL = get_database_url()

engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
