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
| `ENVIRONMENT` | `development` | Deployment environment (`development` / `production`). In `production`, startup fails-closed if required secrets or safe configurations are missing. |
| `KINTSUTECH_API_KEY` | *(None / Unset)* | Secret key for authenticating mutation and MCP tools. Required in `production` (>= 16 characters). Never hardcoded or logged. |
| `KINTSUTECH_REQUIRE_AUTH` | `false` | When `true`, strictly enforces API-key authentication even in development. |
| `KINTSUTECH_WEBHOOK_SECRET` | *(Random 32-byte hex at startup)* | HMAC-SHA256 signing secret for webhooks. In `production`, must be explicitly configured (>= 16 characters). |
| `FRONTEND_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed CORS origins (comma-separated). In `production`, must be explicitly configured without wildcards (`*`). |
| `MAX_REQUEST_BODY_SIZE` | `1048576` (1 MB) | Maximum accepted request payload size in bytes. Oversized payloads return HTTP 413. |
| `KINTSUTECH_RATE_LIMIT_ENABLED` | `true` | When `true`, enforces in-memory sliding-window rate limiting on sensitive endpoints. |
| `RATE_LIMIT_MUTATION_PER_MINUTE` | `60` | Request rate limit per minute per client IP for mutations and admin routes. Returns HTTP 429 with `Retry-After`. |
| `RATE_LIMIT_WEBHOOK_INGEST_PER_MINUTE` | `120` | Request rate limit per minute per client IP for incoming webhook ingestion. |
| `KINTSUTECH_TRUST_PROXY` | `false` | When `true`, extracts client IP from `X-Forwarded-For` / `X-Real-IP`. Keep `false` unless running behind a trusted reverse proxy. |
| `WEATHER_PROVIDER_URL` | `http://127.0.0.1:8000/api/v1/mock/weather` | Upstream target URL for the weather service |
| `KINTSUTECH_DATABASE_URL` | `sqlite:///backend/data/kintsutech.db` | SQLite persistence database location |

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

### Semantic Repair Validation & Consumer Contracts (Phase 5C)

1. **Supported Operations**:
   - `copy_field`: Restores renamed fields without mutating input.
   - `convert_units`: Applies deterministic linear transformation (`output = input * scale + offset`) with explicit, finite numeric `scale` and `offset` parameters.

2. **Explicit Typed Field Constraints**:
   - Supported schema types: `string`, `integer`, `number`, `boolean`, `object`, and `array`.
   - Strict type checking: Booleans are strictly rejected where numeric values are required. Silent coercion between strings and numbers is blocked.
   - Required vs. optional fields and nullable vs. non-nullable values are strictly enforced.
   - Non-finite numbers (NaN, +/- infinity) are rejected.

3. **Numeric Ranges & Invariants**:
   - Optional `minimum` and `maximum` constraints for numeric fields (e.g. humidity `[0, 100]`, Celsius temperature `>= -273.15`).
   - Applied strictly against explicitly declared consumer contracts or service schemas (never assumed or globally guessed).

4. **Downstream Consumer Contract Verification**:
   - Independent verification against all downstream consumer contracts registered in `ConsumerContractRegistry` or supplied in the validation request.
   - Mandatory contract failures or missing required consumer contracts immediately disqualify a repair (`eligible_for_activation = false`).
   - Contract endpoints: `GET /api/v1/contracts` (discoverable contracts) and `POST /api/v1/contracts` (authenticated contract registration).

5. **Validation Integrity & Version Binding**:
   - Binds the complete adapter configuration hash (`adapter_hash`) and the validated `contract_version` to the `validations` table.
   - Guarded activation requires both exact canonical adapter hash matching and contract version matching, rejecting any post-validation tampering or version drift.

---

## 4. Test Suite Execution

Run all test suites across the project:

```bash
# 1. Run backend tests (175 tests)
cd backend && uv run pytest -q

# 2. Run AI engine tests (88 tests)
cd ../ai_engine && uv run pytest -q

# 3. Compile checks across both projects
cd backend && uv run python -m compileall -q app tests && cd ../ai_engine && uv run python -m compileall -q -x "\.venv" .
```

**Total automated tests:** **263 passed** (175 backend + 88 AI engine).

---

## 5. Genuine Model Context Protocol (MCP) Implementation (Phase 5D)

