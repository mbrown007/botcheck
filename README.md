# BotCheck
[![Test Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)](https://github.com/brownster/botcheck/actions/workflows/ci.yml)


**testing platform for LLM-powered voicebots.**

BotCheck is a weekend project to imagine how the next pulse solution would work with scheduled outbound SIP calls to AI Bot LLM as judge scoring rubric etc
Ended up settling on Yaml format for the outboune scneario calls also added scenario builder using react flow
Putting here in case it suseful to someone else
I had issue with webrtc to sip bridge when runnig as container, i had to remove the binary and run locally to get sipgate trunk to connect
run make dev or make build, make up

<img width="1900" height="874" alt="image" src="https://github.com/user-attachments/assets/92197506-c562-4f44-929f-bc0b873c1843" />




<img width="1900" height="874" alt="image" src="https://github.com/user-attachments/assets/920e636f-cf8c-4cf3-8916-c1d753b40810" />




<img width="1900" height="874" alt="image" src="https://github.com/user-attachments/assets/39856b26-6411-4dad-a34d-5796fb2e820a" />

---

## 🚀 Key Features

- **Real Telephony Testing:** Dial out to real PSTN/SIP endpoints to test agents in their native environment.
- **Dynamic Scenarios:** Support for branching logic, persona-driven behaviors, and adversarial probes.
- **Automated LLM Judging:** Intelligent scoring of conversation turns against custom rubrics using Claude 3.5 Sonnet.
- **Visual Flow Builder:** Drag-and-drop scenario creation with side-by-side YAML synchronization.
- **TTS Caching:** Reduce costs and latency with automated S3-backed audio caching.
- **Multi-Tenant Architecture:** Secure isolation for different projects or clients.
- **Compliance & Security:** PII redaction, immutable audit logging, and local auth with TOTP 2FA.
- **Observability:** Comprehensive Prometheus metrics and Grafana dashboards for performance and cost tracking.

---

## 🏁 Get Started

### 1. Prerequisites

- Docker and Docker Compose
- API Keys for: OpenAI, Deepgram, Anthropic
- (Optional) A SIP trunk provider (e.g., Sipgate) for real telephony tests

### 2. Local Setup

```bash
# Clone the repository
git clone https://github.com/brownster/botcheck.git
cd botcheck

# Configure environment
cp .env.example .env
# Edit .env and add your API keys

# Start the full stack
make dev
```

The platform will be available at:
- **Dashboard:** http://localhost:3000
- **API Docs:** http://localhost:7700/docs
- **Metrics:** http://localhost:9090 (Prometheus)

### 3. Your First Run

1. **Login:** Use the default credentials:
   - Email: `admin@botcheck.local`
   - Password: `botcheck-dev-password`
2. **Create Scenario:** Navigate to "Scenarios" and click "Upload Scenario". Use one of the provided templates.
3. **Run Test:** Click "Run" on your new scenario.
4. **View Results:** Observe the live transcript and wait for the "Judge" to provide a final verdict and dimension scores.

---

## 📖 Documentation

### For Users
- [How to: Add, Run, and Schedule Scenarios](docs/how-to-scenarios.md)
- [User Guide: Visual Flow Builder](docs/how-to-builder.md)
- [Running SIP Scenarios](docs/running-sip-scenarios.md)
- [Scenario DSL Reference](docs/scenario-dsl.md)

### For Developers
- [System Architecture (C4 Model)](docs/system-design-c4.md)
- [Developer Guide: Patterns & Standards](docs/developer-guide.md)
- [Developer Guide: Extending the Scenario Builder](docs/developer-guide-builder.md)
- [Release Notes](docs/release-notes.md)
- [Security & Compliance](docs/security-compliance-requirements.md)
- [Deployment Strategy](docs/deployment-strategy.md)

### Operations
- [Monitoring & Metrics](docs/monitoring.md)
- [On-Call Runbook](docs/runbooks/on-call.md)
- [Backup & Restore Guide](docs/runbooks/backup-restore-drill.md)

---

## 🛠 Development

### Makefile Commands

```bash
make test          # Run all Python tests
make test-dsl      # Test the scenario DSL parser
make api           # Run API service locally (outside Docker)
make agent         # Run Harness Agent locally
make judge         # Run Judge Worker locally
```

Test path note:
- `make` now exports `BOTCHECK_REPO_ROOT` automatically.
- If you run `pytest` directly, set it manually so script-loader tests can find `scripts/ci/*`:
  - `BOTCHECK_REPO_ROOT=$(pwd) uv run pytest ...`
- In containerized runs with a full repo mount at `/app`, use:
  - `BOTCHECK_REPO_ROOT=/app uv run pytest ...`

### Repo Structure

- `packages/scenarios`: Shared DSL models used by all services.
- `services/api`: Control plane providing management APIs.
- `services/agent`: The LiveKit-based synthetic caller.
- `services/judge`: Automated scoring and report generation.
- `web`: Next.js frontend dashboard.
- `infra`: Infrastructure as code, monitoring config, and dashboards.

---
