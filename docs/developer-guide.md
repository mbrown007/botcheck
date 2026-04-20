# Developer Guide: Engineering Patterns & Standards

This guide documents the architectural patterns, coding standards, and best practices used across the BotCheck platform. Following these ensures the system remains maintainable, scalable, and reliable.

---

## 1. Backend Patterns (Python / FastAPI)

### 1.1 Service Layer Pattern
We separate concerns using a three-layer architecture:
*   **Routers (`routers/`):** Handle HTTP concerns (auth, parameter validation, status codes). They should be thin and delegate all business logic to services.
*   **Services (`services/`):** The "brain" of the app. Orchestrate complex operations, call repositories, and trigger background jobs.
*   **Repositories (`store_repo.py`):** Pure database I/O using SQLAlchemy. No business logic here.

### 1.2 Test Data Factories
Never manually construct large JSON/Dict objects in tests. Use factories to ensure tests stay dry and resilient to schema changes.
```python
# Use the factory pattern found in services/api/tests/factories.py
scenario = create_scenario_factory(id="test-bot", turns=[...])
```

### 1.3 Structured Logging (`structlog`)
Do not use f-strings in logs. Use structured logging to ensure logs are searchable in Grafana/Loki.
```python
# GOOD:
logger.info("run_started", run_id=run_id, tenant_id=tenant_id, transport="sip")

# BAD:
logger.info(f"Run {run_id} started for tenant {tenant_id}")
```

### 1.4 State Reconciliation (The Reaper)
Background processes must be idempotent. The **Reaper Service** periodically reconciles database states with external reality (e.g., checking if a LiveKit room actually exists for a "RUNNING" record) to prevent "zombie" runs.

---

## 2. Frontend Patterns (Next.js / TypeScript)

### 2.1 Type-Safe API (`openapi-typescript`)
TypeScript interfaces are **never** written manually for API responses. They are generated from the FastAPI backend.
*   **Command:** `npm --prefix web run gen:api-types` (or run `npm run gen:api-types` inside the `web/` directory)
*   **Location:** `web/src/lib/api/generated.ts`
Always use these generated types to prevent type-drift.

### 2.2 Generated Artifacts
BotCheck keeps several generated artifacts checked into git. If you change a canonical model or an API contract, regenerate the matching artifacts before you commit.

*   **JSON schemas** (`schemas/*.json`)
    *   **Command:** `UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/generate_schemas.py`
    *   **Source of truth:** canonical Pydantic models in `packages/scenarios/` and selected API request models
*   **OpenAPI schema** (`web/src/lib/api/openapi.json`)
    *   **Command:** `npm --prefix web run gen:openapi-schema`
    *   **Source of truth:** FastAPI app in `services/api`
*   **Generated API types** (`web/src/lib/api/generated.ts`)
    *   **Command:** `npm --prefix web run gen:api-types`
    *   **Source of truth:** `web/src/lib/api/openapi.json`

For a single local drift check across all generated artifacts, run:

```bash
make check-generated-artifacts
```

### 2.3 Lockfiles And Test Order
Lockfile freshness and test-order independence are explicit repository standards.

*   **Python lockfile:** `UV_CACHE_DIR=/tmp/uv-cache uv lock --check`
*   **Web lockfile:** `npm --prefix web ci --ignore-scripts --dry-run`
*   **Combined local check:** `make check-lockfiles`

Python tests run with `pytest-randomly` in the root dev environment. A failing randomized order should be treated as a real state-leak bug, not worked around. Pytest prints the seed in the session header so failures can be reproduced with:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest --randomly-seed=<N>
```

### 2.4 Store Slice Pattern (Zustand)
As stores grow, they must be split into logical slices to prevent "God Stores."
*   `canvasSlice`: Node/Edge management.
*   `historySlice`: Undo/Redo logic.
*   `ioSlice`: Serialization/Sync.

### 2.5 Web Dependency Graph
The web workspace treats circular imports as a CI failure.

*   **Command:** `npm --prefix web run check:cycles`
*   **Tool:** `madge`
*   **Scope:** `web/src`

Run the cycle check after adding shared helpers, layout components, or new store utilities. These are the areas most likely to create accidental cross-import loops.

### 2.6 Schema-Driven Forms (`react-hook-form` + `zod`)
All complex forms (Scenario Metadata, Turn Editor) must use `react-hook-form` with a `zod` resolver.
*   Define the schema in `web/src/lib/schemas/`.
*   This provides automatic validation, error reporting, and type-coercion (e.g., string to number).

---

## 3. Reliability Patterns

### 3.1 Fail-Closed Logic
If a critical component (ASR, TTS, Judge) fails or returns an ambiguous result, the system must **Fail-Closed**. 
*   A failed judge job results in a `gate_result: blocked` status.
*   Better to block a release than to let a faulty bot through due to a monitoring error.

### 3.2 Distributed Tracing
Every request must carry a `traceparent` (W3C TraceContext).
*   **Propagation:** API -> LiveKit Metadata -> Harness Agent.
*   Allows a single "Run Now" click to be traced across all services in Grafana Tempo.

---

## 4. Testing Standards

*   **Unit Tests:** Every service function and utility must have a unit test.
*   **Integration Tests:** Every API endpoint must have a test covering both success and failure cases (auth, 404, 429).
*   **E2E Tests:** Critical user flows (Create Scenario -> Run -> View Result) are covered by Playwright.
*   **Visual Regression (Planned):** In the future, changes to builder nodes will be verified against "Golden Images" to prevent layout shifts.
