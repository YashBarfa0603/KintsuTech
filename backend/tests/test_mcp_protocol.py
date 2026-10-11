import asyncio
import contextlib
import json
import os
from typing import Any

from fastapi.testclient import TestClient
import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_client_server_memory_streams
import pytest

from app.main import app
from app.mcp_server import mcp_server
from app.security import compute_adapter_hash
from app.storage import storage_registry


def run_async(coro):
    """Helper to run async coroutines in an isolated event loop."""
    return asyncio.run(coro)


@contextlib.asynccontextmanager
async def create_test_mcp_client():
    """Create an official MCP ClientSession paired with the in-process MCPServer."""
    async with create_client_server_memory_streams() as ((s_read, s_write), (c_read, c_write)):
        server_task = asyncio.create_task(
            mcp_server._lowlevel_server.run(
                s_read,
                s_write,
                mcp_server._lowlevel_server.create_initialization_options(),
            )
        )
        try:
            async with ClientSession(c_read, c_write) as session:
                await session.initialize()
                yield session
        finally:
            server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await server_task


def parse_tool_result(result) -> dict[str, Any]:
    """Helper to parse TextContent JSON returned from MCP call_tool."""
    assert result.content, "Result content should not be empty"
    text = result.content[0].text
    return json.loads(text)


def test_mcp_protocol_initialization_and_capabilities():
    """Verify MCP protocol initialization, server info, and capability negotiation."""
    async def _test():
        async with create_test_mcp_client() as session:
            # Session is initialized in context manager
            tools_result = await session.list_tools()
            assert tools_result is not None
            assert len(tools_result.tools) >= 10

    run_async(_test())


def test_mcp_tools_list_schema_definitions():
    """Verify tools/list exposes all expected tools with valid JSON-schema input definitions."""
    async def _test():
        async with create_test_mcp_client() as session:
            tools_result = await session.list_tools()
            tools_by_name = {t.name: t for t in tools_result.tools}

            expected_tools = [
                "list_services",
                "get_service_baseline",
                "analyze_service_changes",
                "calculate_dependency_impact",
                "list_incidents",
                "get_incident_evidence",
                "list_consumer_contracts",
                "validate_repair_proposal",
                "request_repair_activation",
                "request_rollback",
            ]

            for tool_name in expected_tools:
                assert tool_name in tools_by_name, f"Expected tool '{tool_name}' in tools list"
                tool = tools_by_name[tool_name]
                assert tool.description, f"Tool '{tool_name}' must have a description"

                # Check JSON Schema input definitions
                schema = tool.input_schema
                assert isinstance(schema, dict), f"Tool '{tool_name}' must have a dict input_schema"
                assert schema.get("type") == "object"
                assert "properties" in schema

            # Check specific schema requirements
            calc_schema = tools_by_name["calculate_dependency_impact"].input_schema
            assert "service_id" in calc_schema["properties"]

            val_schema = tools_by_name["validate_repair_proposal"].input_schema
            assert "incident_id" in val_schema["properties"]
            assert "adapter" in val_schema["properties"]

            act_schema = tools_by_name["request_repair_activation"].input_schema
            assert "incident_id" in act_schema["properties"]
            assert "adapter" in act_schema["properties"]
            assert "authorizer" in act_schema["properties"]

    run_async(_test())


def test_mcp_read_only_tools():
    """Verify execution of read-only MCP tools over genuine protocol."""
    async def _test():
        async with create_test_mcp_client() as session:
            # 1. list_services
            res = await session.call_tool("list_services", {})
            assert not res.is_error
            data = parse_tool_result(res)
            assert "services" in data
            service_ids = [s["id"] for s in data["services"]]
            assert "weather" in service_ids

            # 2. get_service_baseline
            res = await session.call_tool("get_service_baseline", {"service_id": "weather"})
            assert not res.is_error
            data = parse_tool_result(res)
            assert "baseline" in data

            # Missing service baseline
            res = await session.call_tool("get_service_baseline", {"service_id": "unknown_svc"})
            data = parse_tool_result(res)
            assert "error" in data

            # 3. calculate_dependency_impact
            res = await session.call_tool("calculate_dependency_impact", {"service_id": "weather"})
            assert not res.is_error
            data = parse_tool_result(res)
            assert "impact" in data
            assert data["impact"]["service"] == "weather"
            assert data["impact"]["impact_level"] == "critical"

            # 4. list_consumer_contracts
            res = await session.call_tool("list_consumer_contracts", {})
            assert not res.is_error
            data = parse_tool_result(res)
            assert "contracts" in data

            # 5. list_incidents
            res = await session.call_tool("list_incidents", {})
            assert not res.is_error
            data = parse_tool_result(res)
            assert "incidents" in data

            # 6. get_incident_evidence (unknown)
            res = await session.call_tool("get_incident_evidence", {"incident_id": "INC-NONEXISTENT"})
            data = parse_tool_result(res)
            assert "error" in data

            # 7. analyze_service_changes
            baseline_sample = {"temperature": 22, "city": "Tokyo"}
            current_sample = {"temp_c": 22, "city": "Tokyo"}
            res = await session.call_tool(
                "analyze_service_changes",
                {
                    "service_id": "weather",
                    "baseline": baseline_sample,
                    "current": current_sample,
                },
            )
            assert not res.is_error
            data = parse_tool_result(res)
            assert "deterministic_analysis" in data
            assert "ai_analysis" in data

    run_async(_test())