KintsuTech implements genuine **Model Context Protocol (MCP)** support using the official Python MCP SDK (`mcp>=2.3.0`), rejecting hand-rolled fake JSON-RPC endpoints. It exposes rich, guarded tools to AI agents, Claude Desktop, Cursor, or autonomous systems over both **Streamable HTTP** and **stdio** transports.

### Transports & Connectivity

1. **Hosted Streamable HTTP Transport (Recommended)**:
   - Mounted directly inside the FastAPI application at `/mcp` (and `/api/v1/mcp/stream`).
   - Accessible at `http://127.0.0.1:8000/mcp/`.
   - Supports bi-directional streaming, session lifecycle management, and JSON-RPC message framing via `mcp.client.streamable_http.streamable_http_client`.

2. **stdio Transport (Local Subprocess / CLI)**:
   - Run the standalone MCP server process over standard input/output:
   ```bash
   cd backend
   uv run python -m app.mcp_server
   ```

3. **Backward-Compatible REST Endpoints**:
   - `GET /api/v1/mcp/tools`: Returns the complete tool catalog with JSON-schema input definitions.
   - `POST /api/v1/mcp/tools/call`: Executes tools through the REST bridge with automated API-key header propagation.

### Available MCP Tools Catalog

| Tool Name | Type | Description | Required Arguments |
|-----------|------|-------------|--------------------|
| `list_services` | Read-only | List all monitored services, baselines, and active adapters | None |
| `get_service_baseline` | Read-only | Retrieve versioned baseline response for a service | `service_id` |
| `analyze_service_changes` | Read-only | Deterministic diff and AI-assisted change analysis | `service_id`, `baseline`, `current` |
| `calculate_dependency_impact` | Read-only | Calculate blast radius and downstream dependents via NetworkX | `service_id` |
| `list_incidents` | Read-only | List recorded incidents filtered by status or service | Optional `service_id`, `status` |
| `get_incident_evidence` | Read-only | Inspect comprehensive evidence and structural diffs | `incident_id` |
| `list_consumer_contracts` | Read-only | List registered downstream consumer contracts & schemas | Optional `service_id` |
| `validate_repair_proposal` | Non-mutating | Deterministically validate adapter without mutating state | `incident_id`, `adapter`, optional `test_cases`, `consumer_contracts` |
| `request_repair_activation` | Mutating (Guarded) | Safely activate validated adapter; checks auth, adapter hash, and contract version | `incident_id`, `adapter`, `authorizer`, `api_key` (if auth enforced) |
| `request_rollback` | Mutating (Guarded) | Deactivate active adapter and restore un-adapted state | `service_id`, `authorizer`, `api_key` (if auth enforced) |

### MCP Client Configuration Examples

#### Python MCP Client (Streamable HTTP)
```python
import asyncio
import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with httpx2.AsyncClient(base_url="http://127.0.0.1:8000") as http_client:
        async with streamable_http_client("http://127.0.0.1:8000/mcp/", http_client=http_client) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                print("Available tools:", [t.name for t in tools.tools])

                # Execute read-only impact analysis
                res = await session.call_tool("calculate_dependency_impact", {"service_id": "weather"})
                print("Tool output:", res.content[0].text)

asyncio.run(main())
```

