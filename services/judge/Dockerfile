FROM python:3.12-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
COPY packages/scenarios/ ./packages/scenarios/
COPY packages/observability/ ./packages/observability/
COPY services/judge/ ./services/judge/

RUN cd services/judge && uv sync --frozen --no-dev

# Run the ARQ worker
CMD ["uv", "run", "--project", "services/judge", \
     "arq", "botcheck_judge.workers.judge_worker.WorkerSettings"]
