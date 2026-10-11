from datetime import datetime, timezone
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.auth import (
    AuthenticatedUser,
    get_current_user,
    get_optional_current_user,
    verify_supabase_token,
    SUPABASE_URL,
    SUPABASE_JWT_SECRET,
)
from app.auth_schemas import (
    AuthHealthResponse,
    TokenVerifyRequest,
    TokenVerifyResponse,
    UserProfileResponse,
)

from app.ai_adapter import AIAdapter
from app.ai_adapter import analyze_changes as analyze_with_adapter
from app.change_analyzer import analyze_changes
from app.change_detector import detect_changes
from app.health_monitor import APIHealthMonitor
from app.integration_schemas import ChangeAnalysisRequest, ChangeAnalysisResponse
from app.mock_apis import (
    SimulatedAPIError,
    call_weather_api,
    get_weather_response,
)
from app.observer import APIObserver
from app.resilience import call_with_retry


# Import the AI engine
PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_ENGINE_PATH = PROJECT_ROOT / "ai_engine"

if str(AI_ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(AI_ENGINE_PATH))

from change_workflow import run_change_workflow
from repair_validator import validate_repair

from app.dependency_graph import create_default_dependency_graph
from app.mcp_server import call_mcp_tool, list_mcp_tools
from app.provider_client import (
    ProviderConnectionError,
    ProviderResponseError,
    ProviderTimeoutError,
    weather_provider_client,
)
from app.storage import storage_registry
from app.webhooks import webhook_manager


# Request models
class AIAnalyzeRequest(BaseModel):
    baseline: dict[str, Any]
    current: dict[str, Any]
    service_id: str | None = None
    include_impact: bool = False
    behavior_report: dict[str, Any] | None = None
    text_diff: list[dict[str, str]] | None = None
    pagination_reports: list[dict[str, Any]] | None = None
    rate_limit_reports: list[dict[str, Any]] | None = None
    retry_timing_reports: list[dict[str, Any]] | None = None
    run_behavior_tests: bool = False
    create_incident_on_change: bool = False


class BaselineSaveRequest(BaseModel):
    data: dict[str, Any]
    description: str = ""


class ServiceRegisterRequest(BaseModel):
    name: str
    base_url: str = ""
    description: str = ""
    is_critical: bool = False


class RepairValidationRequest(BaseModel):
    incident_id: str
    adapter: dict[str, Any]
    test_cases: list[dict[str, Any]]


class RepairActivationRequest(BaseModel):
    incident_id: str
    adapter: dict[str, Any]
    authorizer: str = "human_operator"
    note: str = ""


class RepairRollbackRequest(BaseModel):
    service_id: str
    authorizer: str = "human_operator"
    reason: str = ""


class WebhookSubscriptionRequest(BaseModel):
    target_url: str
    events: list[str] = ["*"]
    secret: str | None = None
    description: str = ""


class MCPToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


app = FastAPI(
    title="KintsuTech",
    description="API change detection and resilience monitoring.",
    version="0.1.0",
)

ai_adapter = AIAdapter(run_change_workflow)