#### Claude Desktop Configuration (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "kintsutech": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/yash/PROJECTS/HackWave3.0/KintsuTech/backend",
        "run",
        "python",
        "-m",
        "app.mcp_server"
      ]
    }
  }
}
```

### Security & Integrity Enforcement in MCP

- **Guarded Mutating Tools**: `request_repair_activation` and `request_rollback` strictly verify credentials (`api_key`) via constant-time comparison when authentication is configured.
- **Canonical Adapter Hash Verification**: Activation computes the canonical SHA-256 hash of the incoming adapter configuration and verifies that it exactly matches the independently validated adapter, blocking post-validation parameter tampering.
- **Contract Version Matching**: Ensures the adapter adheres to the consumer contract version verified during validation.
- **Zero Credential Leakage**: Tool results and error payloads never expose API keys, webhook secrets, or environment credentials.

---

## 6. System Limitations & Safety Principles

1. **Deterministic Guardrails**: KintsuTech never promotes an AI-proposed adapter directly to production without passing deterministic test cases.
2. **Explicit Human Authorization**: Every activation and rollback requires an authenticated authorizer name and audit entry.
3. **Semantic Equivalence Guard**: Adapters currently support restricted, safe `copy_field` and `convert_units` semantics. Field mappings cannot silently assume unit equivalence (e.g. Celsius vs Fahrenheit) without explicit reviewer confirmation.
4. **Controlled Upstream Proxy**: KintsuTech only adapts traffic explicitly routed through its proxy endpoints. It does not claim arbitrary network interception.
5. **Timeout Safety**: Upstream requests enforce 2.0s connect and 5.0s read timeouts, mapping to HTTP 504 and 502 rather than hanging worker processes.

---

## 7. Production Deployment Hardening (Phase 5E)

### Fail-Closed Security Configuration
- When `ENVIRONMENT=production`, KintsuTech validates all security parameters at startup:
  - `KINTSUTECH_API_KEY`: Must be configured, at least 16 characters, and not in the trivial blacklist. Startup is aborted immediately if missing or weak.
  - `KINTSUTECH_WEBHOOK_SECRET`: Must be explicitly configured and at least 16 characters.
  - `FRONTEND_ORIGINS`: Must be an explicit list of origins. Wildcards (`*`) are strictly forbidden.
- Local development (`ENVIRONMENT=development`) remains convenient without weakening production defaults.

### Request Protection, Rate Limiting & Proxy Trust
- **Bounded Request Body Size**: Implemented as pure ASGI `BoundedBodyLimitMiddleware`. Configurable via `MAX_REQUEST_BODY_SIZE` (default: 1,048,576 bytes = 1 MB). Enforces limits on requests both with `Content-Length` headers and chunked/streamed requests (`Transfer-Encoding: chunked`), preventing memory exhaustion and bypassing across all routes and mounted MCP endpoints. Oversized requests return HTTP 413 (Payload Too Large). Malformed headers return HTTP 400.
- **Sliding-Window Rate Limiting (Per-Process)**: In-memory thread-safe rate limiter tracks client requests. Sensitive mutation endpoints (`/services/{service_id}`, `/services/{service_id}/baseline`, `/repairs/validate`, `/repairs/activate`, `/repairs/rollback`, `/contracts`, `/webhooks/subscriptions`, `/mcp/tools/call`) enforce 60 req/min; webhook ingestion (`/webhooks/incoming`) enforces 120 req/min. Exceeded limits return HTTP 429 with a standard `Retry-After` header.
  - *Architecture Note:* The sliding-window rate limiter is **in-memory and per-process**. In multi-worker or horizontally scaled multi-pod architectures, a centralized caching backend (e.g., Redis) should back rate limiting.
- **Reverse Proxy Header Trust**: By default, `X-Forwarded-For` and `X-Real-IP` headers are ignored to prevent IP spoofing attacks. Set `KINTSUTECH_TRUST_PROXY=true` only when running behind an authenticated reverse proxy (e.g., NGINX, Cloudflare).

### Storage Architecture & Lifecycle Reliability
- **SQLite Concurrency**: SQLite runs with WAL mode (`PRAGMA journal_mode=WAL`) and a 5,000ms busy timeout.
- **Resource Lifecycle**: The FastAPI `lifespan` manager guarantees clean startup and shutdown:
  - MCP session manager lifecycle states (`_has_started`) are tracked and reset safely, permitting repeated startup/shutdown cycles without resource collision.
  - Background webhook thread pools are gracefully flushed, and auto-reinitialize if invoked post-shutdown.
  - SQLAlchemy database connection pool engines are disposed cleanly via `storage_registry.close()`.
- **Persistence Limitations**:
  - SQLite storage requires a persistent volume mount (`/app/data`) in containerized environments.
  - SQLite supports single-pod deployments. Multi-pod horizontal scaling requires an external PostgreSQL database via `KINTSUTECH_DATABASE_URL`.
  - Background webhook dispatch is in-process and best-effort; in-flight tasks do not survive sudden process crashes or host termination.

### Docker Container Deployment

A multi-stage, unprivileged production Dockerfile is provided in [`backend/Dockerfile`](file:///Users/yash/PROJECTS/HackWave3.0/KintsuTech/backend/Dockerfile):

```bash
# 1. Build the production container (from repository root)
docker build -f backend/Dockerfile -t kintsutech-backend:latest .

# 2. Run the container with persistent storage and environment file
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/backend/data:/app/data \
  --env-file backend/.env \
  --name kintsutech-api \
  kintsutech-backend:latest
