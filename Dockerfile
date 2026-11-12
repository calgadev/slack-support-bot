# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN groupadd --system --gid 1000 bot && useradd --system --uid 1000 --gid bot --create-home bot
WORKDIR /app
COPY --from=builder --chown=bot:bot /app /app
COPY --chown=bot:bot knowledge_base ./knowledge_base
RUN mkdir -p /app/data && chown bot:bot /app/data
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 DATA_DIR=/app/data
USER bot
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "-m", "support_bot.health"]
CMD ["python", "-m", "support_bot"]