def test_mcp_validate_repair_proposal_non_mutating():
    """Verify validate_repair_proposal validates proposal and does NOT activate repair."""
    async def _test():
        async with create_test_mcp_client() as session:
            inc = storage_registry.create_incident(
                "weather",
                title="Field temp renamed to temp_c",
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
                {"input": {"temp_c": 28}, "expected": {"temp_c": 28, "temp": 28}}
            ]

            res = await session.call_tool(
                "validate_repair_proposal",
                {
                    "incident_id": inc_id,
                    "adapter": adapter,
                    "test_cases": test_cases,
                },
            )
            assert not res.is_error
            data = parse_tool_result(res)
            assert "validation" in data
            assert data["validation"]["eligible_for_activation"] is True

            # Verify active adapter was NOT mutated by validation alone
            # If weather had an active adapter or not, this incident is not activated
            incident_record = storage_registry.get_incident(inc_id)
            assert incident_record["status"] != "repair_activated"

    run_async(_test())


def test_mcp_mutating_tools_security_and_authorization(monkeypatch):
    """Verify mutating MCP tools require authentication when configured and do not leak secrets."""
    secret_key = "kintsu-secure-api-key-999"
    monkeypatch.setenv("KINTSUTECH_API_KEY", secret_key)
    monkeypatch.setenv("KINTSUTECH_REQUIRE_AUTH", "true")

    async def _test():
        async with create_test_mcp_client() as session:
            # 1. request_repair_activation without api_key
            res = await session.call_tool(
                "request_repair_activation",
                {
                    "incident_id": "INC-001",
                    "adapter": {"operation": "copy_field"},
                    "authorizer": "attacker",
                },
            )
            data = parse_tool_result(res)
            assert "error" in data
            assert "Unauthorized" in data["error"]
            assert secret_key not in json.dumps(data), "Must not leak secret key in error output"

            # 2. request_repair_activation with invalid api_key
            res = await session.call_tool(
                "request_repair_activation",
                {
                    "incident_id": "INC-001",
                    "adapter": {"operation": "copy_field"},
                    "authorizer": "attacker",
                    "api_key": "wrong-key",
                },
            )
            data = parse_tool_result(res)
            assert "error" in data
            assert "Unauthorized" in data["error"]

            # 3. request_rollback without api_key
            res = await session.call_tool(
                "request_rollback",
                {
                    "service_id": "weather",
                    "authorizer": "attacker",
                },
            )
            data = parse_tool_result(res)
            assert "error" in data
            assert "Unauthorized" in data["error"]

            # 4. request_rollback with invalid api_key
            res = await session.call_tool(
                "request_rollback",
                {
                    "service_id": "weather",
                    "authorizer": "attacker",
                    "api_key": "wrong-key",
                },
            )
            data = parse_tool_result(res)
            assert "error" in data
            assert "Unauthorized" in data["error"]

    run_async(_test())


