import os
from pathlib import Path
import json
import secrets
import sys
from typing import Any

# Ensure ai_engine is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_ENGINE_PATH = PROJECT_ROOT / "ai_engine"
if str(AI_ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(AI_ENGINE_PATH))

from app.ai_adapter import analyze_changes as analyze_with_ai_adapter
from app.change_analyzer import analyze_changes
from app.change_detector import detect_changes
from app.dependency_graph import create_default_dependency_graph
from app.security import (
    compute_adapter_hash,
    get_configured_api_key,
    is_auth_enforced,
)
from app.storage import storage_registry
from mcp.server.mcpserver import Context, MCPServer

# Initialize official MCPServer
mcp_server = MCPServer(
    name="kintsutech-mcp",
    version="0.1.0",
    instructions=(
        "KintsuTech MCP Server provides AI agents with tools to observe, analyze, "
        "and recover third-party API services, calculate dependency blast radiuses, "
        "validate compatibility repairs against consumer contracts, and safely activate or rollback repairs."
    ),
)

default_dep_graph = create_default_dependency_graph()


def check_mcp_authorization(
    ctx: Context | None = None,
    api_key_arg: str | None = None,
) -> tuple[bool, str | None]:
    """
    Verify API key for mutating MCP tool operations.
    Reuses the existing API-key security mechanism:
    - In remote HTTP transport (ctx.headers is present): requires valid API key in HTTP headers
      ('X-API-Key' or 'Authorization: Bearer <key>'). Does NOT rely on client-supplied tool arguments alone.
    - In local stdio or direct in-process calls (ctx is None or ctx.headers is None): uses api_key_arg.
    - Constant-time comparison ensures timing attack resistance.
    - Never echoes credentials in responses or logs.
    Returns (True, None) if authorized, or (False, error_message) if unauthorized.
    """
    if not is_auth_enforced():
        return True, None

    configured_key = get_configured_api_key()
    if not configured_key:
        return (
            False,
            "API key authentication is required, but KINTSUTECH_API_KEY is not configured on this server.",
        )

    # 1. If remote HTTP transport context is available, enforce HTTP-level authorization
    if ctx is not None and getattr(ctx, "headers", None) is not None:
        headers = ctx.headers
        header_key: str | None = None
        for h_name, h_val in headers.items():
            if h_name.lower() == "x-api-key":
                header_key = h_val
                break
            elif h_name.lower() == "authorization" and h_val.startswith("Bearer "):
                header_key = h_val[len("Bearer ") :].strip()
                break

        if not header_key:
            return (
                False,
                "Remote HTTP request missing required 'X-API-Key' or 'Authorization: Bearer <key>' header.",
            )

        if not secrets.compare_digest(header_key, configured_key):
            return False, "Invalid API key provided in HTTP request headers."

        return True, None

    # 2. Local stdio or direct in-process execution fallback
    if not api_key_arg:
        return False, "Missing API key. Provide 'api_key' argument."

    if not secrets.compare_digest(api_key_arg, configured_key):
        return False, "Invalid API key."

    return True, None


# Read-Only Tools


@mcp_server.tool(
    name="list_services",
    description="List all monitored API services, their baseline status, and active adapter configurations.",
)
def list_services() -> dict[str, Any]:
    """List all monitored services."""
    return {"services": storage_registry.list_services()}


@mcp_server.tool(
    name="get_service_baseline",
    description="Retrieve the latest versioned baseline response for a service.",
)
def get_service_baseline(service_id: str) -> dict[str, Any]:
    """Retrieve the latest baseline response for a given service."""
    if not service_id or not isinstance(service_id, str):
        return {"error": "service_id must be a non-empty string."}
    baseline = storage_registry.get_latest_baseline(service_id.strip())
    if not baseline:
        return {"error": f"No baseline found for service '{service_id}'."}
    return {"baseline": baseline}


