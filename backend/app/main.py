from collections import deque
import asyncio
import tempfile
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
import logging
import platform

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
# Load environment variables from .env
load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.security import validate_production_config, verify_api_key
from app.rate_limiter import rate_limit_mutations, rate_limit_webhooks

from app.auth import (
    AuthenticatedUser,
    CallerIdentity,
    authenticate_caller,
    get_current_user,
    get_optional_current_user,
    require_admin_or_api_key,
    require_authenticated_caller,
    require_repair_operator,
    resolve_repair_authorizer,
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
from consumer_contracts import contract_registry
from repair_validator import validate_repair

from app.dependency_graph import create_default_dependency_graph
from app.mcp_server import (
    call_mcp_tool,
    list_mcp_tools,
    mcp_server,
    mcp_streamable_app,
)
from app.provider_client import (
    ProviderConnectionError,
    ProviderResponseError,
    ProviderTimeoutError,
    weather_provider_client,
)
from app.storage import storage_registry
from app.webhooks import webhook_manager
from app.agent import AgentChatRequest, AgentChatResponse, AgentEngine


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
    consumer_contracts: list[dict[str, Any]] | None = None
    service_id: str | None = None
    required_consumers: list[str] | None = None


class RepairActivationRequest(BaseModel):
    incident_id: str
    adapter: dict[str, Any]
    authorizer: str = "human_operator"
    note: str = ""
    contract_version: str | None = None


class ConsumerContractRequest(BaseModel):
    consumer_id: str
    service_id: str
    version: str = "1.0"
    mandatory: bool = True
    fields: dict[str, Any]
    description: str = ""


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Fail-closed production configuration validation
    validate_production_config()

    # 2. Startup MCP server session manager
    mcp_cm = None
    if hasattr(mcp_server, "session_manager") and mcp_server.session_manager:
        mcp_server.session_manager._has_started = False
        mcp_cm = mcp_server.session_manager.run()
        await mcp_cm.__aenter__()

    try:
        yield
    finally:
        # 3. Graceful shutdown of MCP session manager
        if mcp_cm:
            try:
                await mcp_cm.__aexit__(None, None, None)
            except Exception:
                pass
            if hasattr(mcp_server, "session_manager") and mcp_server.session_manager:
                mcp_server.session_manager._has_started = False

        # 4. Graceful shutdown of background webhook workers
        try:
            webhook_manager.shutdown(wait=False)
        except Exception:
            pass

        # 5. Dispose database engine
        try:
            storage_registry.close()
        except Exception:
            pass


class BoundedBodyLimitMiddleware:
    """
    Pure ASGI middleware enforcing MAX_REQUEST_BODY_SIZE.
    Protects both standard Content-Length requests and streaming/chunked requests
    without a trustworthy Content-Length header, avoiding unbounded memory buffering.
    Compatible with FastAPI and mounted MCP Streamable HTTP transport.
    """

    def __init__(self, app: ASGIApp, default_max_size: int = 1048576) -> None:
        self.app = app
        self.default_max_size = default_max_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            if scope.get("path") == "/api/v1/agent/transcribe":
                max_size = int(os.environ.get("MAX_AUDIO_REQUEST_BODY_SIZE", "8388608"))
            else:
                max_size = int(os.environ.get("MAX_REQUEST_BODY_SIZE", str(self.default_max_size)))
        except ValueError:
            max_size = self.default_max_size

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
                if declared_size > max_size:
                    resp = JSONResponse(
                        status_code=413,
                        content={
                            "detail": f"Request entity too large ({declared_size} bytes exceeds limit of {max_size} bytes)."
                        },
                    )
                    return await resp(scope, receive, send)
            except ValueError:
                resp = JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})
                return await resp(scope, receive, send)

        received_body = bytearray()
        received_request = False
        body_complete = False
        trailing_message: Message | None = None

        while True:
            message = await receive()
            if message["type"] != "http.request":
                trailing_message = message
                break

            received_request = True
            body = message.get("body", b"")
            if len(received_body) + len(body) > max_size:
                resp = JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Request entity too large ({len(received_body) + len(body)} bytes exceeds limit of {max_size} bytes)."
                    },
                )
                return await resp(scope, receive, send)

            received_body.extend(body)
            if not message.get("more_body", False):
                body_complete = True
                break

        cached_messages: deque[Message] = deque()
        if received_request:
            cached_messages.append(
                {"type": "http.request", "body": bytes(received_body), "more_body": not body_complete}
            )
        if trailing_message is not None:
            cached_messages.append(trailing_message)

        async def replay() -> Message:
            if cached_messages:
                return cached_messages.popleft()
            return await receive()

        await self.app(scope, replay, send)


