FROM python:3.12-slim AS base

# System deps for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
COPY packages/scenarios/ ./packages/scenarios/
COPY packages/observability/ ./packages/observability/
COPY packages/botcheck_http_client/ ./packages/botcheck_http_client/
COPY services/agent/ ./services/agent/

RUN cd services/agent && uv sync --frozen --no-dev

CMD ["uv", "run", "--project", "services/agent", \
     "python", "-m", "src.agent", "start"]
