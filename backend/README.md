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

## 3. Configuration & Persistence

| Environment Variable | Default Value | Description |
|----------------------|---------------|-------------|
| `WEATHER_PROVIDER_URL` | `http://127.0.0.1:8000/api/v1/mock/weather` | Upstream target URL for the weather service |
| `KINTSUTECH_DATABASE_URL` | `sqlite:///backend/data/kintsutech.db` | SQLite persistence database location |
| `FRONTEND_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed CORS origins for frontend UI |

### Database Tables (SQLAlchemy 2.0)
- `services`: Registered monitored APIs and endpoints.
- `baselines`: Versioned baseline responses with SHA256 checksums.
- `incidents`: Monotonic, collision-free incidents (`INC-001`, `INC-002`, ...).
- `validations`: Deterministic regression test verification outcomes.
- `active_adapters`: Authorizer-guarded active repair adapters.
- `audit_log`: Append-only audit trail recording timestamps and actors.

---

## 4. Test Suite Execution

Run all test suites across the project:

```bash
# 1. Run backend tests (123 tests)
cd backend && uv run pytest -q

# 2. Run AI engine tests (78 tests)
cd ../ai_engine && uv run pytest -q

# 3. Compile checks across both projects
cd .. && uv run python -m compileall -q backend/app ai_engine
```

**Total automated tests:** **201 passed** (123 backend + 78 AI engine).

---

## 5. System Limitations & Safety Principles

1. **Deterministic Guardrails**: KintsuTech never promotes an AI-proposed adapter directly to production without passing deterministic test cases.
2. **Explicit Human Authorization**: Every activation and rollback requires an authenticated authorizer name and audit entry.
3. **Semantic Equivalence Guard**: Adapters currently support restricted, safe `copy_field` semantics. Field mappings cannot silently assume unit equivalence (e.g. Celsius vs Fahrenheit) without explicit reviewer confirmation.
4. **Controlled Upstream Proxy**: KintsuTech only adapts traffic explicitly routed through its proxy endpoints. It does not claim arbitrary network interception.
5. **Timeout Safety**: Upstream requests enforce 2.0s connect and 5.0s read timeouts, mapping to HTTP 504 and 502 rather than hanging worker processes.
