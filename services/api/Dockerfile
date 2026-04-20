FROM python:3.12-slim AS base

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace manifests first (better layer caching)
COPY pyproject.toml uv.lock ./
COPY packages/botcheck_http_client/ ./packages/botcheck_http_client/
COPY packages/scenarios/ ./packages/scenarios/
COPY packages/observability/ ./packages/observability/
COPY services/api/ ./services/api/

# Install dependencies (locked)
RUN cd services/api && uv sync --frozen --no-dev

# Make entrypoint executable
RUN chmod +x /app/services/api/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/services/api/entrypoint.sh"]
CMD ["uv", "run", "--project", "services/api", \
     "uvicorn", "botcheck_api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload"]
