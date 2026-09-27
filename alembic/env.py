from logging.config import fileConfig
from pathlib import Path

from sqlmodel import create_engine

from alembic import context
from lequ.env import Settings
from lequ.models import BaseModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = BaseModel.metadata


def run_migrations() -> None:
    Path(Settings().db.path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{Settings().db.path}")
    # A plain connection, not a Session: closing a Session rolls the version stamp back,
    # which leaves the database migrated but unstamped so the next upgrade re-runs the DDL.
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
