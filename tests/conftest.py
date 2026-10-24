import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="lequ-tests-")
os.environ["DB_PATH"] = os.path.join(_TMP, "test.db")

import pytest_asyncio  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from lequ import queries  # noqa: E402
from lequ.db import engine  # noqa: E402


async def reset_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        for table in reversed(SQLModel.metadata.sorted_tables):
            await conn.execute(table.delete())
    queries._prefix_cache.clear()  # pyright: ignore[reportPrivateUsage]
    queries._emoji_cache.clear()  # pyright: ignore[reportPrivateUsage]


@pytest_asyncio.fixture(autouse=True)
async def clean_database() -> None:
    await reset_db()


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    del session, exitstatus
    shutil.rmtree(_TMP, ignore_errors=True)