@mcp_server.tool(
    name="analyze_service_changes",
    description="Perform deterministic and AI-assisted change analysis between baseline and current API responses.",
)
def analyze_service_changes(
    service_id: str,
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Analyze structural and semantic API changes."""
    try:
        detection = detect_changes(baseline, current)
        analysis = analyze_changes(detection)
        ai_analysis = analyze_with_ai_adapter(
            service=service_id,
            baseline=baseline,
            current=current,
            detected_changes=detection,
        )
        return {
            "service_id": service_id,
            "deterministic_analysis": analysis,
            "ai_analysis": ai_analysis,
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp_server.tool(
    name="calculate_dependency_impact",
    description="Calculate blast radius and downstream consumers affected by an API change using NetworkX graph analysis.",
)
def calculate_dependency_impact(service_id: str) -> dict[str, Any]:
    """Calculate blast radius and downstream consumers."""
    if not service_id or not isinstance(service_id, str):
        return {"error": "service_id must be a non-empty string."}
    impact = default_dep_graph.calculate_impact(service_id.strip())
    return {"impact": impact}


@mcp_server.tool(
    name="list_incidents",
    description="List recorded incidents with status, severity, and repair proposal availability.",
)
def list_incidents(
    service_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """List incidents matching optional filters."""
    try:
        incidents = storage_registry.list_incidents(
            service_id=service_id,
            status=status,
        )
        return {"incidents": incidents}
    except Exception as exc:
        return {"error": str(exc)}


@mcp_server.tool(
    name="get_incident_evidence",
    description="Inspect comprehensive evidence, structural diffs, and verification metrics for a specific incident.",
)
def get_incident_evidence(incident_id: str) -> dict[str, Any]:
    """Inspect incident evidence and verification details."""
    if not incident_id or not isinstance(incident_id, str):
        return {"error": "incident_id must be a non-empty string."}
    incident = storage_registry.get_incident(incident_id.strip())
    if not incident:
        return {"error": f"Incident '{incident_id}' not found."}
    return {"incident": incident}


@mcp_server.tool(
    name="list_consumer_contracts",
    description="List registered downstream consumer contracts and schemas.",
)
def list_consumer_contracts(service_id: str | None = None) -> dict[str, Any]:
    """List downstream consumer contracts."""
    try:
        from consumer_contracts import contract_registry

        if service_id:
            return {"contracts": contract_registry.get_for_service(service_id.strip())}
        return {"contracts": contract_registry.list_all()}
    except Exception as exc:
        return {"error": str(exc)}


# Non-Mutating Validation Tool


@mcp_server.tool(
    name="validate_repair_proposal",
    description="Deterministically validate a proposed compatibility adapter against supplied test cases and registered consumer contracts. Does NOT activate the repair.",
)
def validate_repair_proposal(
    incident_id: str,
    adapter: dict[str, Any],
    test_cases: list[dict[str, Any]] | None = None,
    consumer_contracts: list[dict[str, Any]] | None = None,
    service_id: str | None = None,
    required_consumers: list[str] | None = None,
) -> dict[str, Any]:
    """Validate a repair proposal without mutating active adapters."""
    if not incident_id or not isinstance(incident_id, str) or not incident_id.strip():
        return {"error": "incident_id must be a non-empty string."}
    if not adapter or not isinstance(adapter, dict):
        return {"error": "adapter must be a dictionary configuration."}

    cases = test_cases if test_cases is not None else []
    try:
        from repair_validator import validate_repair

        validation = validate_repair(
            proposal=adapter,
            test_cases=cases,
            consumer_contracts=consumer_contracts,
            service_id=service_id,
            required_consumers=required_consumers,
        )
        storage_registry.record_validation(
            incident_id.strip(),
            validation,
            adapter_config=adapter,
            contract_version=validation.get("contract_version"),
        )
        return {
            "incident_id": incident_id.strip(),
            "validation": validation,
        }
    except Exception as exc:
        return {"error": str(exc)}


# Mutating Operations (Guarded with Authentication and Canonical Hash Validation)


@mcp_server.tool(
    name="request_repair_activation",
    description="Safely activate an independently validated adapter for a service. Rejected if validation did not pass, adapter hash does not match, contract version does not match, or authorization fails.",
)
def request_repair_activation(
    incident_id: str,
    adapter: dict[str, Any],
    authorizer: str,
    api_key: str | None = None,
    contract_version: str | None = None,
    note: str = "",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Activate an independently validated repair adapter."""
    is_auth_ok, auth_err = check_mcp_authorization(ctx=ctx, api_key_arg=api_key)
    if not is_auth_ok:
        return {"error": f"Unauthorized: {auth_err}"}

    if not incident_id or not isinstance(incident_id, str) or not incident_id.strip():
        return {"error": "incident_id must be a non-empty string."}
    if not adapter or not isinstance(adapter, dict):
        return {"error": "adapter must be a dictionary configuration."}
    if not authorizer or not isinstance(authorizer, str) or not authorizer.strip():
        return {"error": "authorizer must be specified."}

    try:
        result = storage_registry.activate_repair(
            incident_id.strip(),
            adapter,
            authorizer=authorizer.strip(),
            note=note or "",
            contract_version=contract_version,
        )

        try:
            from app.webhooks import webhook_manager

            event = webhook_manager.create_event(
                "repair.activated",
                result,
                service_id=result.get("service_id", "kintsutech"),
            )
            webhook_manager.dispatch_event_background(event)
        except Exception:
            pass

        return {
            "status": "activated",
            "activation": result,
        }
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


@mcp_server.tool(
    name="request_rollback",
    description="Deactivate an active repair adapter and rollback the service to its un-adapted state.",
)
def request_rollback(
    service_id: str,
    authorizer: str,
    reason: str = "",
    api_key: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Deactivate active adapter and restore service to un-adapted state."""
    is_auth_ok, auth_err = check_mcp_authorization(ctx=ctx, api_key_arg=api_key)
    if not is_auth_ok:
        return {"error": f"Unauthorized: {auth_err}"}

    if not service_id or not isinstance(service_id, str) or not service_id.strip():
        return {"error": "service_id must be a non-empty string."}
    if not authorizer or not isinstance(authorizer, str) or not authorizer.strip():
        return {"error": "authorizer must be specified."}

    try:
        result = storage_registry.rollback_repair(
            service_id.strip(),
            authorizer=authorizer.strip(),
            reason=reason or "",
        )

        try:
            from app.webhooks import webhook_manager

            event = webhook_manager.create_event(
                "repair.rollback_completed",
                result,
                service_id=service_id.strip(),
            )
            webhook_manager.dispatch_event_background(event)
        except Exception:
            pass

        return {
            "status": "rolled_back",
            "rollback": result,
        }
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


TOOL_DISPATCH: dict[str, Any] = {
    "list_services": list_services,
    "get_service_baseline": get_service_baseline,
    "analyze_service_changes": analyze_service_changes,
    "calculate_dependency_impact": calculate_dependency_impact,
    "list_incidents": list_incidents,
    "get_incident_evidence": get_incident_evidence,
    "list_consumer_contracts": list_consumer_contracts,
    "validate_repair_proposal": validate_repair_proposal,
    "request_repair_activation": request_repair_activation,
    "request_rollback": request_rollback,
}


def list_mcp_tools() -> list[dict[str, Any]]:
    """Return MCP tool catalog with JSON-schema input definitions."""
    tools: list[dict[str, Any]] = []
    for reg in mcp_server._tool_manager.list_tools():
        tools.append({
            "name": reg.name,
            "description": reg.description or "",
            "inputSchema": reg.parameters,
        })
    return tools


def call_mcp_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute an MCP tool request against the backend services."""
    if arguments is None:
        arguments = {}
    fn = TOOL_DISPATCH.get(tool_name)
    if not fn:
        return {"error": f"Unknown MCP tool '{tool_name}'."}
    try:
        return fn(**arguments)
    except TypeError as exc:
        return {"error": f"Invalid arguments for MCP tool '{tool_name}': {exc}"}
    except Exception as exc:
        return {"error": str(exc)}


from mcp.server.transport_security import TransportSecuritySettings


def create_mcp_streamable_app():
    """Create official MCP Streamable HTTP ASGI app with bounded request size and security settings."""
    allowed_hosts = ["localhost:*", "localhost", "127.0.0.1:*", "127.0.0.1", "testserver:*", "testserver"]
    env_hosts = os.environ.get("ALLOWED_HOSTS") or os.environ.get("FRONTEND_ORIGINS")
    if env_hosts:
        for item in env_hosts.split(","):
            h = item.strip()
            if "://" in h:
                h = h.split("://", 1)[1]
            if "/" in h:
                h = h.split("/", 1)[0]
            if h and h not in allowed_hosts:
                allowed_hosts.append(h)
                if not h.endswith(":*"):
                    allowed_hosts.append(f"{h}:*")

    max_size = int(os.environ.get("MAX_REQUEST_BODY_SIZE", "1048576"))
    return mcp_server.streamable_http_app(
        streamable_http_path="/",
        max_request_body_size=max_size,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=os.environ.get("ENVIRONMENT", "development").lower() == "production",
            allowed_hosts=allowed_hosts,
        ),
    )


# Streamable HTTP ASGI app for hosting
mcp_streamable_app = create_mcp_streamable_app()

if __name__ == "__main__":
    mcp_server.run(transport="stdio")
