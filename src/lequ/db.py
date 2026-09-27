from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import text
from sqlmodel.ext.asyncio.session import AsyncSession

from .env import Settings

Path(Settings().db.path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    f"sqlite+aiosqlite:///{Settings().db.path}",
    connect_args={"timeout": 30},
)


@asynccontextmanager
async def get_session():
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text("pragma mmap_size=30000000000"))
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session