```

- **Runtime User**: Runs as unprivileged user `kintsu:kintsu` (UID/GID isolated).
- **Health Check**: Automated periodic health checks via standard library `urllib` targeting `/api/v1/health`.
- **Single-Worker Default**: Defaults to 1 worker process with Uvicorn to ensure safe SQLite write concurrency.
- *Host Note:* Docker daemon was unavailable on the local audit machine (`docker not found`), so the container image build was verified structurally (Dockerfile + `.dockerignore`) rather than built live.

### Securing MCP Endpoints

- Hosted **Streamable HTTP transport** is available at `http://127.0.0.1:8000/mcp/` and `/api/v1/mcp/stream`.
- Read-only tools (`list_services`, `get_service_baseline`, `calculate_dependency_impact`, `list_incidents`, `list_consumer_contracts`) allow safe introspection without authentication.
- Mutating tools (`request_repair_activation`, `request_rollback`) strictly enforce:
  1. **HTTP Transport Header Authentication**: For remote HTTP callers, credentials must be provided via HTTP headers (`X-API-Key` or `Authorization: Bearer <key>`) and verified via `Context.headers`. The server does NOT rely on a client-supplied `api_key` tool argument alone for remote calls.
  2. **stdio Transport Fallback**: When called in local stdio subprocess mode or direct in-process calls (`ctx.headers` is None), the `api_key` tool argument is accepted as a fallback.
  3. **Canonical SHA-256 Adapter Hash Verification**: Activation computes the canonical SHA-256 hash of the incoming adapter configuration and verifies that it exactly matches the independently validated adapter, blocking post-validation parameter tampering.
  4. **Consumer Contract Version Matching**: Ensures the adapter adheres to the consumer contract version verified during validation.
- Tool responses and error payloads never leak internal environment variables, API keys, or webhook signing secrets.

---

## Alert Lifecycle & Voice Agent Pipeline

### Architecture & Component Responsibilities

```
                                +-----------------------------+
                                |  Timeline / Incident Event |
                                +--------------+--------------+
                                               |
                                               v
                                +-----------------------------+
                                |      AlertService           |
                                |  - Evaluates severity       |
                                |  - Checks quiet hours & tz  |
                                |  - Enforces idempotency key |
                                +--------------+--------------+
                                               |
                                               v
+------------------------+      +-----------------------------+      +------------------------+
|   Background Worker    | <--> |   Persistent Storage        | <--> |  Authenticated APIs    |
|   (AlertScheduler)     |      |   (AlertModel, Deliveries,  |      |  - List / Filter       |
|  - Distributed locks   |      |    AlertPreferences)        |      |  - Acknowledge/Resolve |
|  - Bounded retries     |      +-----------------------------+      |  - User preferences    |
|  - Auto-escalation     |                     ^                     +------------------------+
+------------------------+                     |
                                               v
                                +-----------------------------+
                                |      Voice Agent Pipeline   |
                                |  - MLX Whisper STT (local)  |
                                |  - Ollama / Fallback Engine |
                                |  - PCM WAV TTS Synthesizer  |
                                |  - Audited Voice Ack        |
                                +-----------------------------+
```

1. **`app.storage.StorageRegistry`**:
   - Manages tables: `alerts`, `alert_deliveries`, `alert_preferences`.
   - Idempotency via composite constraint `(idempotency_key, user_id)`.
   - Strict status transition state machine: `pending` -> `delivering` -> `delivered` -> `acknowledged` / `escalated` / `resolved` / `failed` / `cancelled`.
   - Concurrency locking with `locked_until` leases.
2. **`app.alerts.AlertService`**:
   - Evaluates incident and timeline events. High/critical incidents trigger immediate alerts; breaking schema changes trigger alerts; low-severity events respect user `min_severity`.
   - Evaluates quiet hours based on user's timezone (`ZoneInfo`).
   - Dispatches initial delivery through configured channels (`in_app`, `voice`). Telephony is disabled by default.
3. **`app.scheduler.AlertScheduler`**:
   - Background async worker polling for due/overdue alerts.
   - Claims atomic leases (`claim_due_alerts`) so concurrent workers do not double-process alerts.
   - Retries failed attempts with bounded exponential backoff up to `max_attempts`.
   - Escalates unacknowledged alerts when deadlines expire.
