from datetime import datetime, timezone
import logging
import os
from typing import Any
import httpx
import jwt
from jwt import PyJWKClient, PyJWTError
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

logger = logging.getLogger("kintsutech.auth")

# Security scheme for FastAPI OpenAPI docs
security_bearer = HTTPBearer(auto_error=False)

# Configuration from environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
SUPABASE_AUTH_ENABLED = os.environ.get("SUPABASE_AUTH_ENABLED", "true").lower() in ("true", "1", "yes")

# JWKS Client cache
_jwks_client: PyJWKClient | None = None


def get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if _jwks_client is None and SUPABASE_URL:
        jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=16)
    return _jwks_client


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
    """
    if not token or not isinstance(token, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims: dict[str, Any] | None = None
    validation_error: str | None = None

    # Step 1: Try local JWKS (RS256 / ES256) if SUPABASE_URL is available
    jwks_client = get_jwks_client()
    if jwks_client:
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256", "EdDSA"],
                options={"verify_aud": False},
                leeway=60,
            )
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
                options={"verify_aud": False},
                leeway=60,
            )
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

    user_id = claims.get("sub") or claims.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required 'sub' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        id=str(user_id),
        email=claims.get("email"),
        phone=claims.get("phone"),
        role=claims.get("role", "authenticated"),
        aud=claims.get("aud", "authenticated"),
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
