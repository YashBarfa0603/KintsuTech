# KintsuTech — Autonomous API Resilience Platform

**Tagline:** Detect. Adapt. Recover.  
**Problem Statement:** PS3 — *The Internet After the API* (HackWave 3.0)

KintsuTech provides an automated, guarded resilience proxy for third-party and upstream APIs. When an upstream provider introduces breaking changes, KintsuTech detects the drift, measures the downstream blast radius using NetworkX graph analysis, independently validates a proposed compatibility adapter against regression tests, requires authorization, activates the adapter into a persistent SQLite registry, dynamically transforms incoming traffic through its resilience proxy, and supports instant rollback and audit tracking.

---

## Quick Start & Setup

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

## Configuration & Security (Phase 5A)

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

### Security Hardening Features
1. **API-Key Authentication**: Sensitive operational endpoints (`/repairs/activate`, `/repairs/rollback`, `/services/*/baseline`, `/webhooks/subscriptions`, `/mcp/tools/call`) are protected. Public monitoring and proxy endpoints remain accessible.
2. **Fail-Safe Mode**: If `ENVIRONMENT=production`, the server fails safely (401) on protected operations if no API key is configured.
3. **SSRF & DNS Rebinding Protection**: Webhook destinations cannot target loopback (`127.0.0.0/8`), private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local metadata (`169.254.169.254`), or broadcast ranges. HTTP client enforces `follow_redirects=False`.
4. **Secret Redaction**: Webhook secrets are never returned in subscription listings (`GET /api/v1/webhooks/subscriptions`).
5. **Exact Adapter Hash Binding**: When an adapter is validated, its canonical SHA-256 hash is computed and stored. Activation recomputes the requested adapter's hash and rejects activation if it differs from the validated adapter, preventing adapter tampering between validation and activation.

---

## Test Suite Execution

```bash
# 1. Run backend tests (133 tests)
cd backend && uv run pytest -q

# 2. Run AI engine tests (78 tests)
cd ../ai_engine && uv run pytest -q

# 3. Compile checks across both projects
cd .. && uv run python -m compileall -q backend/app ai_engine
```

**Total automated tests:** **211 passed** (133 backend + 78 AI engine).