FRONTEND_ORIGINS = os.environ.get(
    "FRONTEND_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
)
allowed_origins = [origin.strip() for origin in FRONTEND_ORIGINS.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

observer = APIObserver()
health_monitor = APIHealthMonitor()
dependency_graph = create_default_dependency_graph()

# Seed weather service and baseline in storage registry idempotently
storage_registry.register_service(
    "weather",
    name="Mock Weather Service",
    base_url="http://127.0.0.1:8000/api/v1/mock/weather",
    description="Simulated third-party weather API",
)
if not storage_registry.get_latest_baseline("weather"):
    storage_registry.save_baseline(
        "weather",
        get_weather_response(1),
        description="Initial known-good Weather v1 baseline",
    )


@app.get("/api/v1/health")
def health_check():
    return {
        "status": "ok",
        "service": "KintsuTech",
        "version": "0.1.0",
        "environment": os.environ.get("ENVIRONMENT", "development"),
    }


@app.get("/api/v1/health/readiness")
def readiness_check():
    """Verify backend storage, dependency graph, and observer readiness."""
    services = storage_registry.list_services()
    graph_info = dependency_graph.to_dict()
    return {
        "status": "ready",
        "service": "KintsuTech",
        "storage_ready": True,
        "services_registered": len(services),
        "dependency_nodes": graph_info["node_count"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/mock/weather")
def mock_weather(
    version: int = 1,
    schema: str | None = None,
    mode: str | None = None,
):
    """Raw mock third-party weather API endpoint."""
    if mode:
        try:
            return call_weather_api(mode=mode)
        except SimulatedAPIError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except ConnectionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        data = get_weather_response(version=version)
        if schema in ("temp_c", "v2_renamed"):
            temp_val = data.pop("temperature")
            data["temp_c"] = temp_val
        return data
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/proxy/weather")
def proxy_weather(
    version: int = 1,
    schema: str | None = None,
    mode: str | None = None,
):
    """
    Consumer-facing resilient weather proxy endpoint.
    1. Requests current response from mock or configured provider.
    2. Retrieves active adapter for the weather service.
    3. Automatically applies the adapter if one is active.
    4. Returns provider response unchanged if no adapter is active.
    5. Reports adaptation outcome and responsible incident ID.
    """
    params: dict[str, Any] = {"version": version}
    if schema:
        params["schema"] = schema
    if mode:
        params["mode"] = mode

    try:
        provider_data = weather_provider_client.fetch_weather(params=params)
    except ProviderTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (ProviderConnectionError, ProviderResponseError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unexpected provider error: {str(exc)}") from exc

    service = storage_registry.get_service("weather")
    active_adapter = service.get("active_adapter") if service else None

    if not active_adapter:
        return {
            "status": "unchanged",
            "adapted": False,
            "incident_id": None,
            "data": provider_data,
            "source": "provider",
        }

    adapter_config = active_adapter.get("adapter_config", {})
    adapted_data = apply_compatibility_adapter(provider_data, adapter_config)

    return {
        "status": "adapted",
        "adapted": True,
        "incident_id": active_adapter.get("incident_id"),
        "data": adapted_data,
        "source": "provider",
    }


def apply_compatibility_adapter(
    response: dict[str, Any],
    adapter_config: dict[str, Any],
) -> dict[str, Any]:
    """Apply a supported field-copy adapter without mutating the input."""
    if adapter_config.get("operation") != "copy_field":
        raise HTTPException(
            status_code=400,
            detail="Unsupported adapter operation.",
        )

    source_field = adapter_config.get("source_field")
    target_field = adapter_config.get("target_field")

    if not isinstance(source_field, str) or not source_field:
        raise HTTPException(status_code=400, detail="Invalid source_field.")

    if not isinstance(target_field, str) or not target_field:
        raise HTTPException(status_code=400, detail="Invalid target_field.")

    if source_field not in response:
        raise HTTPException(
            status_code=422,
            detail=f"Adapter source field '{source_field}' is missing.",
        )

    if target_field in response and target_field != source_field:
        raise HTTPException(
            status_code=409,
            detail=f"Adapter target field '{target_field}' already exists.",
        )

    adapted = dict(response)
    adapted[target_field] = adapted[source_field]
    return adapted


@app.post("/api/v1/compatible/weather")
def compatible_weather(response: dict[str, Any]):
    """Apply the active weather compatibility adapter to a supplied response."""
    service = storage_registry.get_service("weather")
    active_adapter = service.get("active_adapter") if service else None

    if not active_adapter:
        return {
            "status": "unchanged",
            "data": response,
            "reason": "No active compatibility adapter.",
        }

    adapter_config = active_adapter.get("adapter_config", {})
    adapted = apply_compatibility_adapter(response, adapter_config)

    return {
        "status": "adapted",
        "incident_id": active_adapter.get("incident_id"),
        "data": adapted,
    }


@app.post("/api/v1/observe/weather")
def observe_weather(version: int = 1):
    try:
        response = get_weather_response(version=version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    observation = observer.capture("weather", response)
    return {"observation": observation}


@app.post("/api/v1/observe/weather/reset")
def reset_weather_observation():
    baseline = get_weather_response(version=1)
    observer.update_baseline("weather", baseline)

    return {
        "status": "success",
        "message": "Weather baseline reset to version 1.",
        "baseline": baseline,
    }


@app.get("/api/v1/resilience/weather")
def resilient_weather(mode: str = "success", max_attempts: int = 3):
    start_time = time.perf_counter()

    try:
        response = call_with_retry(
            lambda: call_weather_api(mode),
            max_attempts=max_attempts,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        health_monitor.record_success("weather", elapsed_ms)

        return {
            "status": "success",
            "attempt_limit": max_attempts,
            "data": response,
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except (TimeoutError, ConnectionError, SimulatedAPIError) as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        health_monitor.record_failure("weather", elapsed_ms, str(exc))

        raise HTTPException(
            status_code=503,
            detail=f"Weather API failed after retries: {exc}",
        ) from exc


@app.get("/api/v1/monitor/health")
def get_weather_health():
    return health_monitor.get_service_health("weather")


@app.get("/api/v1/monitor/incidents")
def get_weather_incidents():
    incidents = health_monitor.get_recent_incidents()

    return {
        "service": "weather",
        "incident_count": len(incidents),
        "incidents": incidents,
    }


@app.post("/api/v1/analyze/changes")
def analyze_api_changes(
    baseline: dict[str, Any],
    current: dict[str, Any],
):
    detection_result = detect_changes(baseline, current)
    return analyze_changes(detection_result)


@app.post("/api/v1/analyze/changes/ai")
def analyze_api_changes_with_ai(
    baseline: dict[str, Any],
    current: dict[str, Any],
):
    """Analyze API changes using the AI adapter."""
    try:
        detection_result = detect_changes(baseline, current)

        return analyze_with_adapter(
            service="weather",
            baseline=baseline,
            current=current,
            detected_changes=detection_result,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="AI change analysis is temporarily unavailable.",
        ) from exc


@app.post(
    "/api/v1/integrations/change-analysis",
    response_model=ChangeAnalysisResponse,
)
def integration_change_analysis(
    request: ChangeAnalysisRequest,
) -> ChangeAnalysisResponse:
    detection = detect_changes(request.baseline, request.current)
    analysis = analyze_changes(detection)

    return ChangeAnalysisResponse(
        service=request.service,
        has_changes=analysis["has_changes"],
        overall_risk=analysis["overall_risk"],
        change_count=analysis["change_count"],
        severity_counts=analysis["severity_counts"],
        changes=analysis["changes"],
    )


@app.post("/api/v1/ai/analyze")
def analyze_with_ai(payload: AIAnalyzeRequest):
    """Run unified API change detection and the gated repair workflow."""
    try:
        kwargs: dict[str, Any] = {
            "baseline": payload.baseline,
            "current": payload.current,
            "behavior_report": payload.behavior_report,
            "text_diff": payload.text_diff,
            "pagination_reports": payload.pagination_reports,
            "rate_limit_reports": payload.rate_limit_reports,
            "run_behavior_tests": payload.run_behavior_tests,
        }
        if payload.retry_timing_reports is not None:
            kwargs["retry_timing_reports"] = payload.retry_timing_reports

        result = run_change_workflow(**kwargs)

        if payload.include_impact or payload.service_id:
            service_id = payload.service_id or "weather"
            impact = dependency_graph.calculate_impact(service_id)
            result["impact_analysis"] = impact

            if payload.create_incident_on_change and result.get("change_report", {}).get("has_changes"):
                repair_wf = result.get("repair_workflow", {})
                change_rep = result.get("change_report", {})
                inc = storage_registry.create_incident(
                    service_id=service_id,
                    title=f"API change detected in {service_id}",
                    severity=impact.get("impact_level", "medium"),
                    differences=change_rep.get("changes", []),
                    evidence=change_rep.get("evidence", {}),
                    impact=impact,
                    repair_proposal=repair_wf.get("proposal") if isinstance(repair_wf, dict) else None,
                )
                result["incident_id"] = inc["id"]

        return result
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="AI analysis is temporarily unavailable.",
        ) from exc


# Service Registry & Baselines


@app.get("/api/v1/services")
def list_services():
    """List all registered services, version counts, and active adapters."""
    return {"services": storage_registry.list_services()}


@app.post("/api/v1/services/{service_id}")
def register_service(service_id: str, payload: ServiceRegisterRequest):
    """Register or update a monitored service."""
    try:
        service = storage_registry.register_service(
            service_id,
            name=payload.name,
            base_url=payload.base_url,
            description=payload.description,
            is_critical=payload.is_critical,
        )
        return {"status": "registered", "service": service}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/services/{service_id}")
def get_service_details(service_id: str):
    """Get metadata and current baseline version for a service."""
    service = storage_registry.get_service(service_id)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service '{service_id}' not found.")
    return {"service": service}


@app.get("/api/v1/services/{service_id}/baseline")
def get_service_baseline(service_id: str):
    """Retrieve the latest baseline response for a service."""
    baseline = storage_registry.get_latest_baseline(service_id)
    if not baseline:
        raise HTTPException(
            status_code=404,
            detail=f"No baseline found for service '{service_id}'.",
        )
    return {"baseline": baseline}


@app.post("/api/v1/services/{service_id}/baseline")
def save_service_baseline(service_id: str, payload: BaselineSaveRequest):
    """Save a new versioned baseline for a service."""
    try:
        record = storage_registry.save_baseline(
            service_id,
            payload.data,
            description=payload.description,
        )
        return {"status": "saved", "baseline": record}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Dependency Graph & Downstream Blast Radius (NetworkX)


@app.get("/api/v1/services/{service_id}/dependencies")
def get_service_dependencies(service_id: str):
    """Calculate blast radius and downstream dependents for a service change."""
    impact = dependency_graph.calculate_impact(service_id)
    return {"service_id": service_id, "impact": impact}


@app.get("/api/v1/dependencies/graph")
def get_dependency_graph():
    """Retrieve complete service dependency graph topology."""
    return {"dependency_graph": dependency_graph.to_dict()}


# Incidents & Evidence


@app.get("/api/v1/incidents")
def list_incidents(
    service_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    """List recorded incidents with optional filters."""
    incidents = storage_registry.list_incidents(
        service_id=service_id,
        status=status,
    )
    return {"incident_count": len(incidents), "incidents": incidents}


@app.get("/api/v1/incidents/{incident_id}")
def get_incident_by_id(incident_id: str):
    """Get full incident record including evidence, impact, and repair proposals."""
    incident = storage_registry.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found.")
    return {"incident": incident}


# Repair Validation, Guarded Activation & Rollback


@app.post("/api/v1/repairs/validate")
def validate_repair_proposal(payload: RepairValidationRequest):
    """
    Deterministically validate a proposed compatibility adapter using test cases.
    Does NOT activate the repair.
    """
    try:
        validation_result = validate_repair(payload.adapter, payload.test_cases)
        storage_registry.record_validation(payload.incident_id, validation_result)
        return {
            "incident_id": payload.incident_id,
            "validation": validation_result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ============================================================================
# Supabase Authentication Endpoints
# ============================================================================


@app.get("/api/v1/auth/health", response_model=AuthHealthResponse)
def get_auth_health():
    """Report backend Supabase authentication status and configuration without leaking secrets."""
    return AuthHealthResponse(
        status="healthy",
        auth_provider="supabase",
        supabase_configured=bool(SUPABASE_URL),
        jwks_enabled=bool(SUPABASE_URL),
        jwt_secret_configured=bool(SUPABASE_JWT_SECRET),
        protected_endpoints=[
            "/api/v1/auth/me",
            "/api/v1/repairs/activate",
            "/api/v1/repairs/rollback",
        ],
    )


@app.get("/api/v1/auth/me", response_model=UserProfileResponse)
def get_current_user_profile(current_user: AuthenticatedUser = Depends(get_current_user)):
    """
    Retrieve verified profile of the currently authenticated Supabase user
    and automatically save/update the user record in the local SQLite database.
    """
    storage_registry.sync_user(
        user_id=current_user.id,
        email=current_user.email,
        full_name=current_user.user_metadata.get("full_name") or current_user.display_name,
        role=current_user.role,
        user_metadata=current_user.user_metadata,
    )
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        phone=current_user.phone,
        role=current_user.role,
        display_name=current_user.display_name,
        user_metadata=current_user.user_metadata,
        app_metadata=current_user.app_metadata,
    )


@app.post("/api/v1/auth/verify", response_model=TokenVerifyResponse)
def verify_token_endpoint(
    request: Request,
    payload: TokenVerifyRequest | None = None,
):
    """
    Verify the supplied Supabase access token (via Bearer header or request body),
    save user identity into local SQLite database, and return safe identity information.
    Rejects missing, expired, or invalid tokens with HTTP 401.
    """
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    elif payload and payload.token:
        token = payload.token

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing access token in Authorization header or body.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = verify_supabase_token(token)
    storage_registry.sync_user(
        user_id=user.id,
        email=user.email,
        full_name=user.user_metadata.get("full_name") or user.display_name,
        role=user.role,
        user_metadata=user.user_metadata,
    )
    return TokenVerifyResponse(
        valid=True,
        user=UserProfileResponse(
            id=user.id,
            email=user.email,
            phone=user.phone,
            role=user.role,
            display_name=user.display_name,
            user_metadata=user.user_metadata,
            app_metadata=user.app_metadata,
        ),
        error=None,
    )


class UserProfileSyncRequest(BaseModel):
    full_name: str | None = None
    email: str | None = None
    metadata: dict[str, Any] | None = None


@app.post("/api/v1/auth/sync", response_model=UserProfileResponse)
def sync_user_profile(
    payload: UserProfileSyncRequest | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Explicit endpoint for frontend to persist or update signup/login user fields into SQLite database.
    """
    meta = dict(current_user.user_metadata)
    if payload and payload.metadata:
        meta.update(payload.metadata)

    full_name = (
        (payload.full_name if payload and payload.full_name else None)
        or current_user.user_metadata.get("full_name")
        or current_user.display_name
    )
    email = (payload.email if payload and payload.email else None) or current_user.email

    saved_user = storage_registry.sync_user(
        user_id=current_user.id,
        email=email,
        full_name=full_name,
        role=current_user.role,
        user_metadata=meta,
    )

    return UserProfileResponse(
        id=saved_user["id"],
        email=saved_user["email"],
        phone=current_user.phone,
        role=saved_user["role"],
        display_name=saved_user["full_name"] or current_user.display_name,
        user_metadata=saved_user["user_metadata"],
        app_metadata=current_user.app_metadata,
    )


@app.get("/api/v1/users")
def list_local_users():
    """List all registered users stored in the local SQLite database."""
    return {"users": storage_registry.list_users()}


@app.post("/api/v1/auth/logout")
def logout_endpoint(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Backend logout verification endpoint.
    Note: Supabase access tokens are stateless JWTs.
    Client-side session termination is performed by calling supabase.auth.signOut(),
    which deletes the local session and revokes the refresh token on the Supabase Auth server.
    """
    return {
        "status": "logged_out",
        "message": "Session terminated on client. Refresh token revoked via Supabase Auth.",
        "user_id": current_user.id,
    }




@app.post("/api/v1/repairs/activate")
def activate_repair(
    payload: RepairActivationRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Guarded repair activation.
    Rejected if caller is unauthenticated or the proposal has not passed independent validation.
    """
    try:
        authorizer = payload.authorizer or current_user.display_name or current_user.email or current_user.id
        activation = storage_registry.activate_repair(
            payload.incident_id,
            payload.adapter,
            authorizer=authorizer,
            note=payload.note,
        )

        # Notify subscribers
        event = webhook_manager.create_event(
            "repair.activated",
            activation,
            service_id=activation.get("service_id", "kintsutech"),
        )
        webhook_manager.dispatch_event(event)

        return {
            "status": "activated",
            "activation": activation,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/repairs/rollback")
def rollback_repair(
    payload: RepairRollbackRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Deactivate active adapter and restore service to un-adapted baseline state.
    """
    try:
        authorizer = payload.authorizer or current_user.display_name or current_user.email or current_user.id
        rollback = storage_registry.rollback_repair(
            payload.service_id,
            authorizer=authorizer,
            reason=payload.reason,
        )

        event = webhook_manager.create_event(
            "repair.rollback_completed",
            rollback,
            service_id=payload.service_id,
        )
        webhook_manager.dispatch_event(event)

        return {
            "status": "rolled_back",
            "rollback": rollback,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/api/v1/repairs/audit")
def get_repair_audit_log():
    """Retrieve audit trail of all repair validations, activations, and rollbacks."""
    return {"audit_log": storage_registry.get_audit_log()}


# Webhooks (Incoming Receiver & Outgoing Subscriptions)


@app.post("/api/v1/webhooks/incoming")
async def receive_incoming_webhook(request: Request):
    """
    Receive incoming webhooks with HMAC-SHA256 signature verification,
    timestamp freshness check, and idempotency deduplication.
    """
    body = await request.body()
    signature = request.headers.get("X-KintsuTech-Signature")
    timestamp = request.headers.get("X-Timestamp")

    # Verify signature
    if not webhook_manager.verify_signature(body, signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing webhook signature.",
        )

    # Verify timestamp freshness if provided
    if timestamp and not webhook_manager.verify_timestamp(timestamp):
        raise HTTPException(
            status_code=400,
            detail="Webhook timestamp expired or invalid.",
        )

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

    event_id = payload.get("id") or payload.get("event_id")
    if event_id and webhook_manager.is_duplicate_event(str(event_id)):
        return {
            "status": "duplicate_ignored",
            "event_id": event_id,
        }

    return {
        "status": "accepted",
        "event_id": event_id,
        "event_type": payload.get("type", "unknown"),
    }


@app.post("/api/v1/webhooks/subscriptions")
def create_webhook_subscription(payload: WebhookSubscriptionRequest):
    """Register an outgoing webhook destination."""
    try:
        subscription = webhook_manager.subscribe(
            target_url=payload.target_url,
            events=payload.events,
            secret=payload.secret,
            description=payload.description,
        )
        return {"status": "subscribed", "subscription": subscription}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/webhooks/subscriptions")
def list_webhook_subscriptions():
    """List active outgoing webhook subscriptions."""
    return {"subscriptions": webhook_manager.list_subscriptions()}


@app.get("/api/v1/webhooks/deliveries")
def get_webhook_deliveries():
    """Retrieve outgoing webhook delivery logs and retry records."""
    return {"deliveries": webhook_manager.get_delivery_logs()}


# Model Context Protocol (MCP) Endpoints


@app.get("/api/v1/mcp/tools")
def get_mcp_tools():
    """Expose MCP tool catalog for AI client tool-discovery."""
    return {"tools": list_mcp_tools()}


@app.post("/api/v1/mcp/tools/call")
def execute_mcp_tool(payload: MCPToolCallRequest):
    """Execute an MCP tool request against the backend services."""
    result = call_mcp_tool(payload.name, payload.arguments)
    if "error" in result and result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return {"tool": payload.name, "result": result}

