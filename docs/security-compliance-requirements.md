# Security & Compliance Requirements
## BotCheck — LLM Voicebot Testing Platform

**Version:** 0.1 (draft)
**Date:** 2026-02-23
**Status:** Draft for review

---

## 1. Purpose & Scope

This document defines the security and compliance requirements for **BotCheck**, an enterprise-grade platform for testing LLM-powered voicebots. It covers:

- Threat model (STRIDE)
- Data classification and retention
- Tenant isolation strategy
- Authentication and authorization model
- Encryption strategy
- Audit logging requirements
- Incident response hooks
- Compliance posture

**In scope:** The BotCheck platform (control plane, media plane, storage, observability) and its integration with LiveKit as the telephony/media substrate.

**Out of scope:** Security posture of the voicebots under test (BotCheck tests them; it does not secure them).

---

## 2. Threat Model (STRIDE)

The following assets are in scope for the threat model:

| Asset | Description |
|---|---|
| Test audio streams | Real-time media flowing through LiveKit rooms |
| Transcripts | STT output of test conversations |
| Test recordings | Stored audio artifacts |
| Scenario definitions | Test scripts, adversarial prompts, expected outcomes |
| Judge results | Scoring data, policy adherence verdicts |
| Tenant credentials | API keys, SIP trunk credentials |
| LiveKit JWT tokens | Short-lived access grants |
| Audit logs | Immutable record of all test activity |

### 2.1 Spoofing

