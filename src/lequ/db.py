from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import text

from .env import Settings

engine = create_async_engine(f"sqlite+pysqlite:///{Settings().db.path}")


@asynccontextmanager
async def get_session():
    async with AsyncSession(engine) as session:
        await session.execute(text("pragma mmap_size=30000000000"))
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session
