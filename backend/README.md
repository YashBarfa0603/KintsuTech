# KintsuTech Backend — Autonomous API Resilience Platform

**Tagline:** Detect. Adapt. Recover.  
**Problem Statement:** PS3 — *The Internet After the API* (HackWave 3.0)

KintsuTech provides an automated, guarded resilience proxy for third-party and upstream APIs. When an upstream provider introduces breaking changes (such as renaming fields, altering data types, or changing schemas), KintsuTech detects the drift, measures the downstream blast radius using NetworkX graph analysis, independently validates a proposed compatibility adapter against regression tests, requires human authorization, activates the adapter into a persistent SQLite registry, dynamically transforms incoming traffic through its resilience proxy, and supports instant rollback and audit tracking.

---

## 1. Quick Start & Setup

### Requirements
- macOS / Linux
- Python 3.10+
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Running the Backend Locally

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```
- **API Base URL**: `http://127.0.0.1:8000/api/v1`
- **Interactive Swagger UI**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/api/v1/health`
- **Readiness Check**: `http://127.0.0.1:8000/api/v1/health/readiness`

---

## 2. Interactive Hackathon Demo Walkthrough

We provide an automated, colorized end-to-end terminal demo script:

```bash
# Run the complete 10-stage demo walkthrough
./backend/demo_walkthrough.sh
```

### Manual Step-by-Step Demo Sequence (via curl)

#### Step 1: Baseline Request (No Adapter Active)
```bash
curl -s http://127.0.0.1:8000/api/v1/proxy/weather
```
**Response:**
```json
{
  "status": "unchanged",
  "adapted": false,
  "incident_id": null,
  "data": {"city": "Indore", "temperature": 30, "condition": "Sunny"},
  "source": "provider"
}
```

#### Step 2: Detect Upstream Drift & Impact
Upstream provider renames `temperature` to `temp_c`:
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ai/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "weather",
    "baseline": {"city": "Indore", "temperature": 30, "condition": "Sunny"},
    "current": {"city": "Indore", "temp_c": 30, "condition": "Sunny"},
    "create_incident_on_change": true
  }'
```
*Creates incident `INC-001` with blast radius impact analysis.*

#### Step 3: Guarded Rejection (Safety Enforcement)
Attempting to activate an unvalidated repair is blocked:
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/repairs/activate \
  -H "Content-Type: application/json" \
  -d '{"incident_id": "INC-001", "adapter": {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature", "semantics_confirmed": true}}'
```
*Returns HTTP 400: "Cannot activate repair for INC-001: Repair has not passed independent validation."*

#### Step 4: Independent Deterministic Validation
Validate the proposed field-copy mapping against trusted test cases:
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/repairs/validate \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-001",
    "adapter": {
      "operation": "copy_field",
      "source_field": "temp_c",
      "target_field": "temperature",
      "semantics_confirmed": true
    },
    "test_cases": [
      {
        "input": {"temp_c": 25.0, "condition": "Sunny"},
        "expected": {"temp_c": 25.0, "condition": "Sunny", "temperature": 25.0}
      }
    ]
  }'
```
*Returns `eligible_for_activation: true`.*

#### Step 5: Authorized Human Activation
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/repairs/activate \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-001",
    "adapter": {
      "operation": "copy_field",
      "source_field": "temp_c",
      "target_field": "temperature",
      "semantics_confirmed": true
    },
    "authorizer": "senior_architect_alice",
    "note": "Validated for HackWave 3.0 Demo"
  }'
```
*Adapter is stored in persistent SQLite storage.*

#### Step 6: Automatic Proxy Adaptation
When consumer queries the proxy while the upstream provider returns the renamed payload:
```bash
curl -s "http://127.0.0.1:8000/api/v1/proxy/weather?schema=temp_c"
```
**Response:**
```json
{
  "status": "adapted",
  "adapted": true,
  "incident_id": "INC-001",
  "data": {
    "city": "Indore",
    "condition": "Sunny",
    "temp_c": 30,
    "temperature": 30
  },
  "source": "provider"
}
```
*Legacy field `temperature` is automatically restored for backward-compatibility!*

#### Step 7: Instant Rollback
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/repairs/rollback \
  -H "Content-Type: application/json" \
  -d '{"service_id": "weather", "authorizer": "incident_lead_bob", "reason": "Upstream fixed"}'
