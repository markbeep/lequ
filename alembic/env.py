from logging.config import fileConfig
from pathlib import Path

from sqlmodel import Session, create_engine

from alembic import context
from lequ.env import Settings  # pyright: ignore[reportMissingTypeStubs]
from lequ.models import BaseModel  # pyright: ignore[reportMissingTypeStubs]

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = BaseModel.metadata


def run_migrations() -> None:
    Path(Settings().db.path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{Settings().db.path}")
    with Session(engine) as session:
        context.configure(
            connection=session.connection(),
            target_metadata=target_metadata,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
