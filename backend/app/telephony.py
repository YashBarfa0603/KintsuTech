"""
Compatibility module: Provides backward compatibility for app.telephony imports.
Canonical implementation has moved to app.vapi.
"""

from app.vapi import (
    E164_REGEX,
    VapiClient,
    VapiConfig,
    VapiService,
    VapiService as TelephonyService,
    build_privacy_alert_summary,
    mask_phone_number,
    validate_phone_number,
    vapi_client,
    vapi_service,
    vapi_service as telephony_service,
    verify_vapi_webhook_signature,
    verify_vapi_webhook_token,
)

__all__ = [
    "E164_REGEX",
    "TelephonyService",
    "VapiClient",
    "VapiConfig",
    "VapiService",
    "build_privacy_alert_summary",
    "mask_phone_number",
    "telephony_service",
    "validate_phone_number",
    "vapi_client",
    "vapi_service",
    "verify_vapi_webhook_signature",
    "verify_vapi_webhook_token",
]
