from datetime import datetime, timezone
import logging
import os
import secrets
from typing import Any
import httpx
import jwt
from jwt import PyJWKClient, PyJWTError
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.security import get_configured_api_key, is_auth_enforced, is_production

logger = logging.getLogger("kintsutech.auth")

# Security scheme for FastAPI OpenAPI docs
security_bearer = HTTPBearer(auto_error=False)

# Configuration from environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
SUPABASE_AUTH_ENABLED = os.environ.get("SUPABASE_AUTH_ENABLED", "true").lower() in ("true", "1", "yes")
SUPABASE_AUDIENCE = os.environ.get("SUPABASE_AUDIENCE", "authenticated")
SUPABASE_ISSUER = os.environ.get("SUPABASE_ISSUER", "").rstrip("/")

# JWKS Client cache
_jwks_client: PyJWKClient | None = None


def get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if _jwks_client is None and SUPABASE_URL:
        jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=16)
    return _jwks_client


def get_expected_audience() -> str | None:
    return SUPABASE_AUDIENCE or os.environ.get("SUPABASE_AUDIENCE", "authenticated")


def get_expected_issuer() -> str | None:
    """Derive expected JWT issuer from SUPABASE_ISSUER or standard SUPABASE_URL."""
    issuer = SUPABASE_ISSUER or os.environ.get("SUPABASE_ISSUER", "").rstrip("/")
    if issuer:
        return issuer.rstrip("/")
    url = SUPABASE_URL or os.environ.get("SUPABASE_URL", "").rstrip("/")
    if url:
        return f"{url.rstrip('/')}/auth/v1"
    return None



class AuthenticatedUser(BaseModel):
    """Verified user identity derived directly from validated token claims."""

    id: str = Field(description="Supabase user UUID (sub)")
    email: str | None = None
    phone: str | None = None
    role: str = "authenticated"
    aud: str = "authenticated"
    app_metadata: dict[str, Any] = Field(default_factory=dict)
    user_metadata: dict[str, Any] = Field(default_factory=dict)
    raw_claims: dict[str, Any] = Field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return (
            self.user_metadata.get("full_name")
            or self.user_metadata.get("name")
            or self.email
            or self.phone
            or self.id
        )

    @property
    def is_admin(self) -> bool:
        """
        Determine if human user has administrative or owner privileges.
        Derived strictly from trusted server-controlled claims in app_metadata or server-assigned human roles.
        NEVER checks client-editable user_metadata.

        Security Note:
        Top-level role='service_role' is a machine secret role in Supabase, NOT a human administrator.
        A 'service_role' claim alone cannot grant human administrator privileges to a user session.
        Service-to-service authorization is handled independently via API-key authentication
        (CallerIdentity.caller_type == 'api_key').
        """
        # Trusted top-level JWT human role claim (service_role excluded)
        if self.role in ("admin", "owner", "superadmin"):
            return True

        # Trusted server-controlled app_metadata claims (service_role excluded)
        app_meta_role = self.app_metadata.get("role")
        if app_meta_role in ("admin", "owner", "superadmin"):
            return True

        if self.app_metadata.get("is_admin") is True or self.app_metadata.get("is_owner") is True:
            return True

        roles = self.app_metadata.get("roles")
        if isinstance(roles, list) and any(r in ("admin", "owner", "superadmin") for r in roles):
            return True

        return False

    @property
    def can_operate_repairs(self) -> bool:
        """
        Determine if user has explicit permission to activate or rollback compatibility repairs.
        Default-deny: Ordinary authenticated users are denied by default.
        Requires explicit grant from trusted server-controlled claims.
        NEVER checks client-editable user_metadata.
        """
        # Passive, unauthenticated, machine, or disabled roles are denied immediately
        if self.role in ("anon", "guest", "viewer", "unauthorized", "disabled", "service_role"):
            return False


        # Server-controlled explicit revoke in app_metadata
        if self.app_metadata.get("can_repair") is False or self.app_metadata.get("can_operate_repairs") is False:
            return False

        # 1. Administrators and owners have repair permissions
        if self.is_admin:
            return True

        # 2. Trusted top-level JWT role
        if self.role in ("operator", "engineer", "sre", "incident_commander"):
            return True

        # 3. Trusted server-controlled app_metadata role or flag
        app_meta_role = self.app_metadata.get("role")
        if app_meta_role in ("operator", "engineer", "sre", "incident_commander"):
            return True

        if self.app_metadata.get("can_repair") is True or self.app_metadata.get("can_operate_repairs") is True:
            return True

        roles = self.app_metadata.get("roles")
        if isinstance(roles, list) and any(r in ("operator", "engineer", "sre", "incident_commander") for r in roles):
            return True

        # Default-deny: ordinary authenticated user without explicit operator grant
        return False


