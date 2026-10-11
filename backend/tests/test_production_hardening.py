from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import secrets
import tempfile
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.main import app
from app.mcp_server import mcp_server, check_mcp_authorization
from app.rate_limiter import rate_limiter
from app.security import (
    get_client_ip,
    is_trusted_proxy_enabled,
    validate_production_config,
)
from app.storage import StorageRegistry
from app.webhooks import WebhookManager


def test_production_config_missing_api_key(monkeypatch):
    """Refuse startup in production if KINTSUTECH_API_KEY is missing."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("KINTSUTECH_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("KINTSUTECH_WEBHOOK_SECRET", f"mock-wh-{secrets.token_hex(16)}")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.kintsutech.com")

    with pytest.raises(RuntimeError, match="KINTSUTECH_API_KEY must be set in production"):
        validate_production_config()


def test_production_config_insecure_api_key(monkeypatch):
    """Refuse startup in production if KINTSUTECH_API_KEY is too short or insecure default."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KINTSUTECH_WEBHOOK_SECRET", f"mock-wh-{secrets.token_hex(16)}")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.kintsutech.com")

    # Short key
    monkeypatch.setenv("KINTSUTECH_API_KEY", "short-key")
    with pytest.raises(RuntimeError, match="too short or insecure"):
        validate_production_config()

    # Blacklisted key
    monkeypatch.setenv("KINTSUTECH_API_KEY", "passwordpassword")
    with pytest.raises(RuntimeError, match="too short or insecure"):
        validate_production_config()


def test_production_config_missing_or_insecure_webhook_secret(monkeypatch):
    """Refuse startup in production if KINTSUTECH_WEBHOOK_SECRET is missing or weak."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KINTSUTECH_API_KEY", f"mock-key-{secrets.token_hex(16)}")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.kintsutech.com")

    monkeypatch.delenv("KINTSUTECH_WEBHOOK_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="KINTSUTECH_WEBHOOK_SECRET must be explicitly configured"):
        validate_production_config()

    monkeypatch.setenv("KINTSUTECH_WEBHOOK_SECRET", "weak-secret")
    with pytest.raises(RuntimeError, match="too short or insecure"):
        validate_production_config()


def test_production_config_wildcard_cors_rejected(monkeypatch):
    """Refuse startup in production if FRONTEND_ORIGINS contains wildcard '*'."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KINTSUTECH_API_KEY", f"mock-key-{secrets.token_hex(16)}")
    monkeypatch.setenv("KINTSUTECH_WEBHOOK_SECRET", f"mock-wh-{secrets.token_hex(16)}")
    monkeypatch.setenv("FRONTEND_ORIGINS", "*")

    with pytest.raises(RuntimeError, match="cannot contain wildcard"):
        validate_production_config()


