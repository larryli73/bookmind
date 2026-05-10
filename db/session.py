"""Database session and engine setup"""
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


def get_database_url():
    """Get database URL - handles Railway's auto-generated URLs"""
    # Railway automatically sets DATABASE_URL from linked PostgreSQL
    url = os.getenv("DATABASE_URL", "")
    
    if not url:
        # Local development fallback
        url = "postgresql+asyncpg://bookmind:bookmind@localhost:5432/bookmind"
    
    # Fix URL scheme for asyncpg driver
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    print(f"Connecting to database: {url[:50]}...")
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