def _verify_token_via_supabase_api(token: str) -> dict[str, Any]:
    """
    Authoritative fallback verification against Supabase's /auth/v1/user endpoint.
    Guarantees algorithm-agnostic validation, token revocation check, and current user state.
    """
    if not SUPABASE_URL:
        raise ValueError("SUPABASE_URL is not configured.")

    headers = {
        "Authorization": f"Bearer {token}",
    }
    if SUPABASE_ANON_KEY:
        headers["apikey"] = SUPABASE_ANON_KEY

    with httpx.Client(timeout=4.0) as client:
        resp = client.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)
        if resp.status_code == 200:
            user_data = resp.json()
            return {
                "sub": user_data.get("id"),
                "email": user_data.get("email"),
                "phone": user_data.get("phone"),
                "role": user_data.get("role", "authenticated"),
                "aud": user_data.get("aud", "authenticated"),
                "app_metadata": user_data.get("app_metadata", {}),
                "user_metadata": user_data.get("user_metadata", {}),
            }
        elif resp.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired or is invalid.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Supabase auth verification failed with status {resp.status_code}.",
                headers={"WWW-Authenticate": "Bearer"},
            )


def verify_supabase_token(token: str) -> AuthenticatedUser:
    """
    Verifies a Supabase JWT access token using:
    1. Local asymmetric verification via Supabase JWKS (fastest, zero-latency caching).
    2. Local symmetric verification if SUPABASE_JWT_SECRET is configured.
    3. Fallback to Supabase /auth/v1/user endpoint via HTTP.
    Enforces allowed algorithms, signature, expiration, audience, issuer, and active role.
    Fails closed if verification cannot be established.
    """
    if not token or not isinstance(token, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims: dict[str, Any] | None = None
    validation_error: str | None = None
    verified_locally = False

    # Step 1: Try local JWKS (RS256 / ES256 / EdDSA) if SUPABASE_URL is available
    jwks_client = get_jwks_client()
    if jwks_client:
        try:
            token_alg = jwt.get_unverified_header(token).get("alg")
            if token_alg in ("RS256", "ES256", "EdDSA"):
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "ES256", "EdDSA"],
                    options={"verify_aud": False, "verify_iss": False},
                    leeway=60,
                )
                verified_locally = True
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as exc:
            validation_error = str(exc)

    # Step 2: Try HMAC (HS256) if JWT Secret is configured and JWKS didn't match
    if claims is None and SUPABASE_JWT_SECRET:
        try:
            claims = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False, "verify_iss": False},
                leeway=60,
            )
            verified_locally = True
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as exc:
            validation_error = str(exc)

    # Step 3: Authoritative fallback via Supabase HTTP API if local decode failed
    if claims is None and SUPABASE_URL:
        try:
            claims = _verify_token_via_supabase_api(token)
            verified_locally = False
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(f"Supabase auth API fallback failed: {exc}")

    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {validation_error or 'Signature verification failed.'}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate required sub claim
    user_id = claims.get("sub") or claims.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required 'sub' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate audience for locally verified JWTs
    expected_aud = get_expected_audience()
    if verified_locally and expected_aud:
        aud = claims.get("aud")
        if not aud:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing required 'aud' claim.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        aud_list = [aud] if isinstance(aud, str) else aud
        if expected_aud not in aud_list:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token audience '{aud}' does not match required audience '{expected_aud}'.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Validate issuer for locally verified JWTs when issuer is configured
    expected_iss = get_expected_issuer()
    if verified_locally and expected_iss:
        iss = claims.get("iss")
        if not iss:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing required 'iss' claim.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        normalized_iss = iss.rstrip("/")
        normalized_expected = expected_iss.rstrip("/")
        if normalized_iss != normalized_expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token issuer '{iss}' does not match expected issuer '{expected_iss}'.",
                headers={"WWW-Authenticate": "Bearer"},
            )



    # Reject anonymous tokens in all verification flows
    role = claims.get("role", "authenticated")
    aud_val = claims.get("aud", "authenticated")
    if role == "anon" or aud_val == "anon":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Anonymous tokens are not permitted for authenticated user operations.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        id=str(user_id),
        email=claims.get("email"),
        phone=claims.get("phone"),
        role=role,
        aud=str(aud_val),
        app_metadata=claims.get("app_metadata", {}),
        user_metadata=claims.get("user_metadata", {}),
        raw_claims=claims,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security_bearer),
) -> AuthenticatedUser:
    """
    FastAPI dependency requiring a valid Supabase bearer token.
    Raises 401 Unauthorized if token is missing, expired, or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_supabase_token(credentials.credentials)


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security_bearer),
) -> AuthenticatedUser | None:
    """
    FastAPI dependency for endpoints that accept both anonymous and authenticated callers.
    """
    if credentials is None:
        return None

    try:
        return verify_supabase_token(credentials.credentials)
    except HTTPException:
        return None


class CallerIdentity(BaseModel):
    """Normalized caller identity for authenticated requests."""

    caller_type: str = Field(description="'api_key' | 'user' | 'local_dev'")
    identity: str = Field(description="Authorizer string or user identifier")
    user: AuthenticatedUser | None = None
    is_admin: bool = False


def authenticate_caller(request: Request) -> CallerIdentity:
    """
    Authenticate an incoming request from either:
    1. Server-to-server API Key ('X-API-Key' or 'Authorization: Bearer <api_key>')
    2. Supabase Bearer access token ('Authorization: Bearer <jwt>')
    Fails closed when authentication is enforced or in production.
    """
    configured_key = get_configured_api_key()

    # 1. Check X-API-Key header
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        if not configured_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key authentication is required, but KINTSUTECH_API_KEY is not configured on this server.",
            )
        if secrets.compare_digest(api_key_header, configured_key):
            return CallerIdentity(
                caller_type="api_key",
                identity="authenticated_api_client",
                is_admin=True,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    # 2. Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer ") :].strip()

        # Check if the bearer token matches configured API key (S2S)
        if configured_key and secrets.compare_digest(token, configured_key):
            return CallerIdentity(
                caller_type="api_key",
                identity="authenticated_api_client",
                is_admin=True,
            )

        # Otherwise, verify as Supabase JWT
        user = verify_supabase_token(token)
        return CallerIdentity(
            caller_type="user",
            identity=user.display_name or user.email or user.id,
            user=user,
            is_admin=user.is_admin,
        )

    # 3. No credentials provided
    # Local dev bypass is ONLY permitted when explicitly in non-production and auth is unenforced
    if not is_auth_enforced() and not is_production():
        return CallerIdentity(
            caller_type="local_dev",
            identity="local_dev_user",
            is_admin=True,
        )

    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key authentication is required, but KINTSUTECH_API_KEY is not configured on this server.",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing API key. Provide 'X-API-Key' or 'Authorization: Bearer <key>' header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_authenticated_caller(request: Request) -> CallerIdentity:
    """Dependency ensuring caller is authenticated via API key or Supabase token."""
    return authenticate_caller(request)


def require_admin_or_api_key(request: Request) -> CallerIdentity:
    """
    Dependency ensuring caller is either:
    - Server-to-server API key client
    - Authenticated user with Administrator or Owner privilege
    - Local development environment (if non-production and auth unenforced)
    Rejects ordinary authenticated users with HTTP 403 Forbidden.
    """
    caller = authenticate_caller(request)
    if caller.caller_type == "user" and not caller.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Administrator or owner privileges required to access this resource.",
        )
    if caller.caller_type == "local_dev" and is_production():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return caller


def resolve_repair_authorizer(caller: CallerIdentity, payload: Any = None) -> str:
    """
    Derives authorizer identity for repair activation and rollback:
    - For users: strictly derived from verified token claims; requires explicit operator permissions.
    - For API keys: uses trusted caller identity or payload.authorizer.
    - Local dev: only permitted in non-production environments with unenforced auth.
    """
    payload_authorizer = getattr(payload, "authorizer", None) if payload else None

    if caller.caller_type == "user":
        if not caller.user or not caller.user.can_operate_repairs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: User lacks permission to activate or rollback repairs.",
            )
        return caller.user.display_name or caller.user.email or caller.user.id

    if caller.caller_type == "api_key":
        return payload_authorizer or "authenticated_api_client"

    if is_production():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    return payload_authorizer or "local_dev_user"


def require_repair_operator(request: Request, payload: Any = None) -> str:
    """Combined dependency + resolver for repair operations."""
    caller = authenticate_caller(request)
    return resolve_repair_authorizer(caller, payload)