4. **`app.voice.VoiceAgent`**:
   - **STT**: Validates audio uploads (format, max 15MB, silence/corruption checks) and uses local Apple Silicon `mlx_whisper`.
   - **Reasoning**: Resolves intent against user's authorized alerts. Clarifies ambiguous requests ("You have multiple alerts, which one?"). Consequential state changes (acknowledgment) require strictly validated matches.
   - **TTS**: Synthesizes response audio via Piper voice model or standard RFC-compliant WAV audio stream.
   - **Telephony Safety**: PSTN calls remain strictly disabled (`telephony_enabled=False`).

### Database Schema & Safe Migration Strategy

- **`alerts` table**:
  - `id`: Unique identifier (`alt_...`).
  - `user_id`: Target recipient Supabase user UUID.
  - `incident_id`: Associated incident ID (`INC-...`), if applicable.
  - `source_event_id`: Source webhook/timeline event ID.
  - `idempotency_key`: Deduplication key.
  - `title`, `message`: Alert details.
  - `severity`: `"critical"`, `"high"`, `"medium"`, `"low"`, `"info"`.
  - `status`: Valid status state machine.
  - `created_at`, `updated_at`, `due_at`, `acknowledged_at`, `resolved_at`.
  - `escalation_level`, `next_escalation_at`, `attempt_count`, `last_attempt_at`.
  - `delivery_channel`, `locked_until`, `metadata_json`.
- **`alert_deliveries` table**: Complete audit log of every delivery attempt, channel, status, and escalation step.
- **`alert_preferences` table**: Configurable per-user channels, quiet hours, timezone, voice toggles, retry limits, and telephony consent.
- **Migration Strategy**: Handled automatically in `StorageRegistry._migrate_schema()`. Recreates tables safely without dropping data, alters missing columns, and ensures zero downtime during schema upgrades.

### API Endpoints

All alert operations require Bearer token authentication via Supabase JWT (`Authorization: Bearer <token>`):

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/alerts` | Create a persistent alert (idempotent via `idempotency_key`) |
| `GET` | `/api/v1/alerts` | List current user's alerts (supports `status`, `severity`, `incident_id` filters) |
| `GET` | `/api/v1/alerts/{alert_id}` | Retrieve alert details (scoped to owner; 404 if unauthorized) |
| `POST` | `/api/v1/alerts/{alert_id}/acknowledge` | Acknowledge alert (idempotent, stops escalation) |
| `POST` | `/api/v1/alerts/{alert_id}/resolve` | Resolve alert (marks terminal status) |
| `GET` | `/api/v1/alerts/{alert_id}/history` | Retrieve full delivery and escalation audit trail |
| `GET` | `/api/v1/alert-preferences` | Read user's alert channels, quiet hours, and timeouts |
| `PUT` | `/api/v1/alert-preferences` | Update user alert preferences |
| `POST` | `/api/v1/voice/transcribe` | Upload audio and transcribe via local MLX Whisper |
| `POST` | `/api/v1/voice/respond` | Natural language voice turn (detects ack/inquiry with audit) |
| `POST` | `/api/v1/voice/synthesize` | Synthesize text to playable `audio/wav` |
| `GET` | `/api/v1/voice/status` | Read component readiness (STT, Ollama LLM, TTS, Telephony) |

### Setup & Local Commands (macOS)

#### 1. Start the Backend & Scheduler
```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

#### 2. Run All Automated Tests
```bash
cd backend
# Run all tests (baseline 255 + 41 new alert/voice tests = 296 passing)
uv run pytest -v

# Run alert lifecycle tests only
uv run pytest tests/test_alerts.py -v

# Run voice agent tests only
uv run pytest tests/test_voice_agent.py -v
```

#### 3. Optional Local Ollama Setup
```bash
# Install Ollama on macOS
brew install ollama

# Pull recommended model
ollama pull qwen2.5:3b

# Start daemon
ollama serve

# Enable in backend/.env:
# KINTSUTECH_AGENT_LLM_ENABLED=true
# KINTSUTECH_OLLAMA_URL=http://127.0.0.1:11434
# KINTSUTECH_OLLAMA_MODEL=qwen2.5:3b
```

#### 4. Optional Local Piper TTS Setup
```bash
# Download Piper voice model and set in backend/.env:
# KINTSUTECH_VOICE_TTS_ENABLED=true
# KINTSUTECH_TTS_MODEL_PATH=/path/to/en_US-lessac-medium.onnx
```

### Telephony & Vapi Outbound Calling Integration