```
Calling the proxy immediately returns unadapted raw provider data without restarting the server:
```bash
curl -s "http://127.0.0.1:8000/api/v1/proxy/weather?schema=temp_c"
# Output: {"status":"unchanged","adapted":false,"incident_id":null,"data":{"city":"Indore","condition":"Sunny","temp_c":30},"source":"provider"}
```

#### Step 8: Complete Audit Log
```bash
curl -s http://127.0.0.1:8000/api/v1/repairs/audit
```

---

## 3. Configuration & Security

| Environment Variable | Default Value | Description |
|----------------------|---------------|-------------|
| `KINTSUTECH_API_KEY` | *(None / Unset)* | Secret key for authenticating protected mutation endpoints. Never hardcoded or logged. |
| `KINTSUTECH_REQUIRE_AUTH` | `false` | When `true`, strictly enforces API-key authentication even in non-production environments. |
| `ENVIRONMENT` | `development` | Deployment environment (`development` / `production`). If `production`, API key authentication is strictly required and fails safely (401) if `KINTSUTECH_API_KEY` is unset. |
| `KINTSUTECH_WEBHOOK_SECRET` | *(Random 32-byte hex at startup)* | HMAC-SHA256 signing secret for webhooks. If unset, generates a dynamic runtime key. |
| `WEATHER_PROVIDER_URL` | `http://127.0.0.1:8000/api/v1/mock/weather` | Upstream target URL for the weather service |
| `KINTSUTECH_DATABASE_URL` | `sqlite:///backend/data/kintsutech.db` | SQLite persistence database location |
| `FRONTEND_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed CORS origins for frontend UI |

### Authenticated Request Examples

When `KINTSUTECH_API_KEY` is configured, pass the key via `X-API-Key` or `Authorization: Bearer <key>`:

```bash
# 1. Authorize repair activation using X-API-Key header
curl -s -X POST http://127.0.0.1:8000/api/v1/repairs/activate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{
    "incident_id": "INC-001",
    "adapter": {
      "operation": "copy_field",
      "source_field": "temp_c",
      "target_field": "temperature",
      "semantics_confirmed": true
    },
    "authorizer": "lead_architect_alice"
  }'

# 2. Authorize rollback using Authorization: Bearer
curl -s -X POST http://127.0.0.1:8000/api/v1/repairs/rollback \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-api-key" \
  -d '{
    "service_id": "weather",
    "authorizer": "lead_architect_alice",
    "reason": "Upstream resolved"
  }'

# 3. Register webhook destination with SSRF protection
curl -s -X POST http://127.0.0.1:8000/api/v1/webhooks/subscriptions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{
    "target_url": "https://api.kintsutech.com/webhook",
    "events": ["repair.activated", "repair.rollback_completed"]
  }'