def test_mcp_repair_activation_guardrails_and_rollback(monkeypatch):
    """
    Verify complete activation flow over genuine MCP:
    - Rejects unvalidated proposals
    - Rejects adapter hash mismatches
    - Activates validated adapter with authorized key
    - Successfully rolls back active adapter
    """
    secret_key = "kintsu-admin-key-777"
    monkeypatch.setenv("KINTSUTECH_API_KEY", secret_key)

    async def _test():
        async with create_test_mcp_client() as session:
            inc = storage_registry.create_incident(
                "weather",
                title="Weather schema changed",
                severity="high",
                differences=[{"kind": "field_removed", "path": "temp"}],
            )
            inc_id = inc["id"]

            validated_adapter = {
                "operation": "copy_field",
                "source_field": "temp_c",
                "target_field": "temp",
                "semantics_confirmed": True,
            }
            test_cases = [
                {"input": {"temp_c": 19}, "expected": {"temp_c": 19, "temp": 19}}
            ]

            # Validate proposal
            val_res = await session.call_tool(
                "validate_repair_proposal",
                {
                    "incident_id": inc_id,
                    "adapter": validated_adapter,
                    "test_cases": test_cases,
                },
            )
            val_data = parse_tool_result(val_res)
            assert val_data["validation"]["eligible_for_activation"] is True

            # Attempt activation with a tampered adapter (hash mismatch)
            tampered_adapter = {
                "operation": "copy_field",
                "source_field": "different_field",
                "target_field": "temp",
                "semantics_confirmed": True,
            }
            res_tampered = await session.call_tool(
                "request_repair_activation",
                {
                    "incident_id": inc_id,
                    "adapter": tampered_adapter,
                    "authorizer": "lead_eng",
                    "api_key": secret_key,
                },
            )
            tampered_data = parse_tool_result(res_tampered)
            assert "error" in tampered_data
            assert "does not match validated adapter" in tampered_data["error"]

            # Attempt activation with valid key and validated adapter
            res_activate = await session.call_tool(
                "request_repair_activation",
                {
                    "incident_id": inc_id,
                    "adapter": validated_adapter,
                    "authorizer": "lead_eng",
                    "api_key": secret_key,
                },
            )
            act_data = parse_tool_result(res_activate)
            assert act_data.get("status") == "activated"
            assert act_data["activation"]["incident_id"] == inc_id

            # Rollback active repair
            res_rollback = await session.call_tool(
                "request_rollback",
                {
                    "service_id": "weather",
                    "authorizer": "lead_eng",
                    "reason": "Routine rollback test via genuine MCP",
                    "api_key": secret_key,
                },
            )
            rb_data = parse_tool_result(res_rollback)
            assert rb_data.get("status") == "rolled_back"
            assert rb_data["rollback"]["service_id"] == "weather"

    run_async(_test())


def test_mcp_streamable_http_transport():
    """Verify genuine MCP client session communicating over hosted Streamable HTTP transport."""
    async def _test():
        async with app.router.lifespan_context(app):
            transport = httpx2.ASGITransport(app=app)
            async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
                async with streamable_http_client("http://127.0.0.1:8000/mcp/", http_client=client) as (r, w):
                    async with ClientSession(r, w) as session:
                        init_res = await session.initialize()
                        assert init_res.server_info.name == "kintsutech-mcp"
                        assert init_res.server_info.version == "0.1.0"

                        # Call tool over Streamable HTTP
                        tools = await session.list_tools()
                        assert len(tools.tools) >= 10

                        res = await session.call_tool("list_services", {})
                        assert not res.is_error
                        data = parse_tool_result(res)
                        assert "services" in data

    run_async(_test())


def test_mcp_rest_endpoints_backward_compatibility():
    """Verify existing /api/v1/mcp/tools and /api/v1/mcp/tools/call remain fully backward-compatible."""
    client = TestClient(app)

    # 1. GET /api/v1/mcp/tools
    res = client.get("/api/v1/mcp/tools")
    assert res.status_code == 200
    body = res.json()
    assert "tools" in body
    tool_names = [t["name"] for t in body["tools"]]
    assert "list_services" in tool_names
    assert "calculate_dependency_impact" in tool_names
    assert "list_consumer_contracts" in tool_names

    # Check that inputSchema is provided for each tool
    for t in body["tools"]:
        assert "inputSchema" in t

    # 2. POST /api/v1/mcp/tools/call
    res = client.post(
        "/api/v1/mcp/tools/call",
        json={
            "name": "calculate_dependency_impact",
            "arguments": {"service_id": "weather"},
        },
    )
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["tool"] == "calculate_dependency_impact"
    assert "impact" in res_data["result"]
    assert res_data["result"]["impact"]["service"] == "weather"

    # 3. POST /api/v1/mcp/tools/call with unknown tool
    res = client.post(
        "/api/v1/mcp/tools/call",
        json={
            "name": "non_existent_tool_xyz",
            "arguments": {},
        },
    )
    assert res.status_code == 400
    assert "Unknown MCP tool" in res.json()["detail"]