def test_production_config_valid(monkeypatch):
    """Accept valid production configuration without exceptions."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KINTSUTECH_API_KEY", f"mock-key-{secrets.token_hex(16)}")
    monkeypatch.setenv("KINTSUTECH_WEBHOOK_SECRET", f"mock-wh-{secrets.token_hex(16)}")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://kintsu.example.com,https://admin.kintsu.example.com")

    # Should not raise
    validate_production_config()


def test_development_config_allowed_without_secrets(monkeypatch):
    """Permit local development mode without production secret requirements."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("KINTSUTECH_API_KEY", raising=False)
    monkeypatch.delenv("KINTSUTECH_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)

    # Should not raise in development
    validate_production_config()


def test_trusted_proxy_header_handling(monkeypatch):
    """Do not trust X-Forwarded-For or X-Real-IP unless KINTSUTECH_TRUST_PROXY is explicitly enabled."""
    scope = {
        "type": "http",
        "client": ("127.0.0.1", 50000),
        "headers": [
            (b"x-forwarded-for", b"203.0.113.195, 198.51.100.1"),
            (b"x-real-ip", b"198.51.100.2"),
        ],
    }
    request = Request(scope)

    # 1. Default (untrusted proxy) -> ignores forwarded headers
    monkeypatch.setenv("KINTSUTECH_TRUST_PROXY", "false")
    assert not is_trusted_proxy_enabled()
    assert get_client_ip(request) == "127.0.0.1"

    # 2. Enabled trusted proxy -> extracts first client IP
    monkeypatch.setenv("KINTSUTECH_TRUST_PROXY", "true")
    assert is_trusted_proxy_enabled()
    assert get_client_ip(request) == "203.0.113.195"


def test_request_body_size_limit(monkeypatch):
    """Reject requests exceeding MAX_REQUEST_BODY_SIZE with HTTP 413."""
    client = TestClient(app)
    monkeypatch.setenv("MAX_REQUEST_BODY_SIZE", "500")

    # 1. Small payload under 500 bytes -> processed normally
    small_payload = {"city": "Indore", "temp": 30}
    res_small = client.post("/api/v1/analyze/changes", json={"baseline": small_payload, "current": small_payload})
    assert res_small.status_code == 200

    # 2. Large payload over 500 bytes -> rejected with HTTP 413
    large_payload = {"data": "x" * 600}
    res_large = client.post("/api/v1/analyze/changes", json=large_payload)
    assert res_large.status_code == 413
    assert "Request entity too large" in res_large.json()["detail"]


def test_rate_limiting_mutations(monkeypatch):
    """Enforce rate limits on sensitive endpoints returning HTTP 429 and Retry-After."""
    client = TestClient(app)
    monkeypatch.setenv("KINTSUTECH_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_MUTATION_PER_MINUTE", "2")
    rate_limiter.reset()

    # Call 1 & 2 succeed
    res1 = client.post(
        "/api/v1/mcp/tools/call",
        json={"name": "calculate_dependency_impact", "arguments": {"service_id": "weather"}},
    )
    assert res1.status_code == 200

    res2 = client.post(
        "/api/v1/mcp/tools/call",
        json={"name": "calculate_dependency_impact", "arguments": {"service_id": "weather"}},
    )
    assert res2.status_code == 200

    # Call 3 exceeds limit -> 429 Too Many Requests
    res3 = client.post(
        "/api/v1/mcp/tools/call",
        json={"name": "calculate_dependency_impact", "arguments": {"service_id": "weather"}},
    )
    assert res3.status_code == 429
    assert "Rate limit exceeded" in res3.json()["detail"]
    assert "Retry-After" in res3.headers
    assert int(res3.headers["Retry-After"]) >= 1

    # Cleanup
    rate_limiter.reset()


def test_fresh_database_initialization_and_lifecycle():
    """Verify fresh SQLite database initialization, WAL pragma setup, and clean disposal."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_fresh.db"
        db_url = f"sqlite:///{db_path}"

        storage = StorageRegistry(db_url=db_url)
        assert db_path.exists()

        # Check basic operations
        service = storage.register_service("test_svc", name="test_svc", base_url="https://api.example.com")
        assert service["id"] == "test_svc"
        retrieved = storage.get_service("test_svc")
        assert retrieved["name"] == "test_svc"

        # Dispose database engine cleanly
        storage.close()


def test_webhook_manager_shutdown_and_resumption():
    """Verify WebhookManager can be gracefully shut down and automatically re-initialized without error."""
    wm = WebhookManager(secret="test-secret-123")

    # Shut down worker pool
    wm.shutdown(wait=False)
    assert wm._executor._shutdown is True

    # Dispatching in background must automatically reinitialize active executor
    evt = wm.create_event("test.event", {"hello": "world"})
    future = wm.dispatch_event_background(evt)
    assert future is not None
    # Wait for completion without raising BrokenThreadPool or 'cannot schedule new futures'
    results = future.result(timeout=3.0)
    assert isinstance(results, list)

    wm.shutdown(wait=False)


def test_chunked_streaming_request_body_size_limits(monkeypatch):
    """Verify MAX_REQUEST_BODY_SIZE limits both Content-Length and chunked/streamed requests."""
    monkeypatch.setenv("MAX_REQUEST_BODY_SIZE", "500")
    client = TestClient(app)

    # 1. With Content-Length header exceeding limit -> HTTP 413
    res_cl = client.post(
        "/api/v1/analyze/changes",
        content=b"x" * 600,
        headers={"Content-Type": "application/json", "Content-Length": "600"},
    )
    assert res_cl.status_code == 413
    assert "Request entity too large" in res_cl.json()["detail"]

    # 2. Chunked generator (no Content-Length header) exceeding limit -> HTTP 413
    def oversized_chunk_generator():
        yield b'{"baseline": {"temp": 20}, "current": {"temp": '
        yield b'"' + (b"x" * 600) + b'"}}'

    res_chunked = client.post(
        "/api/v1/analyze/changes",
        content=oversized_chunk_generator(),
        headers={"Content-Type": "application/json"},
    )
    assert res_chunked.status_code == 413
    assert "Request entity too large" in res_chunked.json()["detail"]

    # 3. Small chunked generator within limit -> HTTP 200
    def small_chunk_generator():
        yield b'{"baseline": {"temp": 20}, '
        yield b'"current": {"temp": 25}}'

    res_small = client.post(
        "/api/v1/analyze/changes",
        content=small_chunk_generator(),
        headers={"Content-Type": "application/json"},
    )
    assert res_small.status_code == 200

    # 4. Mounted MCP endpoint chunked exceeding limit -> HTTP 413
    res_mcp = client.post(
        "/mcp/",
        content=oversized_chunk_generator(),
        headers={"Content-Type": "application/json"},
    )
    assert res_mcp.status_code == 413


def test_rate_limiter_protects_services_and_repairs_validate(monkeypatch):
    """Verify POST /api/v1/services/{service_id} and /api/v1/repairs/validate are rate-limited."""
    monkeypatch.setenv("KINTSUTECH_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_MUTATION_PER_MINUTE", "2")
    rate_limiter.reset()
    client = TestClient(app)

    # 1. POST /api/v1/services/{service_id}
    r1 = client.post("/api/v1/services/svc_rl_1", json={"name": "svc1"})
    r2 = client.post("/api/v1/services/svc_rl_2", json={"name": "svc2"})
    r3 = client.post("/api/v1/services/svc_rl_3", json={"name": "svc3"})
    assert r1.status_code in (200, 401)
    assert r2.status_code in (200, 401)
    assert r3.status_code == 429

    rate_limiter.reset()

    # 2. POST /api/v1/repairs/validate
    val_payload = {
        "incident_id": "inc_rl_1",
        "adapter": {"field_mappings": {"temp": "temperature"}},
        "test_cases": [{"input": {"temp": 25}, "expected": {"temperature": 25}}],
    }
    v1 = client.post("/api/v1/repairs/validate", json=val_payload)
    v2 = client.post("/api/v1/repairs/validate", json=val_payload)
    v3 = client.post("/api/v1/repairs/validate", json=val_payload)
    assert v1.status_code in (200, 400)
    assert v2.status_code in (200, 400)
    assert v3.status_code == 429

    rate_limiter.reset()


def test_rate_limiter_spoofing_prevented(monkeypatch):
    """Verify spoofed X-Forwarded-For headers cannot bypass rate limiter when proxy is untrusted."""
    monkeypatch.setenv("KINTSUTECH_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("KINTSUTECH_TRUST_PROXY", "false")
    monkeypatch.setenv("RATE_LIMIT_MUTATION_PER_MINUTE", "2")
    rate_limiter.reset()
    client = TestClient(app)

    # Attacker attempts to rotate X-Forwarded-For to spoof different client IPs
    r1 = client.post(
        "/api/v1/mcp/tools/call",
        headers={"X-Forwarded-For": "1.1.1.1"},
        json={"name": "calculate_dependency_impact", "arguments": {"service_id": "weather"}},
    )
    r2 = client.post(
        "/api/v1/mcp/tools/call",
        headers={"X-Forwarded-For": "2.2.2.2"},
        json={"name": "calculate_dependency_impact", "arguments": {"service_id": "weather"}},
    )
    r3 = client.post(
        "/api/v1/mcp/tools/call",
        headers={"X-Forwarded-For": "3.3.3.3"},
        json={"name": "calculate_dependency_impact", "arguments": {"service_id": "weather"}},
    )

    assert r1.status_code == 200
    assert r2.status_code == 200
    # 3rd request is blocked because the actual client IP is tracked, ignoring spoofed headers
    assert r3.status_code == 429

    rate_limiter.reset()


def test_rate_limiter_concurrent_requests(monkeypatch):
    """Verify rate limiter operates safely under high concurrency without race conditions."""
    monkeypatch.setenv("KINTSUTECH_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_MUTATION_PER_MINUTE", "10")
    rate_limiter.reset()
    client = TestClient(app)

    def make_call():
        res = client.post(
            "/api/v1/mcp/tools/call",
            json={"name": "calculate_dependency_impact", "arguments": {"service_id": "weather"}},
        )
        return res.status_code

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_call) for _ in range(25)]
        results = [f.result() for f in futures]

    # Exactly 10 succeed, and 15 are rate limited
    assert results.count(200) == 10
    assert results.count(429) == 15

    rate_limiter.reset()


def test_repeated_lifespan_cycles():
    """Verify repeated app startup and shutdown cycles do not fail or leak MCP session managers."""
    for cycle in range(3):
        with TestClient(app) as client:
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200
            assert resp.json()["status"] in ("ok", "healthy", "operational")


def test_mcp_streamable_http_auth_enforcement(monkeypatch):
    """Verify remote HTTP callers cannot invoke mutating MCP tools without valid HTTP headers."""
    mock_api_key = f"mock-key-{secrets.token_hex(16)}"
    monkeypatch.setenv("KINTSUTECH_API_KEY", mock_api_key)

    class MockRemoteHTTPContext:
        def __init__(self, headers: dict[str, str]):
            self.headers = headers

    # 1. Remote HTTP with no headers, but api_key provided in argument -> rejected
    ctx_no_header = MockRemoteHTTPContext(headers={"Host": "localhost"})
    ok, err = check_mcp_authorization(ctx=ctx_no_header, api_key_arg=mock_api_key)
    assert not ok
    assert "missing required" in err

    # 2. Remote HTTP with invalid X-API-Key header -> rejected
    ctx_bad_key = MockRemoteHTTPContext(headers={"Host": "localhost", "X-API-Key": "wrong-key"})
    ok, err = check_mcp_authorization(ctx=ctx_bad_key, api_key_arg=mock_api_key)
    assert not ok
    assert "Invalid API key" in err

    # 3. Remote HTTP with valid X-API-Key header -> authorized
    ctx_valid_x_key = MockRemoteHTTPContext(
        headers={"Host": "localhost", "X-API-Key": mock_api_key}
    )
    ok, err = check_mcp_authorization(ctx=ctx_valid_x_key)
    assert ok
    assert err is None

    # 4. Remote HTTP with valid Authorization Bearer header -> authorized
    ctx_valid_bearer = MockRemoteHTTPContext(
        headers={"Host": "localhost", "Authorization": f"Bearer {mock_api_key}"}
    )
    ok, err = check_mcp_authorization(ctx=ctx_valid_bearer)
    assert ok
    assert err is None


def test_mcp_stdio_auth_fallback(monkeypatch):
    """Verify local stdio transport (ctx is None) accepts tool argument api_key."""
    mock_api_key = f"mock-key-{secrets.token_hex(16)}"
    monkeypatch.setenv("KINTSUTECH_API_KEY", mock_api_key)

    # 1. Local stdio with valid tool argument -> authorized
    ok, err = check_mcp_authorization(ctx=None, api_key_arg=mock_api_key)
    assert ok
    assert err is None

    # 2. Local stdio with invalid tool argument -> rejected
    ok, err = check_mcp_authorization(ctx=None, api_key_arg="invalid-key")
    assert not ok
    assert "Invalid API key" in err

    # 3. Local stdio with missing tool argument -> rejected
    ok, err = check_mcp_authorization(ctx=None, api_key_arg=None)
    assert not ok
    assert "Missing API key" in err


def test_production_config_with_kintsutech_env_variable(monkeypatch):
    """Confirm KINTSUTECH_ENV=production enforces fail-closed startup."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("KINTSUTECH_ENV", "production")
    monkeypatch.delenv("KINTSUTECH_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("KINTSUTECH_WEBHOOK_SECRET", f"mock-wh-{secrets.token_hex(16)}")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.kintsutech.com")

    with pytest.raises(RuntimeError, match="KINTSUTECH_API_KEY must be set in production"):
        validate_production_config()
