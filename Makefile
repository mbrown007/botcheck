.PHONY: help dev up down logs build test lint format migrate scenario test-phase5-merge-gate gen-schemas check-generated-artifacts check-lockfiles compare-ai-voice-latency test-ai-voice-latency plan-ai-voice-latency smoke-block-runtime-alignment

SHELL := /bin/bash

# Shared test helper path root used by script-loader tests.
# Can be overridden, e.g. `make test BOTCHECK_REPO_ROOT=/workspace/botcheck`.
BOTCHECK_REPO_ROOT ?= $(CURDIR)
export BOTCHECK_REPO_ROOT

# ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "BotCheck — development commands"
	@echo ""
	@echo "  make dev             Build and start all services (with logs)"
	@echo "  make up              Start all services in background"
	@echo "  make down            Stop all services"
	@echo "  make logs [s=<svc>]  Tail logs (all or specific service)"
	@echo "  make build           Rebuild all Docker images"
	@echo ""
	@echo "  make migrate         Run Alembic migrations"
	@echo "  make migrate-new n=<name>  Create a new migration"
	@echo ""
	@echo "  make test            Run all Python tests"
	@echo "  make test-fast-lane  Run PR fast-lane checks (lint + Python + web type/lint)"
	@echo "  make test-release-audio-gate  Run release audio gate script against API"
	@echo "  make test-release-readiness-gate  Run Phase 4 launch-readiness gate (migrations + smoke + alerts + optional audio)"
	@echo "  make test-phase5-merge-gate  Enforce archived Phase 4 evidence before main merges"
	@echo "  make test-phase4-alert-sim  Run temporary Prometheus alert simulation drill"
	@echo "  make test-phase4-backup-restore-drill  Run timed DB backup+restore drill"
	@echo "  make test-phase9-matrix  Run Phase 9 pack regression matrix gate"
	@echo "  make test-schedule-capacity-drill  Run 10/5 scheduled SIP capacity drill"
	@echo "  make test-pack-capacity-drill  Run pack fan-out SIP capacity drill"
	@echo "  make test-pack-trigger-latency  Probe /packs/{id}/run response-time budget"
	@echo "  make test-ai-voice-latency   Probe AI voice pipeline latency (requires BOTCHECK_AI_SCENARIO_ID, BOTCHECK_USER_TOKEN)"
	@echo "  make compare-ai-voice-latency BUNDLES=\"<dir1> <dir2> [dir3]\"  Compare Phase 40 lane bundles"
	@echo "  make plan-ai-voice-latency  Print a Phase 40 live benchmark execution plan"
	@echo "  make smoke-block-runtime-alignment BOTCHECK_USER_TOKEN=<token> BOTCHECK_WAIT_SCENARIO_ID=<id> BOTCHECK_TIME_ROUTE_SCENARIO_ID=<id>"
	@echo "  make test-dsl        Run scenario DSL tests only"
	@echo "  make lint            Ruff lint check"
	@echo "  make format          Ruff autoformat"
	@echo "  make gen-schemas     Regenerate checked-in JSON schemas"
	@echo "  make check-generated-artifacts  Verify OpenAPI, API types, and schemas are current"
	@echo "  make check-lockfiles Verify uv.lock freshness and web package-lock validity"
	@echo ""
	@echo "  make scenario-validate f=<path>   Validate a scenario YAML"
	@echo "  make scenario-run f=<path>        Run a scenario (requires services up)"
	@echo ""
	@echo "  make gate r=<run_id>  Check CI gate result for a run"
	@echo ""

# ── Docker ───────────────────────────────────────────────────────────────────

dev:
	docker compose build
	docker compose up

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f $(s)

build:
	docker compose build

# Like dev but skips observability (prometheus/alloy/node-exporter) to save ~400 MB
dev-lean:
	docker compose build
	docker compose up --scale prometheus=0 --scale alloy=0 --scale node-exporter=0

# ── Database ─────────────────────────────────────────────────────────────────

migrate:
	docker compose up -d postgres
	@echo "Waiting for postgres…"
	@until docker compose exec -T postgres pg_isready -U botcheck > /dev/null 2>&1; do sleep 1; done
	cd services/api && DATABASE_URL=postgresql+asyncpg://botcheck:$${POSTGRES_PASSWORD:-botcheck_dev}@localhost/botcheck uv run alembic upgrade head