app = FastAPI(
    title="KintsuTech",
    description="API change detection and resilience monitoring.",
    version="0.1.0",
    lifespan=lifespan,
)

# Genuine Model Context Protocol (MCP) Streamable HTTP transport
app.mount("/mcp", mcp_streamable_app)
app.mount("/api/v1/mcp/stream", mcp_streamable_app)

ai_adapter = AIAdapter(run_change_workflow)

FRONTEND_ORIGINS = os.environ.get(
    "FRONTEND_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
)
allowed_origins = [origin.strip() for origin in FRONTEND_ORIGINS.split(",") if origin.strip()]

MAX_REQUEST_BODY_SIZE = int(os.environ.get("MAX_REQUEST_BODY_SIZE", "1048576"))  # default 1MB

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(BoundedBodyLimitMiddleware, default_max_size=MAX_REQUEST_BODY_SIZE)

observer = APIObserver()
health_monitor = APIHealthMonitor()
dependency_graph = create_default_dependency_graph()
agent_engine = AgentEngine(health_monitor=health_monitor)

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
    """Apply a supported compatibility adapter (copy_field or convert_units) without mutating input."""
    operation = adapter_config.get("operation")
    if operation not in ("copy_field", "convert_units"):
        raise HTTPException(
            status_code=400,
            detail="Unsupported adapter operation.",
        )

    try:
        from repair_validator import apply_compatibility_adapter as ai_apply_adapter
        return ai_apply_adapter(response, adapter_config=adapter_config)
    except ValueError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        if "is missing" in msg or "cannot be null" in msg or "must be a finite number" in msg or "below required" in msg or "exceeds required" in msg:
            raise HTTPException(status_code=422, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc


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

                # Dispatch incident.created webhook event
                event = webhook_manager.create_event(
                    "incident.created",
                    inc,
                    service_id=service_id,
                )
                webhook_manager.dispatch_event_background(event)

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


@app.post(
    "/api/v1/services/{service_id}",
    dependencies=[Depends(rate_limit_mutations)],
)
def register_service(
    service_id: str,
    payload: ServiceRegisterRequest,
    caller: CallerIdentity = Depends(require_admin_or_api_key),
):
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


@app.post(
    "/api/v1/services/{service_id}/baseline",
    dependencies=[Depends(rate_limit_mutations)],
)
def save_service_baseline(
    service_id: str,
    payload: BaselineSaveRequest,
    caller: CallerIdentity = Depends(require_admin_or_api_key),
):
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


@app.post(
    "/api/v1/repairs/validate",
    dependencies=[Depends(rate_limit_mutations)],
)
def validate_repair_proposal(payload: RepairValidationRequest):
    """
    Deterministically validate a proposed compatibility adapter using test cases
    and downstream consumer contracts.
    Does NOT activate the repair.
    """
    try:
        service_id = payload.service_id
        if not service_id:
            inc = storage_registry.get_incident(payload.incident_id)
            if inc:
                service_id = inc.get("service_id")

        validation_result = validate_repair(
            payload.adapter,
            payload.test_cases,
            consumer_contracts=payload.consumer_contracts,
            service_id=service_id,
            required_consumers=payload.required_consumers,
        )
        storage_registry.record_validation(
            payload.incident_id,
            validation_result,
            adapter_config=payload.adapter,
            contract_version=validation_result.get("contract_version"),
        )

        # Dispatch repair.validated webhook event upon successful validation
        if validation_result.get("eligible_for_activation") or validation_result.get("passed"):
            effective_service_id = service_id or "kintsutech"
            event = webhook_manager.create_event(
                "repair.validated",
                {
                    "incident_id": payload.incident_id,
                    "validation": validation_result,
                    "adapter": payload.adapter,
                    "contract_version": validation_result.get("contract_version"),
                },
                service_id=effective_service_id,
            )
            webhook_manager.dispatch_event_background(event)

        return {
            "incident_id": payload.incident_id,
            "validation": validation_result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Supabase Authentication Endpoints


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
            "/api/v1/auth/sync",
            "/api/v1/users",
            "/api/v1/repairs/activate",
            "/api/v1/repairs/rollback",
            "/api/v1/repairs/audit",
            "/api/v1/webhooks/deliveries",
            "/api/v1/webhooks/subscriptions",
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
    Prefers 'Authorization: Bearer <token>' header for frontend calls.
    Raw tokens are never logged or persisted.
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
    # Clear local token reference
    del token

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
def list_local_users(
    caller: CallerIdentity = Depends(require_admin_or_api_key),
):
    """
    List all registered users stored in the local SQLite database.
    Restricted to administrators, owners, or server-to-server integrations to prevent account enumeration.
    """
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




@app.post(
    "/api/v1/repairs/activate",
    dependencies=[Depends(rate_limit_mutations)],
)
def activate_repair(
    payload: RepairActivationRequest,
    caller: CallerIdentity = Depends(authenticate_caller),
):
    """
    Guarded repair activation.
    Rejected if proposal has not passed independent validation, adapter hash mismatch,
    or contract version mismatch.
    Requires explicit authorization via server API key or verified Supabase operator token.
    Client-supplied authorizer is ignored for authenticated user sessions in favor of verified claims.
    """
    authorizer = resolve_repair_authorizer(caller, payload)
    try:
        activation = storage_registry.activate_repair(
            payload.incident_id,
            payload.adapter,
            authorizer=authorizer,
            note=payload.note,
            contract_version=payload.contract_version,
        )

        # Notify subscribers asynchronously in background
        event = webhook_manager.create_event(
            "repair.activated",
            activation,
            service_id=activation.get("service_id", "kintsutech"),
        )
        webhook_manager.dispatch_event_background(event)

        return {
            "status": "activated",
            "activation": activation,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/contracts")
def list_consumer_contracts(service_id: str | None = Query(default=None)):
    """List registered downstream consumer contracts."""
    if service_id:
        return {"contracts": contract_registry.get_for_service(service_id)}
    return {"contracts": contract_registry.list_all()}


@app.post(
    "/api/v1/contracts",
    dependencies=[Depends(rate_limit_mutations)],
)
def register_consumer_contract(
    payload: ConsumerContractRequest,
    caller: CallerIdentity = Depends(require_admin_or_api_key),
):
    """Register or update a downstream consumer contract."""
    try:
        contract = contract_registry.register(payload.model_dump())
        return {"status": "registered", "contract": contract}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/v1/repairs/rollback",
    dependencies=[Depends(rate_limit_mutations)],
)
def rollback_repair(
    payload: RepairRollbackRequest,
    caller: CallerIdentity = Depends(authenticate_caller),
):
    """
    Deactivate active adapter and restore service to un-adapted baseline state.
    Requires explicit authorization via server API key or verified Supabase operator token.
    Client-supplied authorizer is ignored for authenticated user sessions in favor of verified claims.
    """
    authorizer = resolve_repair_authorizer(caller, payload)
    try:
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
        webhook_manager.dispatch_event_background(event)

        return {
            "status": "rolled_back",
            "rollback": rollback,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/api/v1/repairs/audit")
def get_repair_audit_log(
    caller: CallerIdentity = Depends(require_authenticated_caller),
):
    """Retrieve audit trail of all repair validations, activations, and rollbacks."""
    return {"audit_log": storage_registry.get_audit_log()}


# Webhooks (Incoming Receiver & Outgoing Subscriptions)


@app.post(
    "/api/v1/webhooks/incoming",
    dependencies=[Depends(rate_limit_webhooks)],
)
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


@app.post(
    "/api/v1/webhooks/subscriptions",
    dependencies=[Depends(rate_limit_mutations)],
)
def create_webhook_subscription(
    payload: WebhookSubscriptionRequest,
    caller: CallerIdentity = Depends(require_admin_or_api_key),
):
    """Register an outgoing webhook destination."""
    try:
        subscription = webhook_manager.subscribe(
            target_url=payload.target_url,
            events=payload.events,
            secret=payload.secret,
            description=payload.description,
        )
        # Ensure secret is never returned in response
        sanitized_sub = dict(subscription)
        sanitized_sub.pop("secret", None)
        sanitized_sub["secret_configured"] = bool(subscription.get("secret_configured") or payload.secret)
        return {"status": "subscribed", "subscription": sanitized_sub}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/webhooks/subscriptions")
def list_webhook_subscriptions(
    caller: CallerIdentity = Depends(require_admin_or_api_key),
):
    """List active outgoing webhook subscriptions with secrets redacted."""
    return {"subscriptions": webhook_manager.list_subscriptions()}


@app.get("/api/v1/webhooks/subscriptions/{subscription_id}")
def get_webhook_subscription(
    subscription_id: str,
    caller: CallerIdentity = Depends(require_admin_or_api_key),
):
    """Get a specific webhook subscription with secret redacted."""
    sub = storage_registry.get_webhook_subscription(subscription_id, include_secret=False)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Subscription '{subscription_id}' not found.")
    return {"subscription": sub}


@app.get("/api/v1/webhooks/deliveries")
def get_webhook_deliveries(
    caller: CallerIdentity = Depends(require_authenticated_caller),
):
    """Retrieve outgoing webhook delivery logs and retry records."""
    return {"deliveries": webhook_manager.get_delivery_logs()}


# Model Context Protocol (MCP) Endpoints


@app.get("/api/v1/mcp/tools")
def get_mcp_tools():
    """Expose MCP tool catalog for AI client tool-discovery."""
    return {"tools": list_mcp_tools()}


@app.post(
    "/api/v1/mcp/tools/call",
    dependencies=[Depends(rate_limit_mutations)],
)
def execute_mcp_tool(
    payload: MCPToolCallRequest,
    request: Request,
    auth_user: str = Depends(verify_api_key),
):
    """Execute an MCP tool request against the backend services."""
    args = dict(payload.arguments) if payload.arguments else {}
    if "api_key" not in args:
        header_key = request.headers.get("X-API-Key")
        if not header_key:
            auth_hdr = request.headers.get("Authorization", "")
            if auth_hdr.startswith("Bearer "):
                header_key = auth_hdr[7:].strip()
        if header_key:
            args["api_key"] = header_key

    result = call_mcp_tool(payload.name, args)
    if "error" in result and result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return {"tool": payload.name, "result": result}



# Local-only speech transcription with MLX Whisper.
_WHISPER_LOCK = threading.Lock()
_MAX_AUDIO_FILE_BYTES = 7 * 1024 * 1024
_AUDIO_SUFFIXES = {
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/aac": ".aac",
}


class MLXWhisperUnavailableError(HTTPException):
    """Raised when runtime platform or MLX Whisper dependency is unsupported."""

    def __init__(
        self,
        detail: str = "Local voice transcription is unavailable: MLX Whisper requires macOS on Apple Silicon.",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )


def _check_mlx_whisper_support() -> None:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise MLXWhisperUnavailableError(
            "Local voice transcription is unavailable: MLX Whisper requires macOS on Apple Silicon."
        )
    try:
        import mlx_whisper  # noqa: F401
    except (ImportError, ModuleNotFoundError) as exc:
        logger.warning("MLX Whisper module could not be imported: %s", exc)
        raise MLXWhisperUnavailableError(
            "Local voice transcription is unavailable: MLX Whisper dependency is not installed."
        ) from exc


def _transcribe_local_audio(file_path: str) -> str:
    _check_mlx_whisper_support()

    import mlx_whisper

    model = os.environ.get(
        "KINTSUTECH_WHISPER_MODEL", "mlx-community/whisper-tiny"
    )
    language = os.environ.get("KINTSUTECH_WHISPER_LANGUAGE") or None

    with _WHISPER_LOCK:
        result = mlx_whisper.transcribe(
            file_path,
            path_or_hf_repo=model,
            language=language,
            verbose=False,
        )
    return str(result.get("text", "")).strip()


@app.post(
    "/api/v1/agent/transcribe",
    dependencies=[Depends(rate_limit_mutations)],
)
async def transcribe_agent_audio(
    file: UploadFile = File(...),
    current_user: AuthenticatedUser | None = Depends(get_optional_current_user),
):
    """Transcribe a short audio clip locally with MLX Whisper."""
    del current_user

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    suffix = _AUDIO_SUFFIXES.get(content_type)
    if suffix is None:
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported audio format.",
        )

    temp_path = None
    total_bytes = 0
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=suffix, prefix="kintsu-whisper-", delete=False
        ) as temp_file:
            temp_path = temp_file.name
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > _MAX_AUDIO_FILE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Audio file exceeds the 7 MB upload limit.",
                    )
                temp_file.write(chunk)

        if total_bytes == 0:
            raise HTTPException(
                status_code=400,
                detail="The audio file is empty.",
            )

        transcript = await asyncio.to_thread(_transcribe_local_audio, temp_path)
        if not transcript:
            raise HTTPException(
                status_code=422,
                detail="No speech could be recognized. Please try again.",
            )

        return {
            "text": transcript,
            "engine": "mlx-whisper",
            "local_processing": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Unexpected error during local audio transcription: %s", exc, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local transcription failed. Check backend logs and Whisper model.",
        ) from exc
    finally:
        await file.close()
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError as err:
                logger.warning(
                    "Failed to remove temporary audio file %s: %s", temp_path, err
                )


# Conversational AI Agent Endpoint


@app.post(
    "/api/v1/agent/chat",
    response_model=AgentChatResponse,
    dependencies=[Depends(rate_limit_mutations)],
)
def chat_with_agent(
    payload: AgentChatRequest,
    current_user: AuthenticatedUser | None = Depends(get_optional_current_user),
):
    """
    Conversational AI agent endpoint grounded in live KintsuTech backend tools and telemetry.
    Answers general queries and diagnoses API drift, consumer blast radius, and recovery proposals.
    """
    is_admin = current_user.is_admin if current_user else False
    user_id = current_user.id if current_user else "anonymous"
    return agent_engine.process_query(
        query=payload.message,
        caller_is_admin=is_admin,
        caller_id=user_id,
    )

