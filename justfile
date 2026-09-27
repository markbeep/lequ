# https://just.systems

bot:
    uv run bot

revision message:
    uv run alembic revision --autogenerate -m "{{ message }}"

upgrade:
    uv run alembic upgrade heads

downgrade:
    uv run alembic downgrade base