migrate-new:
	@[ -n "$(n)" ] || (echo "Usage: make migrate-new n=<description>" && exit 1)
	cd services/api && uv run alembic revision --autogenerate -m "$(n)"

# ── Tests ────────────────────────────────────────────────────────────────────

test:
	uv run pytest packages/ services/ -v --tb=short

test-fast-lane:
	uv run ruff check packages/ services/
	uv run ruff format --check packages/ services/
	uv run pytest packages/scenarios/tests/ services/api/tests/ services/judge/tests/ -v --tb=short
	cd web && npm run lint && npm run typecheck

test-release-audio-gate:
	@[ -n "$${BOTCHECK_SCENARIO_ID:-}" ] || (echo "Set BOTCHECK_SCENARIO_ID=<scenario_id>" && exit 1)
	@[ -n "$${BOTCHECK_USER_TOKEN:-}" ] || (echo "Set BOTCHECK_USER_TOKEN=<token>" && exit 1)
	@bash scripts/ci/audio_release_gate.sh

test-release-readiness-gate:
	@bash scripts/ci/release_readiness_gate.sh

test-phase5-merge-gate:
	@bash scripts/ci/release_readiness_gate.sh --check-runtime 0 --require-phase4-evidence 1

test-phase4-alert-sim:
	@bash scripts/ci/phase4_alert_simulation.sh

test-phase4-backup-restore-drill:
	@bash scripts/ci/phase4_backup_restore_drill.sh

test-phase9-matrix:
	@bash scripts/ci/phase9_test_matrix.sh

test-schedule-capacity-drill:
	@[ -n "$${BOTCHECK_SCENARIO_ID:-}" ] || (echo "Set BOTCHECK_SCENARIO_ID=<scenario_id>" && exit 1)
	@[ -n "$${BOTCHECK_SCHEDULER_TOKEN:-}" ] || (echo "Set BOTCHECK_SCHEDULER_TOKEN=<scheduler_token>" && exit 1)
	@bash scripts/ci/schedule_capacity_drill.sh

test-pack-capacity-drill:
	@[ -n "$${BOTCHECK_PACK_ID:-}" ] || (echo "Set BOTCHECK_PACK_ID=<pack_id>" && exit 1)
	@[ -n "$${BOTCHECK_USER_TOKEN:-}" ] || (echo "Set BOTCHECK_USER_TOKEN=<user_token>" && exit 1)
	@bash scripts/ci/pack_capacity_drill.sh

test-pack-trigger-latency:
	@[ -n "$${BOTCHECK_PACK_ID:-}" ] || (echo "Set BOTCHECK_PACK_ID=<pack_id>" && exit 1)
	@[ -n "$${BOTCHECK_USER_TOKEN:-}" ] || (echo "Set BOTCHECK_USER_TOKEN=<user_token>" && exit 1)
	@bash scripts/ci/pack_trigger_latency_probe.sh

test-ai-voice-latency:
	@[ -n "$${BOTCHECK_AI_SCENARIO_ID:-}" ] || (echo "Set BOTCHECK_AI_SCENARIO_ID=<ai_scenario_id>" && exit 1)
	@[ -n "$${BOTCHECK_USER_TOKEN:-}" ] || (echo "Set BOTCHECK_USER_TOKEN=<user_token>" && exit 1)
	@bash scripts/ci/ai_voice_latency_probe.sh

compare-ai-voice-latency:
	@bash scripts/ci/ai_voice_latency_compare.sh $(patsubst %,--bundle %,$(BUNDLES))

plan-ai-voice-latency:
	@[ -n "$${BOTCHECK_AI_SCENARIO_ID:-}" ] || (echo "Set BOTCHECK_AI_SCENARIO_ID=<ai_scenario_id>" && exit 1)
	@bash scripts/ci/ai_voice_latency_benchmark_plan.sh

