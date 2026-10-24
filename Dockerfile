# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.12.19-python3.14-alpine AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.14-alpine
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY alembic.ini ./
COPY alembic ./alembic

RUN adduser -D -u 10001 lequ \
    && mkdir -p /app/data \
    && chown lequ:lequ /app/data

USER lequ
VOLUME ["/app/data"]

# Single instance: migrations on start would race with replicas.
CMD ["sh", "-c", "alembic upgrade heads && bot"]