KintsuTech integrates with the official **Vapi Outbound Calling REST API** (`POST https://api.vapi.ai/call/phone`) to escalate critical unacknowledged alerts to responsible on-call engineers.

#### Outbound Calling Lifecycle & Safety Rules

1. **Safety Default**: Outbound telephone calls are **strictly disabled by default** (`KINTSUTECH_TELEPHONY_ENABLED=false`). Automated tests always run with mocked providers and never initiate real phone calls.
2. **Escalation Trigger**: When an alert remains unacknowledged past its acknowledgment deadline:
   - The scheduler atomically acquires a distributed lease (`claim_due_alerts`).
   - The scheduler checks recipient preferences: explicit `phone_consent` must be `true`, `phone_number` must be valid E.164, and the user must not be in quiet hours (unless critical emergency).
   - If previous call attempts have reached `max_attempts` or an active call is already `queued`/`in-progress`, the call is safely skipped (idempotent & bounded).
3. **Outbound Vapi Call**: The backend issues an authenticated request to `POST /call/phone`:
   - Passes `assistantId` and `phoneNumberId` (imported number; Vapi free numbers do not support outbound calls).
   - Passes a **privacy-conscious alert summary** via `assistantOverrides.variableValues` (alert ID, title, severity, incident ID; no internal secrets).
   - Persists the returned `call_id` and initial status (`queued`) in `AlertDeliveryModel` and alert metadata.
4. **Verified Canonical Webhook Processing**:
   - Vapi sends status updates and end-of-call reports to the canonical endpoint: `POST /api/vapi/webhook`.
   - The endpoint verifies the Bearer token or `x-vapi-secret` header using constant-time comparison against `KINTSUTECH_VAPI_WEBHOOK_TOKEN` (or `VAPI_WEBHOOK_SECRET`).
   - Duplicate webhook deliveries are handled idempotently via `webhook_idempotency` tracking.
   - Call duration, status (`in-progress`, `ended`, `completed`), and ended reasons are recorded without storing raw audio or personal info.
   - If the call results in user acknowledgment (`assistant-acknowledged-alert` or `customer-acknowledged`), the alert status is automatically transitioned to `acknowledged`, terminating further escalation.

#### Environment Configuration (`backend/.env`)

```bash
KINTSUTECH_TELEPHONY_ENABLED=false
KINTSUTECH_TELEPHONY_PROVIDER=vapi
VAPI_API_KEY=your-vapi-private-api-key
VAPI_ASSISTANT_ID=your-vapi-assistant-uuid
VAPI_PHONE_NUMBER_ID=your-vapi-phone-number-uuid
KINTSUTECH_VAPI_WEBHOOK_TOKEN=your-webhook-secret-token
VAPI_BASE_URL=https://api.vapi.ai
VAPI_REQUEST_TIMEOUT_SECONDS=10.0
```

#### Local Webhook Testing Command

```bash
# Test local canonical webhook endpoint (authenticated via Bearer token):
curl -i -X POST http://localhost:8000/api/vapi/webhook \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_WEBHOOK_TOKEN>" \
  -d '{"message":{"type":"status-update","call":{"id":"local-test","status":"in-progress"}}}'
```

#### Manual Live-Call Verification Procedure

To test a live outbound phone call without waiting for automated escalation timeouts:

```bash
# 1. Start the backend server
cd backend
uv run uvicorn app.main:app --port 8000 --reload

# 2. Check telephony readiness (should report ready: true once credentials are set)
curl -s http://127.0.0.1:8000/api/v1/telephony/status | jq .

# 3. Authenticate and update your test user alert preferences with phone consent
curl -X PUT http://127.0.0.1:8000/api/v1/alert-preferences \
  -H "Authorization: Bearer <SUPABASE_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_consent": true,
    "phone_number": "+1XXXXXXXXXX",
    "channels": ["in_app", "phone"]
  }'

# 4. Create an urgent alert with delivery_channel: "phone"
curl -X POST http://127.0.0.1:8000/api/v1/alerts \
  -H "Authorization: Bearer <SUPABASE_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Manual Test Call",
    "message": "Testing Vapi automated voice escalation",
    "severity": "critical",
    "delivery_channel": "phone"
  }'

# 5. Check call history to inspect Vapi Call ID and status
curl -s http://127.0.0.1:8000/api/v1/alerts/<ALERT_ID>/history \
  -H "Authorization: Bearer <SUPABASE_TOKEN>" | jq .
```