| Threat | Mitigation |
|---|---|
| Caller impersonates a legitimate test harness | Short-lived, room-scoped LiveKit JWT tokens issued server-side; no client-side token generation |
| Adversary replays a captured SIP invite | SIP TLS + nonce-based digest auth on SIP trunk; TLS for signaling |
| API caller impersonates another tenant | SSO + service account tokens scoped to tenant; JWT claims validated server-side |
| Synthetic caller agent impersonates a human | Out of scope (by design — this is the product's intended capability) |

### 2.2 Tampering

| Threat | Mitigation |
|---|---|
| Man-in-the-middle modifies audio in transit | SRTP for media; SIP TLS for signaling; WebRTC DTLS-SRTP inside LiveKit rooms |
| Transcript or judge result modified post-generation | Artifacts stored with HMAC or object-level checksums; write-once storage policies |
| Scenario definition tampered before execution | Scenario versions stored with content hash; hash recorded in audit log at test start |
| Kubernetes workload compromised to alter data | Pod security standards; network policies; image signing (cosign); RBAC on k8s API |

### 2.3 Repudiation

| Threat | Mitigation |
|---|---|
| Engineer denies triggering a sensitive test run | Immutable, append-only audit log recording actor, action, scenario version, bot endpoint, timestamp |
| Dispute over which artifact corresponds to a run | Artifact IDs linked cryptographically to audit log entries |
| Denial of configuration change | All control plane mutations logged with actor identity |

### 2.4 Information Disclosure

| Threat | Mitigation |
|---|---|
| Audio/transcripts leaked between tenants | Hard tenancy (separate storage buckets, keys) or soft tenancy with IAM boundary per tenant |
| Adversarial prompt library exposed to competitor tenants | Scenario store with tenant-scoped access; no cross-tenant reads |
| SIP trunk credentials leaked | Stored in Vault/KMS; never logged; rotated regularly; only injected at runtime via env/secrets |
| LLM judge model credentials leaked | Same Vault pattern; model API keys scoped per tenant where possible |
| LiveKit API key/secret leaked | Server-side only; rotated quarterly minimum; never in client bundles |
| PII in transcripts exposed to unauthorized parties | PII detection + redaction pipeline; RBAC on transcript access; data retention limits |
| Kubernetes secrets exposed | External secrets operator (ESO) or Vault agent; no secrets in ConfigMaps or image layers |

### 2.5 Denial of Service

| Threat | Mitigation |
|---|---|
| Flood of test runs exhausts LiveKit SFU resources | Per-tenant concurrency quotas; rate limiting on Orchestrator API |
| SIP trunk flooded with inbound calls | SIP trunk IP allow-listing; carrier-level rate limits; LiveKit dispatch rules as first filter |
| Storage exhausted by runaway recordings | Per-tenant storage quotas; recording lifecycle policies (TTL); circuit breakers in Artifact Store |
| Judge service overwhelmed by long transcripts | Async job queue with backpressure; per-tenant queue depth limits |

### 2.6 Elevation of Privilege

| Threat | Mitigation |
|---|---|
| Viewer role escalates to trigger destructive test | RBAC enforced server-side; roles: Admin / QA Engineer / Viewer / Auditor |
| Test harness agent escapes its LiveKit room grant | Room-scoped JWT tokens; grants checked server-side by LiveKit |
| Container escape from test workload | gVisor or similar sandbox for scenario execution pods; no host-network, no privileged |
| CI/CD pipeline compromise injects malicious image | Signed images (cosign + policy controller); SLSA build provenance; admission webhook |

---

## 3. Data Classification & Retention

### 3.1 Data Classes

| Class | Examples | Sensitivity |
|---|---|---|
| **C1 — Public** | Product documentation, open scenario templates | None |
| **C2 — Internal** | Aggregate test metrics, non-PII run statistics | Low |
| **C3 — Confidential** | Scenario definitions, judge rubrics, routing logic | Medium |
| **C4 — Restricted** | Audio recordings, transcripts, SIP credentials, PII in transcripts, API keys | High |
| **C5 — Regulated** | PCI/PII in transcripts (if health/finance bots tested) | Very high — may trigger HIPAA/PCI-DSS |

### 3.2 Retention Profiles

Tenants must be able to select a retention profile at project level:

| Profile | Audio | Transcripts | Judge Results | Metrics |
|---|---|---|---|---|
| **Ephemeral** | Deleted on run completion | Deleted on run completion | 30 days | 90 days |
| **Standard** | 30 days | 30 days | 1 year | 2 years |
| **Compliance** | 90 days | 90 days | 3 years | 3 years |
| **No-Audio** | Never stored | 30 days | 1 year | 2 years |

All retention deletions are logged in the audit log.

### 3.3 PII / PCI Handling

- **Detection:** Run NLP-based PII detector on all transcripts before storage (names, card numbers, SSNs, account numbers, health info).
- **Redaction:** Replace detected PII with typed placeholders (`[PERSON_NAME]`, `[CREDIT_CARD]`) in stored transcripts.
- **Audio redaction:** Optional; beep/silence segments flagged by transcript-audio alignment. Computationally expensive — offer as opt-in per tenant.
- **No-storage mode:** Tenant may elect to receive only scoring JSON and no raw transcript/audio.

---

## 4. Tenant Isolation Strategy

### 4.1 Isolation Tiers

| Tier | Description | Target customer |
|---|---|---|
| **Hard** | Separate LiveKit project, separate k8s namespace, separate storage buckets, separate encryption keys | Regulated enterprises (finance, health) |
| **Soft** | Shared cluster; strict room naming + token grants; separate buckets/prefixes per tenant; separate KMS keys | Standard enterprise SaaS |
| **Shared-Dev** | Shared infrastructure; logical separation only | Developer/trial tier — not for production data |

Regulated customers (HIPAA, PCI-DSS) must use **Hard** tier.

### 4.2 LiveKit-Level Isolation

- **Hard tier:** Each tenant gets its own LiveKit project with its own API key/secret; rooms cannot cross project boundaries.
- **Soft tier:** Single LiveKit project; rooms named with tenant prefix enforced by token grant (`roomJoin` grant restricted to `tenant-{id}-*`); server-side validation.
- Token generation is **always server-side** — clients never receive LiveKit API secrets.

### 4.3 Storage Isolation

- Each tenant has a dedicated object storage bucket or prefix with IAM policy denying cross-tenant access.
- KMS key per tenant for envelope encryption of stored artifacts.
- Database rows tagged with `tenant_id`; row-level security policies enforced at DB layer.

---

## 5. Authentication & Authorization Model

### 5.1 Human Users (UI/API)

| Mechanism | Detail |
|---|---|
| **Identity provider** | OIDC/SAML — BotCheck acts as SP; customer brings their IdP (Okta, Azure AD, Google Workspace) |
| **MFA** | Enforced via IdP; BotCheck does not manage MFA directly |
| **Session tokens** | Short-lived JWTs (1h access, 8h refresh); refresh tokens rotated on use |
| **API keys** | Long-lived service account keys for CI/CD; scoped to tenant + permission set; stored hashed |

### 5.2 RBAC Roles

| Role | Capabilities |
|---|---|
| **Admin** | Manage tenant settings, users, SIP trunks, secrets, retention policy; trigger runs |
| **QA Engineer** | Create/edit/run scenarios; view results and artifacts |
| **Viewer** | View results, metrics, scores; no scenario edit or trigger |
| **Auditor** | Read-only access to audit logs and compliance reports; no operational access |

Role assignments are stored server-side; JWT claims are assertions that are always re-validated against authoritative RBAC store.

### 5.3 Machine-to-Machine (Service Accounts)

- CI/CD pipelines authenticate via API key bound to a service account.
- Service accounts have role `QA Engineer` maximum (cannot modify tenant security settings).
- API keys rotated at least annually; rotation is non-breaking (overlap window).

### 5.4 LiveKit Token Issuance

- All LiveKit JWT tokens issued by BotCheck backend, never by clients.
- Token claims:
  - `roomJoin`: yes
  - `room`: `tenant-{id}-run-{run_id}` (ephemeral; unique per run)
  - `canPublish`: only for test harness agent participant
  - `canSubscribe`: yes for observer/recorder participant
  - `exp`: max 1h (test run duration cap)
- Token endpoint protected by BotCheck RBAC (`QA Engineer` minimum to trigger run).

---

## 6. Encryption Strategy

### 6.1 In Transit

| Path | Protocol |
|---|---|
| Browser/CLI → BotCheck API | HTTPS/TLS 1.3 |
| BotCheck services (internal) | mTLS (service mesh, e.g. Istio/Cilium) |
| SIP signaling (SIP trunk → LiveKit SIP bridge) | SIP TLS (port 5061) |
| Media (SIP trunk → LiveKit SIP bridge → room) | SRTP |
| WebRTC inside LiveKit room | DTLS-SRTP (enforced by LiveKit) |
| BotCheck → cloud storage | HTTPS |
| BotCheck → database | TLS |

### 6.2 At Rest

| Asset | Encryption |
|---|---|
| Audio recordings | AES-256-GCM; envelope key in KMS per tenant |
| Transcripts | AES-256-GCM; envelope key in KMS per tenant |
| Scenario definitions | AES-256-GCM; envelope key in KMS |
| Database (sensitive columns) | Application-level encryption for C4/C5 fields; DB volume encryption as baseline |
| Kubernetes secrets | etcd encryption at rest; External Secrets Operator pulls from Vault |

### 6.3 Optional E2EE (LiveKit)

LiveKit supports WebRTC E2EE (via Insertable Streams API). This means the SFU cannot decrypt media.

**Trade-offs:**

| With E2EE | Without E2EE |
|---|---|
| Server cannot record/inspect media | Server-side recording possible |
| Maximum confidentiality of call content | Needed for artifact storage and real-time analysis |
| Breaks server-side ASR | |

**Decision:** E2EE is offered as a tenant-level opt-in for use cases where the call content is highly sensitive and the tenant accepts no server-side recording. For most test use cases, E2EE is disabled to enable artifact capture and judge pipeline.

### 6.4 Key Management

- **KMS:** Cloud KMS (AWS KMS, GCP Cloud KMS, Azure Key Vault) or on-prem Vault with PKCS#11 backend.
- **Envelope encryption:** Data keys generated per artifact, encrypted under tenant's KMS key.
- **Key rotation:** Annual minimum; rotation is transparent (old keys retained for decryption of existing data).
- **Access:** Only the Artifact Store service has IAM permission to use KMS keys. No human direct access.

---

## 7. Audit Logging Requirements

### 7.1 What Must Be Logged

Every entry must include: `timestamp` (UTC, ISO 8601), `actor` (user ID or service account), `tenant_id`, `action`, `resource_type`, `resource_id`, `outcome` (success/failure), `ip_address`, `trace_id`.

| Category | Actions |
|---|---|
| **Authentication** | Login, logout, MFA events, API key used, token refresh |
| **Authorization** | Permission denied events |
| **Scenario management** | Create, update, delete, publish scenario; scenario version hash |
| **Test execution** | Run triggered (actor, scenario ID+version, bot endpoint, run ID); run completed; run cancelled |
| **Artifact access** | Recording downloaded, transcript downloaded, result exported |
| **Configuration changes** | SIP trunk added/modified/deleted, secret rotated, retention policy changed, role assigned/revoked |
| **Admin actions** | Tenant created/suspended, user invited/removed, data deletion requested |
| **Security events** | Failed login, repeated RBAC denials, anomalous API access patterns |

### 7.2 Log Properties

- **Append-only:** Audit log is write-once; no update or delete operations permitted by any role including Admin.
- **Integrity:** Logs signed or chained (hash chain) so tampering is detectable.
- **Retention:** Minimum 2 years hot + 5 years cold for compliance tier; 1 year for standard tier.
- **Searchable:** Full-text search on actor, resource, action; time-range filtering.
- **Export:** Tenant Auditor role can export logs in standard formats (JSON, CEF) for SIEM integration.

### 7.3 SIEM Integration

- Audit log stream available via webhook or Kafka topic per tenant.
- Supported formats: CEF, JSON (ECS-compatible), syslog.
- SIEM-friendly: every event has consistent field names for correlation rules.

### 7.4 Audit Log Write Rules (Transactional Integrity)

- `write_audit_event` MUST run in the same DB transaction/session as the state mutation it records.
- Handlers MUST call `write_audit_event` before `db.commit()` finalizes that mutation.
- Audit writes MUST NOT be deferred through `BackgroundTasks`, queue workers, or any out-of-transaction callback path.
- CI enforces this convention with an AST guard (`scripts/ci/check_audit_write_conventions.py`) that fails the release gate on violations.

---

## 8. Incident Response Hooks

### 8.1 Detection Signals

The platform emits signals that should feed into an incident response workflow:

| Signal | Description | Severity |
|---|---|---|
| `auth.failed_login_burst` | >5 failed logins in 5 minutes for a user | Medium |
| `authz.denied_burst` | >10 permission denied events in 1 minute from one actor | High |
| `secret.access_anomaly` | Secret accessed outside normal service account pattern | High |
| `data.cross_tenant_attempt` | Any query with cross-tenant resource ID | Critical |
| `run.jailbreak_detected` | Judge scores jailbreak attempt as successful (informational — voicebot under test) | Low |
| `infra.image_policy_denied` | Unsigned or unverified image rejected by admission webhook | High |
| `storage.quota_exceeded` | Tenant storage quota breached | Medium |
| `sip.trunk_auth_failure` | SIP digest auth failures on trunk | High |

### 8.2 Alerting Pipeline

```
Platform signals
    → structured log (JSON)
    → log aggregator (Loki / CloudWatch / Datadog)
    → alert rules (Grafana Alerting / PagerDuty)
    → on-call runbook
```

### 8.3 Breach Response Procedure (outline)

1. **Detect** — automated alert or manual report.
2. **Contain** — suspend affected tenant/service account; isolate affected pods via NetworkPolicy.
3. **Assess** — pull audit log for affected actor/tenant; determine blast radius.
4. **Notify** — if C4/C5 data involved, notify affected tenant within 72h (GDPR Art. 33 requirement).
5. **Remediate** — rotate secrets, patch vulnerability, redeploy signed images.
6. **Post-mortem** — document timeline, root cause, and control improvements.

All breach response actions are themselves logged in the audit log.

---

## 9. Compliance Posture

### 9.1 Applicable Frameworks

| Framework | Relevance | Approach |
|---|---|---|
| **SOC 2 Type II** | Required by most enterprise buyers | Design controls aligned to TSC; annual audit |
| **GDPR** | If EU customer data (voice) is processed | Data residency options; DPA available; 72h breach notification |
| **HIPAA** | If health-sector bots are tested and PHI transits | Hard tenant isolation; BAA with LiveKit Cloud or self-host; PHI minimization |
| **PCI-DSS** | If payment bots tested and card data transits | Scoping (minimize PCI scope); redaction pipeline; no card data at rest |
| **ISO 27001** | Enterprise procurement requirement | ISMS aligned; can support customer audits |

### 9.2 LiveKit Cloud Compliance

If using LiveKit Cloud (vs self-hosted):

- LiveKit publishes SOC 2 Type II, GDPR, and HIPAA/BAA at [trust.livekit.io](https://trust.livekit.io).
- BotCheck's overall compliance posture must account for LiveKit Cloud as a sub-processor.
- For strict data residency, prefer self-hosted LiveKit on customer's own infrastructure.

### 9.3 Self-Hosting for Compliance

LiveKit server can be self-hosted via Helm on Kubernetes, keeping all media within the customer's network boundary. This is the recommended path for Hard tier tenants in regulated industries.

---

## 10. Open Questions / Decisions Needed

| # | Question | Owner | Default if not decided |
|---|---|---|---|
| 1 | Hard vs soft tenancy as default SaaS offering? | Product | Soft tenancy default; Hard tier as add-on |
| 2 | Which cloud KMS provider is primary? | Infra | AWS KMS (pluggable via abstraction layer) |
| 3 | E2EE — offer per-tenant or globally off? | Product + Security | Off by default; per-tenant opt-in |
| 4 | Audio redaction — MVP or later? | Product | Later (v2); transcript redaction is MVP |
| 5 | ASR provider — in-VPC or vendor API? | Infra | Vendor API (Deepgram/Google) for MVP; in-VPC option for Hard tier |
| 6 | Audit log integrity — hash chain or external notary? | Security | Hash chain MVP; notary for compliance tier |
| 7 | SIEM integration in MVP or later? | Product | Log export endpoint in MVP; full webhook stream later |

---

*Next: [System Design (C4 Model)](./system-design-c4.md)*
