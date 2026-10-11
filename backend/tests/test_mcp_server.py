import pytest
from app.mcp_server import list_mcp_tools, call_mcp_tool
from app.storage import storage_registry


def test_list_mcp_tools():
    tools = list_mcp_tools()
    tool_names = [t["name"] for t in tools]

    assert "list_services" in tool_names
    assert "get_service_baseline" in tool_names
    assert "analyze_service_changes" in tool_names
    assert "calculate_dependency_impact" in tool_names
    assert "list_incidents" in tool_names
    assert "validate_repair_proposal" in tool_names
    assert "request_repair_activation" in tool_names
    assert "request_rollback" in tool_names


def test_mcp_tool_dependency_impact():
    res = call_mcp_tool("calculate_dependency_impact", {"service_id": "weather"})
    assert "impact" in res
    assert res["impact"]["service"] == "weather"
    assert res["impact"]["impact_level"] == "critical"


def test_mcp_tool_validate_and_activate_flow():
    # Setup test incident
    inc = storage_registry.create_incident(
        "weather",
        title="Weather field temp renamed to temp_c",
        severity="high",
        differences=[{"kind": "field_removed", "path": "temp"}],
    )
    inc_id = inc["id"]

    adapter = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temp",
        "semantics_confirmed": True,
    }
    test_cases = [
        {"input": {"temp_c": 30}, "expected": {"temp_c": 30, "temp": 30}}
    ]

    val_res = call_mcp_tool(
        "validate_repair_proposal",
        {
            "incident_id": inc_id,
            "adapter": adapter,
            "test_cases": test_cases,
        },
    )
    assert "validation" in val_res
    assert val_res["validation"]["eligible_for_activation"] is True

    # Activate
    act_res = call_mcp_tool(
        "request_repair_activation",
        {
            "incident_id": inc_id,
            "adapter": adapter,
            "authorizer": "mcp_admin",
        },
    )
    assert act_res["status"] == "activated"

    # Rollback
    rb_res = call_mcp_tool(
        "request_rollback",
        {
            "service_id": "weather",
            "authorizer": "mcp_admin",
            "reason": "Test rollback via MCP",
        },
    )
    assert rb_res["status"] == "rolled_back"


def test_unknown_mcp_tool():
    res = call_mcp_tool("non_existent_tool", {})
    assert "error" in res
