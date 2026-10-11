from datetime import datetime, timedelta, timezone
import secrets
from unittest.mock import patch
import jwt
import pytest
from fastapi import HTTPException

from app.auth import (
    AuthenticatedUser,
    get_current_user,
    get_optional_current_user,
    verify_supabase_token,
)
from fastapi.security import HTTPAuthorizationCredentials

TEST_SECRET = f"mock-jwt-test-key-{secrets.token_hex(16)}"


def _generate_test_token(
    sub: str = "user-uuid-1234",
    email: str = "alice@kintsutech.com",
    phone: str | None = None,
    expires_in_seconds: int = 3600,
    secret: str = TEST_SECRET,
    algorithm: str = "HS256",
    extra_claims: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
        "user_metadata": {
            "full_name": "Alice Developer",
        },
    }
    if phone:
        payload["phone"] = phone
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, secret, algorithm=algorithm)


def test_valid_token_decodes_claims(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    token = _generate_test_token(sub="user-42", email="test@kintsu.io")
    user = verify_supabase_token(token)

    assert isinstance(user, AuthenticatedUser)
    assert user.id == "user-42"
    assert user.email == "test@kintsu.io"
    assert user.role == "authenticated"
    assert user.display_name == "Alice Developer"


def test_token_with_phone_auth(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    token = _generate_test_token(
        sub="phone-user-99",
        email=None,
        phone="+919999999999",
        extra_claims={"user_metadata": {}},
    )
    user = verify_supabase_token(token)

    assert user.id == "phone-user-99"
    assert user.phone == "+919999999999"
    assert user.display_name == "+919999999999"


def test_expired_token_raises_401(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    expired_token = _generate_test_token(expires_in_seconds=-100)

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(expired_token)

    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_tampered_signature_raises_401(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    token = _generate_test_token(secret=f"wrong-jwt-key-{secrets.token_hex(16)}")

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)

    assert exc_info.value.status_code == 401


def test_missing_sub_claim_raises_401(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    now = datetime.now(timezone.utc)
    invalid_payload = {
        "email": "nosub@kintsu.io",
        "exp": int((now + timedelta(seconds=3600)).timestamp()),
    }
    token = jwt.encode(invalid_payload, TEST_SECRET, algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)

    assert exc_info.value.status_code == 401
    assert "sub" in exc_info.value.detail.lower()


def test_get_current_user_dependency_rejects_missing_credentials():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(None)

    assert exc_info.value.status_code == 401
    assert "authentication required" in exc_info.value.detail.lower()


def test_get_current_user_dependency_accepts_valid_credentials(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    token = _generate_test_token(sub="dep-user-1")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    user = get_current_user(creds)
    assert user.id == "dep-user-1"


def test_optional_current_user_returns_none_when_unauthenticated():
    assert get_optional_current_user(None) is None


def test_optional_current_user_returns_user_when_valid(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    token = _generate_test_token(sub="opt-user-2")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    user = get_optional_current_user(creds)
    assert user is not None
    assert user.id == "opt-user-2"


def test_unauthenticated_request_to_auth_me_returns_401():
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "authentication required" in response.json()["detail"].lower()


def test_authenticated_request_to_auth_me_returns_profile(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    from fastapi.testclient import TestClient
    client = TestClient(app)

    token = _generate_test_token(sub="uuid-me-123", email="me@kintsu.io")
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "uuid-me-123"
    assert data["email"] == "me@kintsu.io"
    assert data["role"] == "authenticated"


def test_auth_me_rejects_missing_token():
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    from fastapi.testclient import TestClient
    client = TestClient(app)

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "authentication required" in response.json()["detail"].lower()


def test_auth_me_rejects_malformed_token():
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    from fastapi.testclient import TestClient
    client = TestClient(app)

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer malformed.token.value"},
    )
    assert response.status_code == 401


def test_auth_health_endpoint_public():
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    response = client.get("/api/v1/auth/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["auth_provider"] == "supabase"
    assert "protected_endpoints" in data
    assert "/api/v1/auth/me" in data["protected_endpoints"]
    assert "/api/v1/repairs/activate" in data["protected_endpoints"]


def test_auth_verify_endpoint_with_header_token(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    token = _generate_test_token(sub="verify-user-1", email="verify@kintsu.io")
    response = client.post(
        "/api/v1/auth/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["user"]["id"] == "verify-user-1"
    assert data["user"]["email"] == "verify@kintsu.io"


def test_auth_verify_endpoint_with_body_token(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    token = _generate_test_token(sub="verify-body-2", email="body@kintsu.io")
    response = client.post(
        "/api/v1/auth/verify",
        json={"token": token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["user"]["id"] == "verify-body-2"


def test_auth_verify_endpoint_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    invalid_token = _generate_test_token(secret=f"wrong-jwt-key-{secrets.token_hex(16)}")
    response = client.post(
        "/api/v1/auth/verify",
        headers={"Authorization": f"Bearer {invalid_token}"},
    )
    assert response.status_code == 401


def test_auth_verify_endpoint_missing_token():
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    response = client.post("/api/v1/auth/verify")
    assert response.status_code == 401


def test_auth_logout_endpoint(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    from fastapi.testclient import TestClient
    client = TestClient(app)

    token = _generate_test_token(sub="logout-user")
    # Authenticated request succeeds
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "logged_out"
    assert response.json()["user_id"] == "logout-user"

    # Unauthenticated request fails
    unauth_resp = client.post("/api/v1/auth/logout")
    assert unauth_resp.status_code == 401


def test_public_routes_remain_accessible_without_auth():
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # Weather mock endpoint
    resp1 = client.get("/api/v1/mock/weather")
    assert resp1.status_code == 200

    # Services catalog endpoint
    resp2 = client.get("/api/v1/services")
    assert resp2.status_code == 200

    # Health endpoint
    resp3 = client.get("/api/v1/auth/health")
    assert resp3.status_code == 200


def test_supabase_api_fallback_success(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr("app.auth.SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setattr("app.auth.get_jwks_client", lambda: None)

    import httpx

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "id": "supabase-api-user-123",
                "email": "oauth_user@gmail.com",
                "role": "authenticated",
                "aud": "authenticated",
                "app_metadata": {"provider": "google"},
                "user_metadata": {"full_name": "Google OAuth User"},
            }

    with patch.object(httpx.Client, "get", return_value=MockResponse()):
        user = verify_supabase_token("some-opaque-or-rs256-token")
        assert user.id == "supabase-api-user-123"
        assert user.email == "oauth_user@gmail.com"
        assert user.display_name == "Google OAuth User"
        assert user.app_metadata.get("provider") == "google"


def test_user_is_persisted_to_sqlite_on_auth_me(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from app.storage import storage_registry
    app.dependency_overrides.pop(get_current_user, None)
    from fastapi.testclient import TestClient
    client = TestClient(app)

    token = _generate_test_token(sub="sqlite-user-1", email="sqlite@kintsu.io")
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    # Verify user exists in SQLite database
    db_user = storage_registry.get_user("sqlite-user-1")
    assert db_user is not None
    assert db_user["email"] == "sqlite@kintsu.io"
    assert db_user["full_name"] == "Alice Developer"


def test_user_sync_endpoint_updates_sqlite(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from app.storage import storage_registry
    app.dependency_overrides.pop(get_current_user, None)
    from fastapi.testclient import TestClient
    client = TestClient(app)

    token = _generate_test_token(sub="sqlite-sync-2", email="sync@kintsu.io")
    payload = {
        "full_name": "Bob Architect",
        "metadata": {"team": "infrastructure", "company": "Kintsu"},
    }
    response = client.post(
        "/api/v1/auth/sync",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Bob Architect"

    # Verify updated in SQLite
    db_user = storage_registry.get_user("sqlite-sync-2")
    assert db_user is not None
    assert db_user["full_name"] == "Bob Architect"
    assert db_user["user_metadata"]["team"] == "infrastructure"


def test_list_local_users_endpoint():
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    response = client.get("/api/v1/users")
    assert response.status_code == 200
    assert "users" in response.json()
    assert isinstance(response.json()["users"], list)


# Authorization Hardening Regression Tests


def test_user_enumeration_rejected_for_ordinary_users(monkeypatch):
    """Ordinary authenticated users cannot enumerate accounts via GET /api/v1/users (returns 403)."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # Ordinary user token (role: authenticated, not admin)
    token = _generate_test_token(sub="ordinary-user-1", email="user@kintsu.io")
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "privileges required" in response.json()["detail"].lower()


def test_user_enumeration_allowed_for_admin_users(monkeypatch):
    """Users with administrator role can access GET /api/v1/users."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # Admin user token
    admin_token = _generate_test_token(
        sub="admin-user-1",
        email="admin@kintsu.io",
        extra_claims={"role": "admin"},
    )
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert "users" in response.json()


def test_user_enumeration_allowed_for_api_key(monkeypatch):
    """Server-to-server callers with valid API key can access GET /api/v1/users."""
    mock_key = f"mock-api-key-{secrets.token_hex(16)}"
    monkeypatch.setenv("KINTSUTECH_API_KEY", mock_key)

    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # 1. Via X-API-Key header
    res1 = client.get("/api/v1/users", headers={"X-API-Key": mock_key})
    assert res1.status_code == 200
    assert "users" in res1.json()

    # 2. Via Authorization Bearer header
    res2 = client.get("/api/v1/users", headers={"Authorization": f"Bearer {mock_key}"})
    assert res2.status_code == 200
    assert "users" in res2.json()


def test_user_enumeration_rejected_unauthenticated_when_auth_enforced(monkeypatch):
    """Unauthenticated requests to GET /api/v1/users are rejected with 401 when auth is enforced."""
    mock_key = f"mock-api-key-{secrets.token_hex(16)}"
    monkeypatch.setenv("KINTSUTECH_API_KEY", mock_key)

    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    response = client.get("/api/v1/users")
    assert response.status_code == 401
    assert "missing api key" in response.json()["detail"].lower()


def test_repair_activation_rejects_viewer_or_unauthorized_user(monkeypatch):
    """Users with guest or viewer role cannot activate repairs (returns 403 Forbidden)."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    viewer_token = _generate_test_token(
        sub="viewer-user-1",
        email="viewer@kintsu.io",
        extra_claims={"role": "viewer"},
    )
    response = client.post(
        "/api/v1/repairs/activate",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={
            "incident_id": "INC-TEST",
            "adapter": {"operation": "copy_field", "source_field": "a", "target_field": "b"},
        },
    )
    assert response.status_code == 403
    assert "lacks permission" in response.json()["detail"].lower()


def test_repair_activation_derives_identity_from_verified_claims_and_ignores_payload_authorizer(monkeypatch):
    """User-triggered repair activation derives authorizer identity strictly from verified token claims."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from app.storage import storage_registry
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # Create and record a validated incident first
    inc = storage_registry.create_incident(
        service_id="weather",
        title="Test Incident for Auth Hardening",
        severity="medium",
        differences=[],
        evidence={},
        impact={},
    )
    adapter = {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"}
    storage_registry.record_validation(
        inc["id"],
        {"passed": True, "eligible_for_activation": True},
        adapter_config=adapter,
    )

    operator_token = _generate_test_token(
        sub="verified-operator-uuid",
        email="operator_alice@kintsu.io",
        extra_claims={
            "role": "operator",
            "user_metadata": {"full_name": "Alice Operator"},
        },
    )

    # Client attempts to pass forged authorizer
    response = client.post(
        "/api/v1/repairs/activate",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "incident_id": inc["id"],
            "adapter": adapter,
            "authorizer": "spoofed_superadmin",
            "note": "Activating via verified user session",
        },
    )
    assert response.status_code == 200
    activation = response.json()["activation"]

    # Verify authorizer was derived from verified user identity, NOT client payload
    assert activation["authorizer"] == "Alice Operator"
    assert activation["authorizer"] != "spoofed_superadmin"


def test_repair_rollback_derives_identity_from_claims_and_rejects_unauthorized_user(monkeypatch):
    """Rollback derives authorizer from verified claims and rejects unauthorized viewers."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from app.storage import storage_registry
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # Activate a repair first so rollback has an active adapter
    inc = storage_registry.create_incident(
        service_id="weather",
        title="Incident for Rollback Auth Test",
        severity="medium",
        differences=[],
        evidence={},
        impact={},
    )
    adapter = {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"}
    storage_registry.record_validation(
        inc["id"],
        {"passed": True, "eligible_for_activation": True},
        adapter_config=adapter,
    )
    storage_registry.activate_repair(inc["id"], adapter, authorizer="setup_auth_test")

    # Viewer cannot rollback (403)
    viewer_token = _generate_test_token(
        sub="viewer-rb-1",
        email="viewer@kintsu.io",
        extra_claims={"role": "viewer"},
    )
    resp_viewer = client.post(
        "/api/v1/repairs/rollback",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"service_id": "weather", "reason": "Viewer attempting rollback"},
    )
    assert resp_viewer.status_code == 403

    # Operator rollback succeeds and uses verified identity
    operator_token = _generate_test_token(
        sub="op-rb-1",
        email="bob_ops@kintsu.io",
        extra_claims={
            "role": "operator",
            "user_metadata": {"full_name": "Bob Operations"},
        },
    )
    resp_op = client.post(
        "/api/v1/repairs/rollback",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "service_id": "weather",
            "authorizer": "forged_commander",
            "reason": "Legitimate rollback by ops",
        },
    )
    assert resp_op.status_code == 200
    rollback = resp_op.json()["rollback"]
    assert rollback["authorizer"] == "Bob Operations"
    assert rollback["authorizer"] != "forged_commander"



def test_jwt_verification_rejects_invalid_audience(monkeypatch):
    """Tokens with an unauthorized audience (e.g. 'anon') are rejected with 401."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    anon_token = _generate_test_token(
        sub="anon-user-1",
        extra_claims={"aud": "anon"},
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(anon_token)
    assert exc_info.value.status_code == 401
    assert "audience" in exc_info.value.detail.lower()


def test_jwt_verification_rejects_anon_role(monkeypatch):
    """Tokens with role 'anon' are rejected with 401 Unauthorized."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    anon_role_token = _generate_test_token(
        sub="anon-role-user",
        extra_claims={"role": "anon", "aud": "authenticated"},
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(anon_role_token)
    assert exc_info.value.status_code == 401
    assert "anonymous tokens" in exc_info.value.detail.lower()


def test_jwt_verification_rejects_mismatched_issuer(monkeypatch):
    """Tokens with a forged issuer are rejected with 401 Unauthorized."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "https://valid-project.supabase.co")
    monkeypatch.setattr("app.auth.get_jwks_client", lambda: None)

    forged_iss_token = _generate_test_token(
        sub="user-iss-1",
        extra_claims={"iss": "https://malicious-supabase-clone.com/auth/v1"},
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(forged_iss_token)
    assert exc_info.value.status_code == 401
    assert "issuer" in exc_info.value.detail.lower()


def test_audit_log_and_webhook_deliveries_require_auth_when_enforced(monkeypatch):
    """GET /api/v1/repairs/audit and GET /api/v1/webhooks/deliveries enforce authentication."""
    mock_key = f"mock-api-key-{secrets.token_hex(16)}"
    monkeypatch.setenv("KINTSUTECH_API_KEY", mock_key)
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # 1. Unauthenticated requests are rejected with 401
    assert client.get("/api/v1/repairs/audit").status_code == 401
    assert client.get("/api/v1/webhooks/deliveries").status_code == 401

    # 2. S2S API key requests succeed (200)
    assert client.get("/api/v1/repairs/audit", headers={"X-API-Key": mock_key}).status_code == 200
    assert client.get("/api/v1/webhooks/deliveries", headers={"X-API-Key": mock_key}).status_code == 200

    # 3. Authenticated Supabase user requests succeed (200)
    user_token = _generate_test_token(sub="audit-viewer-1", email="viewer@kintsu.io")
    assert client.get(
        "/api/v1/repairs/audit",
        headers={"Authorization": f"Bearer {user_token}"},
    ).status_code == 200
    assert client.get(
        "/api/v1/webhooks/deliveries",
        headers={"Authorization": f"Bearer {user_token}"},
    ).status_code == 200


def test_auth_verify_endpoint_does_not_persist_or_echo_raw_token(monkeypatch):
    """POST /api/v1/auth/verify verifies token without echoing raw token in response or SQLite."""
    import json
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from app.storage import storage_registry
    from fastapi.testclient import TestClient
    client = TestClient(app)

    raw_token = _generate_test_token(sub="verify-token-uuid", email="clean@kintsu.io")
    response = client.post(
        "/api/v1/auth/verify",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert response.status_code == 200
    res_data = response.json()

    # Raw token must not appear in response payload
    assert raw_token not in json.dumps(res_data)

    # Raw token must not appear in persisted user database record
    user_db = storage_registry.get_user("verify-token-uuid")
    assert user_db is not None
    assert raw_token not in json.dumps(user_db)


# =====================================================================
# Phase 6 Authorization Hardening Tests
# =====================================================================


def test_admin_privilege_escalation_via_user_metadata_role_rejected(monkeypatch):
    """Setting user_metadata.role = 'admin' does NOT grant administrative privileges (403 Forbidden)."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    token = _generate_test_token(
        sub="attacker-sub-1",
        email="attacker@kintsu.io",
        extra_claims={
            "role": "authenticated",
            "user_metadata": {"role": "admin", "full_name": "Attacker Role"},
        },
    )
    user = verify_supabase_token(token)
    assert user.is_admin is False

    response = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert "administrator or owner privileges required" in response.json()["detail"].lower()


def test_admin_privilege_escalation_via_user_metadata_is_admin_rejected(monkeypatch):
    """Setting user_metadata.is_admin = true does NOT grant administrative privileges (403 Forbidden)."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    token = _generate_test_token(
        sub="attacker-sub-2",
        email="attacker2@kintsu.io",
        extra_claims={
            "role": "authenticated",
            "user_metadata": {"is_admin": True, "full_name": "Attacker Flag"},
        },
    )
    user = verify_supabase_token(token)
    assert user.is_admin is False

    response = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert "administrator or owner privileges required" in response.json()["detail"].lower()


def test_admin_privileges_granted_only_by_trusted_claims(monkeypatch):
    """Admin privilege is granted ONLY via trusted server-controlled claims (top-level role or app_metadata)."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # 1. Top-level role: admin
    token_role = _generate_test_token(
        sub="legit-admin-1",
        email="admin1@kintsu.io",
        extra_claims={"role": "admin"},
    )
    assert verify_supabase_token(token_role).is_admin is True
    assert client.get("/api/v1/users", headers={"Authorization": f"Bearer {token_role}"}).status_code == 200

    # 2. Server-controlled app_metadata: role = admin
    token_app_role = _generate_test_token(
        sub="legit-admin-2",
        email="admin2@kintsu.io",
        extra_claims={"role": "authenticated", "app_metadata": {"role": "admin"}},
    )
    assert verify_supabase_token(token_app_role).is_admin is True
    assert client.get("/api/v1/users", headers={"Authorization": f"Bearer {token_app_role}"}).status_code == 200

    # 3. Server-controlled app_metadata: is_admin = True
    token_app_flag = _generate_test_token(
        sub="legit-admin-3",
        email="admin3@kintsu.io",
        extra_claims={"role": "authenticated", "app_metadata": {"is_admin": True}},
    )
    assert verify_supabase_token(token_app_flag).is_admin is True
    assert client.get("/api/v1/users", headers={"Authorization": f"Bearer {token_app_flag}"}).status_code == 200


def test_repair_default_deny_for_ordinary_authenticated_user(monkeypatch):
    """Ordinary authenticated users cannot activate or rollback repairs by default (403 Forbidden)."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from app.storage import storage_registry
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # Prepare validated incident
    inc = storage_registry.create_incident(
        service_id="weather",
        title="Incident for Default-Deny Test",
        severity="medium",
        differences=[],
        evidence={},
        impact={},
    )
    adapter = {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"}
    storage_registry.record_validation(
        inc["id"],
        {"passed": True, "eligible_for_activation": True},
        adapter_config=adapter,
    )

    # Ordinary user token (role: authenticated, no operator claim)
    user_token = _generate_test_token(
        sub="ordinary-user-dd",
        email="regular_dev@kintsu.io",
        extra_claims={"role": "authenticated"},
    )
    user = verify_supabase_token(user_token)
    assert user.can_operate_repairs is False

    # Activation denied
    res_act = client.post(
        "/api/v1/repairs/activate",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"incident_id": inc["id"], "adapter": adapter},
    )
    assert res_act.status_code == 403
    assert "lacks permission" in res_act.json()["detail"].lower()

    # Rollback denied
    res_rb = client.post(
        "/api/v1/repairs/rollback",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"service_id": "weather", "reason": "Ordinary user rollback"},
    )
    assert res_rb.status_code == 403
    assert "lacks permission" in res_rb.json()["detail"].lower()


def test_repair_privilege_escalation_via_user_metadata_spoofing_rejected(monkeypatch):
    """User metadata cannot grant repair activation or rollback permission (403 Forbidden)."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    spoofed_token = _generate_test_token(
        sub="spoofed-repair-user",
        email="spoof@kintsu.io",
        extra_claims={
            "role": "authenticated",
            "user_metadata": {
                "role": "operator",
                "can_repair": True,
                "can_operate_repairs": True,
                "is_admin": True,
            },
        },
    )
    user = verify_supabase_token(spoofed_token)
    assert user.can_operate_repairs is False

    res_act = client.post(
        "/api/v1/repairs/activate",
        headers={"Authorization": f"Bearer {spoofed_token}"},
        json={
            "incident_id": "INC-NONEXISTENT",
            "adapter": {"operation": "noop"},
        },
    )
    assert res_act.status_code == 403
    assert "lacks permission" in res_act.json()["detail"].lower()

    res_rb = client.post(
        "/api/v1/repairs/rollback",
        headers={"Authorization": f"Bearer {spoofed_token}"},
        json={"service_id": "weather", "reason": "Spoofed metadata rollback"},
    )
    assert res_rb.status_code == 403
    assert "lacks permission" in res_rb.json()["detail"].lower()


def test_repair_allowed_for_explicit_operator_roles_and_app_metadata(monkeypatch):
    """Explicit server-controlled operator grants allow repair operations."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    # Top-level roles
    for role in ("operator", "engineer", "sre", "incident_commander"):
        token = _generate_test_token(sub=f"op-{role}", extra_claims={"role": role})
        assert verify_supabase_token(token).can_operate_repairs is True

    # app_metadata roles
    for app_role in ("operator", "engineer", "sre", "incident_commander"):
        token = _generate_test_token(
            sub=f"app-op-{app_role}",
            extra_claims={"role": "authenticated", "app_metadata": {"role": app_role}},
        )
        assert verify_supabase_token(token).can_operate_repairs is True

    # app_metadata can_repair flag
    token_flag = _generate_test_token(
        sub="app-flag-user",
        extra_claims={"role": "authenticated", "app_metadata": {"can_repair": True}},
    )
    assert verify_supabase_token(token_flag).can_operate_repairs is True


def test_repair_viewer_and_guest_roles_denied(monkeypatch):
    """Viewers and guests are denied repair operations."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    for role in ("viewer", "guest"):
        token = _generate_test_token(sub=f"deny-{role}", extra_claims={"role": role})
        assert verify_supabase_token(token).can_operate_repairs is False
        res = client.post(
            "/api/v1/repairs/rollback",
            headers={"Authorization": f"Bearer {token}"},
            json={"service_id": "weather", "reason": "Denied role rollback"},
        )
        assert res.status_code == 403

    # Anonymous tokens are rejected at authentication stage (401)
    anon_token = _generate_test_token(sub="deny-anon", extra_claims={"role": "anon"})
    res_anon = client.post(
        "/api/v1/repairs/rollback",
        headers={"Authorization": f"Bearer {anon_token}"},
        json={"service_id": "weather", "reason": "Anon rollback"},
    )
    assert res_anon.status_code == 401



def test_repair_operations_allowed_for_api_key(monkeypatch):
    """S2S integrations with valid API key can operate repairs."""
    mock_key = f"mock-api-key-{secrets.token_hex(16)}"
    monkeypatch.setenv("KINTSUTECH_API_KEY", mock_key)

    from app.main import app
    from app.storage import storage_registry
    from fastapi.testclient import TestClient

    client = TestClient(app)

    inc = storage_registry.create_incident(
        service_id="weather",
        title="Incident for API Key Repair",
        severity="low",
        differences=[],
        evidence={},
        impact={},
    )
    adapter = {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"}
    storage_registry.record_validation(
        inc["id"],
        {"passed": True, "eligible_for_activation": True},
        adapter_config=adapter,
    )

    # Activate via X-API-Key
    res_act = client.post(
        "/api/v1/repairs/activate",
        headers={"X-API-Key": mock_key},
        json={"incident_id": inc["id"], "adapter": adapter, "authorizer": "ci_pipeline"},
    )
    assert res_act.status_code == 200
    assert res_act.json()["activation"]["authorizer"] == "ci_pipeline"

    # Rollback via Authorization Bearer <api_key>
    res_rb = client.post(
        "/api/v1/repairs/rollback",
        headers={"Authorization": f"Bearer {mock_key}"},
        json={"service_id": "weather", "authorizer": "automated_canary", "reason": "S2S rollback"},
    )
    assert res_rb.status_code == 200
    assert res_rb.json()["rollback"]["authorizer"] == "automated_canary"


def test_jwt_missing_audience_claim_rejected(monkeypatch):
    """Locally verified tokens missing the required 'aud' claim are rejected with 401."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    now = datetime.now(timezone.utc)
    payload_no_aud = {
        "sub": "user-no-aud-1",
        "email": "noaud@kintsu.io",
        "role": "authenticated",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=3600)).timestamp()),
    }
    token = jwt.encode(payload_no_aud, TEST_SECRET, algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)
    assert exc_info.value.status_code == 401
    assert "missing required 'aud' claim" in exc_info.value.detail.lower()


def test_jwt_incorrect_audience_rejected(monkeypatch):
    """Locally verified tokens with an incorrect audience are rejected with 401."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    token = _generate_test_token(sub="user-wrong-aud", extra_claims={"aud": "wrong-client-aud"})
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)
    assert exc_info.value.status_code == 401
    assert "does not match required audience" in exc_info.value.detail.lower()


def test_jwt_missing_issuer_claim_rejected(monkeypatch):
    """Locally verified tokens missing the required 'iss' claim when configured are rejected with 401."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_ISSUER", "https://auth.kintsutech.internal/auth/v1")
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    token = _generate_test_token(sub="user-no-iss")  # lacks iss claim
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)
    assert exc_info.value.status_code == 401
    assert "missing required 'iss' claim" in exc_info.value.detail.lower()


def test_jwt_incorrect_issuer_rejected(monkeypatch):
    """Locally verified tokens with an incorrect issuer are rejected with 401."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_ISSUER", "https://valid.supabase.co/auth/v1")
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    token = _generate_test_token(
        sub="user-bad-iss",
        extra_claims={"iss": "https://attacker.supabase.co/auth/v1"},
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)
    assert exc_info.value.status_code == 401
    assert "does not match expected issuer" in exc_info.value.detail.lower()


def test_jwt_valid_audience_and_issuer_accepted(monkeypatch):
    """Tokens with matching audience and issuer are successfully verified."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_ISSUER", "https://valid.supabase.co/auth/v1")
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    token = _generate_test_token(
        sub="user-valid-jwt",
        email="valid@kintsu.io",
        extra_claims={
            "aud": "authenticated",
            "iss": "https://valid.supabase.co/auth/v1",
        },
    )
    user = verify_supabase_token(token)
    assert user.id == "user-valid-jwt"
    assert user.email == "valid@kintsu.io"


def test_supabase_api_fallback_rejects_anonymous_user(monkeypatch):
    """Remote Supabase API verification rejects anonymous tokens with 401."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr("app.auth.SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setattr("app.auth.get_jwks_client", lambda: None)

    import httpx

    class MockAnonResponse:
        status_code = 200
        def json(self):
            return {
                "id": "anon-user-uuid",
                "email": None,
                "role": "anon",
                "aud": "anon",
                "app_metadata": {},
                "user_metadata": {},
            }

    with patch.object(httpx.Client, "get", return_value=MockAnonResponse()):
        with pytest.raises(HTTPException) as exc_info:
            verify_supabase_token("some-anon-token")
        assert exc_info.value.status_code == 401
        assert "anonymous tokens are not permitted" in exc_info.value.detail.lower()


def test_production_mode_fails_closed_without_credentials(monkeypatch):
    """In production mode, unauthenticated requests fail closed with 401 Unauthorized."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("KINTSUTECH_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # User listing requires authentication and fails closed with 401
    res1 = client.get("/api/v1/users")
    assert res1.status_code == 401

    # Repair activation requires authentication and fails closed with 401
    res2 = client.post(
        "/api/v1/repairs/activate",
        json={"incident_id": "INC-1", "adapter": {"operation": "noop"}},
    )
    assert res2.status_code == 401

    # Repair rollback requires authentication and fails closed with 401
    res3 = client.post(
        "/api/v1/repairs/rollback",
        json={"service_id": "weather", "reason": "Prod test"},
    )
    assert res3.status_code == 401


def test_local_dev_bypass_disabled_in_production(monkeypatch):
    """authenticate_caller fails closed in production and never returns local_dev caller."""
    from app.auth import authenticate_caller

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("KINTSUTECH_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    class MockRequest:
        headers = {}

    with pytest.raises(HTTPException) as exc_info:
        authenticate_caller(MockRequest())
    assert exc_info.value.status_code == 401


def test_service_role_claim_alone_cannot_grant_human_admin_privileges(monkeypatch):
    """A JWT top-level role='service_role' alone does not grant human administrator privileges."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from app.storage import storage_registry
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # Token with role='service_role'
    srv_token = _generate_test_token(
        sub="service-worker-machine-id",
        email="service-worker@internal.kintsu.io",
        extra_claims={"role": "service_role"},
    )
    user = verify_supabase_token(srv_token)
    assert user.is_admin is False
    assert user.can_operate_repairs is False

    # Attempt to enumerate users via human admin endpoint
    res_users = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {srv_token}"},
    )
    assert res_users.status_code == 403
    assert "administrator or owner privileges required" in res_users.json()["detail"].lower()

    # Attempt to activate repair via human operator endpoint
    inc = storage_registry.create_incident(
        service_id="weather",
        title="Incident for service_role test",
        severity="low",
        differences=[],
        evidence={},
        impact={},
    )
    adapter = {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"}
    storage_registry.record_validation(
        inc["id"],
        {"passed": True, "eligible_for_activation": True},
        adapter_config=adapter,
    )

    res_act = client.post(
        "/api/v1/repairs/activate",
        headers={"Authorization": f"Bearer {srv_token}"},
        json={"incident_id": inc["id"], "adapter": adapter},
    )
    assert res_act.status_code == 403
    assert "lacks permission" in res_act.json()["detail"].lower()


def test_legitimate_explicitly_authorized_admin_retains_access(monkeypatch):
    """Legitimate explicitly authorized administrators retain access to protected operations."""
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    from app.main import app
    from app.storage import storage_registry
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # 1. Admin via app_metadata.role
    admin_token = _generate_test_token(
        sub="human-admin-uuid",
        email="lead_admin@kintsu.io",
        extra_claims={
            "role": "authenticated",
            "app_metadata": {"role": "admin"},
            "user_metadata": {"full_name": "Lead Admin"},
        },
    )
    user = verify_supabase_token(admin_token)
    assert user.is_admin is True
    assert user.can_operate_repairs is True

    # User enumeration succeeds
    assert client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200

    # Repair activation succeeds
    inc = storage_registry.create_incident(
        service_id="weather",
        title="Incident for Human Admin Test",
        severity="medium",
        differences=[],
        evidence={},
        impact={},
    )
    adapter = {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"}
    storage_registry.record_validation(
        inc["id"],
        {"passed": True, "eligible_for_activation": True},
        adapter_config=adapter,
    )

    res = client.post(
        "/api/v1/repairs/activate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"incident_id": inc["id"], "adapter": adapter},
    )
    assert res.status_code == 200
    assert res.json()["activation"]["authorizer"] == "Lead Admin"


def test_configured_issuer_accepted_exact_format(monkeypatch):
    """Locally verified token matching the exact configured project issuer format is accepted."""
    exact_iss = "https://kintsu-prod-project.supabase.co/auth/v1"
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_ISSUER", exact_iss)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    valid_token = _generate_test_token(
        sub="exact-iss-user",
        email="exact@kintsu.io",
        extra_claims={"iss": exact_iss, "aud": "authenticated"},
    )
    user = verify_supabase_token(valid_token)
    assert user.id == "exact-iss-user"
    assert user.email == "exact@kintsu.io"


def test_unexpected_issuer_and_missing_issuer_rejected(monkeypatch):
    """Tokens with unexpected issuer formats or missing issuer claims are strictly rejected with 401."""
    configured_iss = "https://kintsu-prod-project.supabase.co/auth/v1"
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_ISSUER", configured_iss)
    monkeypatch.setattr("app.auth.SUPABASE_URL", "")

    # 1. Missing issuer claim
    token_missing = _generate_test_token(sub="missing-iss-user")
    with pytest.raises(HTTPException) as exc1:
        verify_supabase_token(token_missing)
    assert exc1.value.status_code == 401
    assert "missing required 'iss' claim" in exc1.value.detail.lower()

    # 2. Mismatched format (e.g. omitting /auth/v1)
    token_mismatched_format = _generate_test_token(
        sub="mismatched-format-user",
        extra_claims={"iss": "https://kintsu-prod-project.supabase.co"},
    )
    with pytest.raises(HTTPException) as exc2:
        verify_supabase_token(token_mismatched_format)
    assert exc2.value.status_code == 401
    assert "does not match expected issuer" in exc2.value.detail.lower()

    # 3. Rogue external issuer
    token_rogue = _generate_test_token(
        sub="rogue-iss-user",
        extra_claims={"iss": "https://malicious-idp.com/auth/v1"},
    )
    with pytest.raises(HTTPException) as exc3:
        verify_supabase_token(token_rogue)
    assert exc3.value.status_code == 401
    assert "does not match expected issuer" in exc3.value.detail.lower()


def test_existing_server_to_server_api_key_operations_still_work(monkeypatch):
    """Server-to-server operations authenticated via API key continue working independently."""
    mock_key = f"mock-s2s-key-{secrets.token_hex(16)}"
    monkeypatch.setenv("KINTSUTECH_API_KEY", mock_key)

    from app.main import app
    from app.storage import storage_registry
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # 1. User listing via X-API-Key
    res_users = client.get("/api/v1/users", headers={"X-API-Key": mock_key})
    assert res_users.status_code == 200
    assert "users" in res_users.json()

    # 2. User listing via Authorization Bearer
    res_users_bearer = client.get("/api/v1/users", headers={"Authorization": f"Bearer {mock_key}"})
    assert res_users_bearer.status_code == 200

    # 3. Repair activation and rollback via API key
    inc = storage_registry.create_incident(
        service_id="weather",
        title="Incident for S2S Key Test",
        severity="low",
        differences=[],
        evidence={},
        impact={},
    )
    adapter = {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"}
    storage_registry.record_validation(
        inc["id"],
        {"passed": True, "eligible_for_activation": True},
        adapter_config=adapter,
    )

    res_act = client.post(
        "/api/v1/repairs/activate",
        headers={"X-API-Key": mock_key},
        json={"incident_id": inc["id"], "adapter": adapter, "authorizer": "s2s_pipeline"},
    )
    assert res_act.status_code == 200
    assert res_act.json()["activation"]["authorizer"] == "s2s_pipeline"

    res_rb = client.post(
        "/api/v1/repairs/rollback",
        headers={"Authorization": f"Bearer {mock_key}"},
        json={"service_id": "weather", "authorizer": "s2s_pipeline", "reason": "S2S test rollback"},
    )
    assert res_rb.status_code == 200
    assert res_rb.json()["rollback"]["authorizer"] == "s2s_pipeline"