smoke-block-runtime-alignment:
	@[ -n "$${BOTCHECK_USER_TOKEN:-}" ] || (echo "Set BOTCHECK_USER_TOKEN=<token>" && exit 1)
	@[ -n "$${BOTCHECK_WAIT_SCENARIO_ID:-}" ] || (echo "Set BOTCHECK_WAIT_SCENARIO_ID=<scenario_id>" && exit 1)
	@[ -n "$${BOTCHECK_TIME_ROUTE_SCENARIO_ID:-}" ] || (echo "Set BOTCHECK_TIME_ROUTE_SCENARIO_ID=<scenario_id>" && exit 1)
	@bash scripts/smoke_block_runtime_alignment.sh

test-dsl:
	uv run pytest packages/scenarios/tests/ -v

test-api:
	uv run pytest services/api/tests/ -v

test-judge:
	uv run pytest services/judge/tests/ -v

# ── Lint / Format ─────────────────────────────────────────────────────────────

lint:
	uv run ruff check packages/ services/
	uv run ruff format --check packages/ services/
	cd web && npm run lint

format:
	uv run ruff format packages/ services/
	uv run ruff check --fix packages/ services/

gen-schemas:
	UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/uv-cache} uv run python scripts/generate_schemas.py

check-generated-artifacts:
	@bash scripts/ci/check_generated_artifacts.sh

check-lockfiles:
	UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/uv-cache} uv lock --check
	npm --prefix web ci --ignore-scripts --dry-run

typecheck:
	cd web && npm run typecheck

# ── Local dev (no Docker required) ───────────────────────────────────────────
# Requires: LiveKit dev server running (podman run livekit/livekit-server --dev)
# Terminal 1: make api        Terminal 2: make agent       Terminal 3: make -C poc bot

api:
	cd services/api && uv run uvicorn botcheck_api.main:app --host 0.0.0.0 --port 7700 --reload

agent:
	cd services/agent && uv run python -m src.agent dev

# Upload a scenario YAML to the running API
# Usage: make scenario-upload f=poc/scenario.yaml
scenario-upload:
	@[ -n "$(f)" ] || (echo "Usage: make scenario-upload f=<path>" && exit 1)
	@python3 -c "\
import json, urllib.request; \
body = json.dumps({'yaml_content': open('$(f)').read()}).encode(); \
req = urllib.request.Request('http://localhost:7700/scenarios/', data=body, headers={'Content-Type': 'application/json'}); \
print(json.dumps(json.loads(urllib.request.urlopen(req).read()), indent=2))"

# Submit a saved harness run JSON for judging
# Usage: make judge-ingest f=poc/runs/poc-xxx.json r=run_abc123
judge-ingest:
	@[ -n "$(f)" ] || (echo "Usage: make judge-ingest f=<run_json> r=<run_id>" && exit 1)
	@[ -n "$(r)" ] || (echo "Usage: make judge-ingest f=<run_json> r=<run_id>" && exit 1)
	@python3 -c "\
import json, urllib.request; \
d = json.load(open('$(f)')); \
body = json.dumps({'conversation': d['conversation']}).encode(); \
req = urllib.request.Request('http://localhost:7700/runs/$(r)/complete', data=body, headers={'Content-Type': 'application/json'}); \
print(json.dumps(json.loads(urllib.request.urlopen(req).read()), indent=2))"

# ── Scenarios ────────────────────────────────────────────────────────────────

scenario-validate:
	@[ -n "$(f)" ] || (echo "Usage: make scenario-validate f=<path>" && exit 1)
	uv run python -c "from botcheck_scenarios import load_scenario; s = load_scenario('$(f)'); print('✓', s.name)"

scenario-run:
	@[ -n "$(f)" ] || (echo "Usage: make scenario-run f=<path.yaml>" && exit 1)
	@python3 -c "\
import json, urllib.request, yaml; \
sid = yaml.safe_load(open('$(f)'))['id']; \
body = json.dumps({'scenario_id': sid}).encode(); \
req = urllib.request.Request('http://localhost:7700/runs/', data=body, headers={'Content-Type': 'application/json'}); \
print(json.dumps(json.loads(urllib.request.urlopen(req).read()), indent=2))"

# ── CI gate ──────────────────────────────────────────────────────────────────

gate:
	@[ -n "$(r)" ] || (echo "Usage: make gate r=<run_id>" && exit 1)
	@curl -s http://localhost:7700/runs/$(r)/gate | jq .gate_result