```

### Security Hardening Features (Phase 5A)
1. **API-Key Authentication**: Sensitive operational endpoints (`/repairs/activate`, `/repairs/rollback`, `/services/*/baseline`, `/webhooks/subscriptions`, `/mcp/tools/call`) are protected. Public monitoring and proxy endpoints remain accessible.
2. **Fail-Safe Mode**: If `ENVIRONMENT=production`, the server fails safely (401) on protected operations if no API key is configured.
3. **SSRF & DNS Rebinding Protection**: Webhook destinations cannot target loopback (`127.0.0.0/8`), private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local metadata (`169.254.169.254`), or broadcast ranges. HTTP client enforces `follow_redirects=False`.
4. **Secret Redaction**: Webhook secrets are never returned in subscription listings (`GET /api/v1/webhooks/subscriptions`).
5. **Exact Adapter Hash Binding**: When an adapter is validated, its canonical SHA-256 hash is computed and stored. Activation recomputes the requested adapter's hash and rejects activation if it differs from the validated adapter, preventing adapter tampering between validation and activation.

### Database Tables (SQLAlchemy 2.0)
- `services`: Registered monitored APIs and endpoints.
- `baselines`: Versioned baseline responses with SHA256 checksums.
- `incidents`: Monotonic, collision-free incidents (`INC-001`, `INC-002`, ...).
- `validations`: Deterministic regression test verification outcomes with canonical `adapter_hash`.
- `active_adapters`: Authorizer-guarded active repair adapters.
- `audit_log`: Append-only audit trail recording timestamps and actors.
- `webhook_subscriptions`: Persisted webhook subscriptions with target URL, event filters, active status, creation time, and securely stored secret.
- `webhook_deliveries`: Persisted delivery attempts, statuses, HTTP status codes, timestamps, and sanitized errors.
- `webhook_idempotency`: Processed event IDs with automatic bounded retention pruning.

### Persistent, Reliable Webhooks (Phase 5B)

1. **Persistent SQLite Storage**:
   - Subscriptions, delivery logs, and idempotency records are stored in SQLite and survive application and `StorageRegistry` restarts.
   - Database migrations use safe schema updates (`Base.metadata.create_all` and `ALTER TABLE`) without dropping existing data.
   - High concurrency is handled using SQLite WAL mode (`PRAGMA journal_mode=WAL`) and a 5000ms busy timeout.

2. **Secret Redaction**:
   - Webhook secrets are never returned in ANY API response (`POST /api/v1/webhooks/subscriptions`, `GET /api/v1/webhooks/subscriptions`, or `GET /api/v1/webhooks/subscriptions/{id}`).
   - API responses indicate whether a secret is configured (`"secret_configured": true`) without exposing the key material.

3. **Non-Blocking Background Delivery**:
   - Outgoing webhook delivery is completely decoupled from the critical path of repair activation, rollback, validation, and incident creation.
   - Uses an in-process background worker pool (`ThreadPoolExecutor`) via `dispatch_event_background()`. Primary HTTP responses return immediately (< 50ms) even when webhook subscribers are slow or unreachable.
   - *Architecture Note:* Delivery is best-effort in-process background work. In-flight jobs do not survive sudden process crashes.

4. **Retry Policy & Timeout Limits**:
   - Explicit timeout bounds: connect = 2.0s, read = 3.0s, write = 3.0s, pool = 5.0s.
   - Bounded retries: up to 3 bounded attempts with exponential backoff (`0.2s * 2^(attempt-1)`, capped at 2.0s).
   - `follow_redirects=False` strictly enforced to prevent redirect-based SSRF bypass.
   - Target URLs are re-validated against SSRF / DNS rebinding immediately before every outbound request attempt.

5. **Sanitized Error Logging**:
   - Stored error messages in delivery logs are sanitized to remove Bearer tokens, API keys, signature headers, and subscriber secrets (`[REDACTED]`).

6. **Bounded Idempotency Retention**:
   - Incoming and outgoing events are deduplicated via `webhook_idempotency`.
   - Bounded retention policy automatically prunes the oldest records when total entries exceed the limit (default 1,000), preventing database bloat.

7. **Supported Event Types**:
   - `incident.created`: Dispatched only after an incident is successfully detected and created in SQLite.
   - `repair.validated`: Dispatched only after proposed repair adapter passes independent validation.
   - `repair.activated`: Dispatched only after authorized repair activation succeeds (never emitted if activation fails or adapter hash mismatch occurs).
   - `repair.rollback_completed`: Dispatched only after rollback completes.

---

## 4. Test Suite Execution

Run all test suites across the project:

```bash
# 1. Run backend tests (143 tests)
cd backend && uv run pytest -q

# 2. Run AI engine tests (78 tests)
cd ../ai_engine && uv run pytest -q

# 3. Compile checks across both projects
cd backend && uv run python -m compileall -q app tests && cd ../ai_engine && uv run python -m compileall -q -x "\.venv" .
```

**Total automated tests:** **221 passed** (143 backend + 78 AI engine).

---

## 5. System Limitations & Safety Principles

1. **Deterministic Guardrails**: KintsuTech never promotes an AI-proposed adapter directly to production without passing deterministic test cases.
2. **Explicit Human Authorization**: Every activation and rollback requires an authenticated authorizer name and audit entry.
3. **Semantic Equivalence Guard**: Adapters currently support restricted, safe `copy_field` semantics. Field mappings cannot silently assume unit equivalence (e.g. Celsius vs Fahrenheit) without explicit reviewer confirmation.
4. **Controlled Upstream Proxy**: KintsuTech only adapts traffic explicitly routed through its proxy endpoints. It does not claim arbitrary network interception.
5. **Timeout Safety**: Upstream requests enforce 2.0s connect and 5.0s read timeouts, mapping to HTTP 504 and 502 rather than hanging worker processes.
