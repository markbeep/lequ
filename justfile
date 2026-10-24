# https://just.systems

bot:
    uv run bot

format:
    uv run ruff format .

check:
    uv run ruff format --check .
    uv run basedpyright src

revision message:
    uv run alembic revision --autogenerate -m "{{ message }}"

upgrade:
    uv run alembic upgrade heads

downgrade:
    uv run alembic downgrade base

upgrade-deps:
    uv lock --upgrade
    uv sync
