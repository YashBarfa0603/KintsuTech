from typing import Any
import json

from app.dependency_graph import create_default_dependency_graph
from app.storage import storage_registry
from app.change_detector import detect_changes
from app.change_analyzer import analyze_changes
from app.ai_adapter import analyze_changes as analyze_with_ai_adapter


# Default dependency graph instance
default_dep_graph = create_default_dependency_graph()


MCP_TOOLS_SPEC = [
    {
        "name": "list_services",
        "description": "List all monitored API services, their baseline status, and active adapter configurations.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_service_baseline",
        "description": "Retrieve the latest versioned baseline response for a service.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_id": {
                    "type": "string",
                    "description": "Unique identifier of the service (e.g., 'weather', 'products')",
                }
            },
            "required": ["service_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "analyze_service_changes",
        "description": "Perform deterministic and AI-assisted change analysis between baseline and current API responses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_id": {
                    "type": "string",
                    "description": "Target service identifier",
                },
                "baseline": {
                    "type": "object",
                    "description": "Original known-good API response",
                },
                "current": {
                    "type": "object",
                    "description": "Current observed API response",
                },
            },
            "required": ["service_id", "baseline", "current"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calculate_dependency_impact",
        "description": "Calculate blast radius and downstream consumers affected by an API change using NetworkX graph analysis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_id": {
                    "type": "string",
                    "description": "The service experiencing changes",
                }
            },
            "required": ["service_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_incidents",
        "description": "List recorded incidents with status, severity, and repair proposal availability.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_id": {
                    "type": "string",
                    "description": "Optional filter by service ID",
                },
                "status": {
                    "type": "string",
                    "description": "Optional filter by status (open, repair_validated, repair_activated, rolled_back)",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_incident_evidence",
        "description": "Inspect comprehensive evidence, structural diffs, and verification metrics for a specific incident.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "Identifier of the incident (e.g., 'INC-001')",
                }
            },
            "required": ["incident_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "validate_repair_proposal",
        "description": "Deterministically validate a proposed compatibility adapter against supplied test cases. Does NOT activate the repair.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "Incident ID associated with the repair proposal",
                },
                "adapter": {
                    "type": "object",
                    "description": "The proposed adapter configuration (e.g., {'operation': 'copy_field', 'source_field': 'temp_c', 'target_field': 'temperature', 'semantics_confirmed': True})",
                },
                "test_cases": {
                    "type": "array",
                    "description": "List of test cases with 'input' and 'expected' outputs",
                    "items": {"type": "object"},
                },
            },
            "required": ["incident_id", "adapter", "test_cases"],
            "additionalProperties": False,
        },
    },
    {
        "name": "request_repair_activation",
        "description": "Safely activate an independently validated adapter for a service. Rejected if validation did not pass.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "The incident ID to activate the repair for",
                },
                "adapter": {
                    "type": "object",
                    "description": "The validated adapter configuration to activate",
                },
                "authorizer": {
                    "type": "string",
                    "description": "Identity of the authorizing human reviewer or automated policy",
                },
            },
            "required": ["incident_id", "adapter", "authorizer"],
            "additionalProperties": False,
        },
    },
    {
        "name": "request_rollback",
        "description": "Deactivate an active repair adapter and rollback the service to its un-adapted state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_id": {
                    "type": "string",
                    "description": "Service ID to roll back",
                },
                "authorizer": {
                    "type": "string",
                    "description": "Identity of the person requesting rollback",
                },
                "reason": {
                    "type": "string",
                    "description": "Explanation for rollback",
                },
            },
            "required": ["service_id", "authorizer"],
            "additionalProperties": False,
        },
    },
]


def list_mcp_tools() -> list[dict[str, Any]]:
    """Return MCP tool catalog."""
    return MCP_TOOLS_SPEC


def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute an MCP tool request against the backend services."""
    try:
        if tool_name == "list_services":
            return {"services": storage_registry.list_services()}

        elif tool_name == "get_service_baseline":
            svc_id = arguments["service_id"]
            baseline = storage_registry.get_latest_baseline(svc_id)
            if not baseline:
                return {"error": f"No baseline found for service '{svc_id}'."}
            return {"baseline": baseline}

        elif tool_name == "analyze_service_changes":
            svc_id = arguments["service_id"]
            baseline = arguments["baseline"]
            current = arguments["current"]

            detection = detect_changes(baseline, current)
            analysis = analyze_changes(detection)
            ai_analysis = analyze_with_ai_adapter(
                service=svc_id,
                baseline=baseline,
                current=current,
                detected_changes=detection,
            )
            return {
                "service_id": svc_id,
                "deterministic_analysis": analysis,
                "ai_analysis": ai_analysis,
            }

        elif tool_name == "calculate_dependency_impact":
            svc_id = arguments["service_id"]
            impact = default_dep_graph.calculate_impact(svc_id)
            return {"impact": impact}

        elif tool_name == "list_incidents":
            incidents = storage_registry.list_incidents(
                service_id=arguments.get("service_id"),
                status=arguments.get("status"),
            )
            return {"incidents": incidents}

        elif tool_name == "get_incident_evidence":
            inc_id = arguments["incident_id"]
            incident = storage_registry.get_incident(inc_id)
            if not incident:
                return {"error": f"Incident '{inc_id}' not found."}
            return {"incident": incident}

        elif tool_name == "validate_repair_proposal":
            from repair_validator import validate_repair

            inc_id = arguments["incident_id"]
            adapter = arguments["adapter"]
            test_cases = arguments["test_cases"]

            validation = validate_repair(adapter, test_cases)
            storage_registry.record_validation(inc_id, validation)
            return {
                "incident_id": inc_id,
                "validation": validation,
            }

        elif tool_name == "request_repair_activation":
            inc_id = arguments["incident_id"]
            adapter = arguments["adapter"]
            authorizer = arguments["authorizer"]

            result = storage_registry.activate_repair(
                inc_id,
                adapter,
                authorizer=authorizer,
            )
            return {
                "status": "activated",
                "activation": result,
            }

        elif tool_name == "request_rollback":
            svc_id = arguments["service_id"]
            authorizer = arguments["authorizer"]
            reason = arguments.get("reason", "")

            result = storage_registry.rollback_repair(
                svc_id,
                authorizer=authorizer,
                reason=reason,
            )
            return {
                "status": "rolled_back",
                "rollback": result,
            }

        else:
            return {"error": f"Unknown MCP tool '{tool_name}'."}

    except Exception as exc:
        return {"error": str(exc)}
