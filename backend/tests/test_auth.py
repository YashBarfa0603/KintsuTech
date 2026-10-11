from datetime import datetime, timedelta, timezone
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

TEST_SECRET = "super-secret-test-key-32-chars-long!"


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

    token = _generate_test_token(secret="wrong-secret-key-1234567890123456")

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


def test_unauthenticated_request_to_activate_returns_401():
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.post(
        "/api/v1/repairs/activate",
        json={"incident_id": "INC-001", "adapter": {}},
    )
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

    invalid_token = _generate_test_token(secret="wrong-secret-signature-key-12345")
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



