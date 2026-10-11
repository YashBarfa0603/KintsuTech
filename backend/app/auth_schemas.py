from typing import Any
from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    """Public, safe representation of an authenticated Supabase user."""

    id: str = Field(description="Supabase user UUID (sub)")
    email: str | None = Field(default=None, description="User email address if authenticated via email/OAuth")
    phone: str | None = Field(default=None, description="User phone number if authenticated via phone OTP")
    role: str = Field(default="authenticated", description="Supabase user role claim")
    display_name: str = Field(description="Best available display name derived from user metadata, email, or phone")
    user_metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata provided by user or OAuth provider")
    app_metadata: dict[str, Any] = Field(default_factory=dict, description="Application metadata managed by Supabase")


class AuthHealthResponse(BaseModel):
    """Health and configuration status of the backend Supabase authentication service."""

    status: str = Field(default="healthy")
    auth_provider: str = Field(default="supabase")
    supabase_configured: bool
    jwks_enabled: bool
    jwt_secret_configured: bool
    protected_endpoints: list[str]


class TokenVerifyRequest(BaseModel):
    """Optional request body to verify a raw Supabase token."""

    token: str | None = Field(default=None, description="Raw access token to verify if not passed in Authorization header")


class TokenVerifyResponse(BaseModel):
    """Result of token verification."""

    valid: bool
    user: UserProfileResponse | None = None
    error: str | None = None
