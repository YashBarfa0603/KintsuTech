"""
KintsuTech Vapi Voice Integration Module.

Provides official Vapi outbound calling adapter, phone validation,
privacy-conscious alert summarization, constant-time webhook authentication,
idempotent event processing, and integration with the KintsuTech alert storage layer.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import re
import secrets
from typing import Any
import httpx

from app.alerts import is_in_quiet_hours
from app.storage import StorageRegistry, storage_registry

logger = logging.getLogger("kintsutech.vapi")

E164_REGEX = re.compile(r"^\+[1-9]\d{1,14}$")


def validate_phone_number(number: str | None) -> bool:
    """Validate that the phone number matches E.164 standard formatting (+14155552671)."""
    if not number or not isinstance(number, str):
        return False
    return bool(E164_REGEX.match(number.strip()))


def mask_phone_number(number: str | None) -> str:
    """Return a masked phone number for safe logging and audit persistence."""
    if not number:
        return ""
    clean = number.strip()
    if len(clean) <= 5:
        return "***"
    return f"{clean[:2]}***{clean[-4:]}"


class VapiConfig:
    """Read and validate Vapi configuration from environment variables."""

    @classmethod
    def is_enabled(cls) -> bool:
        return os.environ.get("KINTSUTECH_TELEPHONY_ENABLED", "false").lower() in ("true", "1", "yes")

    @classmethod
    def get_provider(cls) -> str:
        return os.environ.get("KINTSUTECH_TELEPHONY_PROVIDER", "vapi").lower()

    @classmethod
    def get_api_key(cls) -> str:
        return os.environ.get("VAPI_API_KEY", "").strip()

    @classmethod
    def get_phone_number_id(cls) -> str:
        return os.environ.get("VAPI_PHONE_NUMBER_ID", "").strip()

    @classmethod
    def get_assistant_id(cls) -> str:
        return os.environ.get("VAPI_ASSISTANT_ID", "").strip()

    @classmethod
    def get_webhook_token(cls) -> str:
        return (
            os.environ.get("KINTSUTECH_VAPI_WEBHOOK_TOKEN", "")
            or os.environ.get("VAPI_WEBHOOK_SECRET", "")
        ).strip()

    @classmethod
    def get_webhook_secret(cls) -> str:
        """Alias for get_webhook_token for backward compatibility."""
        return cls.get_webhook_token()

    @classmethod
    def get_base_url(cls) -> str:
        return os.environ.get("VAPI_BASE_URL", "https://api.vapi.ai").rstrip("/")

    @classmethod
    def get_timeout_seconds(cls) -> float:
        try:
            return float(os.environ.get("VAPI_REQUEST_TIMEOUT_SECONDS", "10.0"))
        except ValueError:
            return 10.0

    @classmethod
    def is_ready(cls) -> bool:
        """Telephony is ready only if enabled and all required credentials are set."""
        if not cls.is_enabled():
            return False
        return bool(cls.get_api_key()) and bool(cls.get_phone_number_id()) and bool(cls.get_assistant_id())

    @classmethod
    def get_readiness_report(cls) -> dict[str, Any]:
        """Safe public readiness report that never leaks secrets."""
        return {
            "enabled": cls.is_enabled(),
            "provider": cls.get_provider(),
            "ready": cls.is_ready(),
            "api_key_configured": bool(cls.get_api_key()),
            "phone_number_id_configured": bool(cls.get_phone_number_id()),
            "assistant_id_configured": bool(cls.get_assistant_id()),
            "webhook_token_configured": bool(cls.get_webhook_token()),
            "webhook_secret_configured": bool(cls.get_webhook_token()),
            "base_url": cls.get_base_url(),
        }


def build_privacy_alert_summary(alert: dict[str, Any]) -> dict[str, str]:
    """
    Construct a privacy-conscious context payload for the Vapi voice assistant.
    Strictly omits credentials, tokens, connection strings, or full diff details.
    """
    alert_id = str(alert.get("id", "unknown"))
    title = str(alert.get("title", "Service incident alert"))
    severity = str(alert.get("severity", "medium")).upper()
    incident_id = str(alert.get("incident_id") or "N/A")
    meta = alert.get("metadata") or {}
    service_id = str(meta.get("service_id") or "monitored service")

    spoken_summary = (
        f"This is an urgent automated alert from KintsuTech. "
        f"A {severity} severity alert has been triggered for {service_id}. "
        f"Incident identifier {incident_id}. Title: {title}. "
        f"Please acknowledge this alert in the KintsuTech dashboard to resolve escalation."
    )

    return {
        "alert_id": alert_id,
        "title": title,
        "severity": severity,
        "incident_id": incident_id,
        "service_id": service_id,
        "summary": spoken_summary,
    }


def verify_vapi_webhook_token(
    headers: dict[str, str],
    expected_token: str | None = None,
) -> bool:
    """
    Verify incoming Vapi webhook authenticity using constant-time comparison.
    Accepts:
      - Authorization: Bearer <token>
      - x-vapi-secret: <token>
    Rejects immediately if no token is configured or if comparison fails.
    Never logs or leaks credentials.
    """
    expected = (expected_token or VapiConfig.get_webhook_token()).strip()
    if not expected:
        # Fail closed: reject unauthorized requests when token is unconfigured
        return False

    auth_header: str | None = None
    vapi_secret_header: str | None = None

    for key, val in headers.items():
        k = key.lower()
        if k == "authorization":
            auth_header = val.strip()
        elif k in ("x-vapi-secret", "x-vapi-signature"):
            vapi_secret_header = val.strip()

    # 1. Check Bearer token in Authorization header
    if auth_header:
        token = auth_header
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if secrets.compare_digest(token, expected):
            return True

    # 2. Check x-vapi-secret header
    if vapi_secret_header:
        if secrets.compare_digest(vapi_secret_header, expected):
            return True

    return False


# Alias for backward compatibility
verify_vapi_webhook_signature = verify_vapi_webhook_token


class VapiClient:
    """Official Vapi REST API client for outbound phone calling."""

    def __init__(self, config: type[VapiConfig] = VapiConfig) -> None:
        self.config = config

    def initiate_phone_call(
        self,
        to_number: str,
        alert: dict[str, Any],
        client: httpx.Client | None = None,
    ) -> dict[str, Any]:
        """
        Synchronously initiate an outbound call via official Vapi POST /call/phone endpoint.
        Returns call details or structured error dict.
        """
        if not self.config.is_ready():
            return {
                "success": False,
                "error": "Vapi telephony is disabled or credentials (API key, Phone ID, Assistant ID) are unconfigured.",
                "status": "unconfigured",
            }

        if not validate_phone_number(to_number):
            return {
                "success": False,
                "error": f"Invalid recipient phone number format '{to_number}'. Must be E.164.",
                "status": "invalid_phone_number",
            }

        summary_vars = build_privacy_alert_summary(alert)
        url = f"{self.config.get_base_url()}/call/phone"
        headers = {
            "Authorization": f"Bearer {self.config.get_api_key()}",
            "Content-Type": "application/json",
        }
        payload = {
            "assistantId": self.config.get_assistant_id(),
            "phoneNumberId": self.config.get_phone_number_id(),
            "customer": {
                "number": to_number.strip(),
            },
            "assistantOverrides": {
                "variableValues": summary_vars,
            },
        }

        try:
            if client is not None:
                res = client.post(url, json=payload, headers=headers)
            else:
                with httpx.Client(timeout=self.config.get_timeout_seconds()) as default_client:
                    res = default_client.post(url, json=payload, headers=headers)

            if res.status_code in (200, 201):
                data = res.json()
                call_id = data.get("id") or f"call_{secrets.token_hex(8)}"
                call_status = data.get("status", "queued")
                return {
                    "success": True,
                    "call_id": call_id,
                    "status": call_status,
                    "data": data,
                }
            elif res.status_code == 429:
                err_msg = f"Vapi API rate limit reached (HTTP 429): {res.text[:200]}"
                logger.warning(err_msg)
                return {
                    "success": False,
                    "error": err_msg,
                    "status_code": 429,
                    "status": "rate_limited",
                }
            else:
                err_msg = f"Vapi API returned HTTP {res.status_code}: {res.text[:300]}"
                logger.error("Vapi call initiation failed: %s", err_msg)
                return {
                    "success": False,
                    "error": err_msg,
                    "status_code": res.status_code,
                }
        except httpx.TimeoutException as exc:
            err_msg = f"Vapi API request timed out after {self.config.get_timeout_seconds()}s"
            logger.error(err_msg)
            return {
                "success": False,
                "error": err_msg,
                "status": "timeout",
            }
        except Exception as exc:
            logger.error("Network error connecting to Vapi API: %s", exc, exc_info=True)
            return {
                "success": False,
                "error": f"Connection error to Vapi API: {str(exc)}",
            }

    async def initiate_phone_call_async(
        self,
        to_number: str,
        alert: dict[str, Any],
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """
        Asynchronously initiate an outbound call via official Vapi POST /call/phone endpoint.
        """
        if not self.config.is_ready():
            return {
                "success": False,
                "error": "Vapi telephony is disabled or credentials (API key, Phone ID, Assistant ID) are unconfigured.",
                "status": "unconfigured",
            }

        if not validate_phone_number(to_number):
            return {
                "success": False,
                "error": f"Invalid recipient phone number format '{to_number}'. Must be E.164.",
                "status": "invalid_phone_number",
            }

        summary_vars = build_privacy_alert_summary(alert)
        url = f"{self.config.get_base_url()}/call/phone"
        headers = {
            "Authorization": f"Bearer {self.config.get_api_key()}",
            "Content-Type": "application/json",
        }
        payload = {
            "assistantId": self.config.get_assistant_id(),
            "phoneNumberId": self.config.get_phone_number_id(),
            "customer": {
                "number": to_number.strip(),
            },
            "assistantOverrides": {
                "variableValues": summary_vars,
            },
        }

        try:
            if client is not None:
                res = await client.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self.config.get_timeout_seconds()) as default_client:
                    res = await default_client.post(url, json=payload, headers=headers)

            if res.status_code in (200, 201):
                data = res.json()
                call_id = data.get("id") or f"call_{secrets.token_hex(8)}"
                call_status = data.get("status", "queued")
                return {
                    "success": True,
                    "call_id": call_id,
                    "status": call_status,
                    "data": data,
                }
            elif res.status_code == 429:
                err_msg = f"Vapi API rate limit reached (HTTP 429): {res.text[:200]}"
                logger.warning(err_msg)
                return {
                    "success": False,
                    "error": err_msg,
                    "status_code": 429,
                    "status": "rate_limited",
                }
            else:
                err_msg = f"Vapi API returned HTTP {res.status_code}: {res.text[:300]}"
                logger.error("Vapi call initiation failed: %s", err_msg)
                return {
                    "success": False,
                    "error": err_msg,
                    "status_code": res.status_code,
                }
        except httpx.TimeoutException:
            err_msg = f"Vapi API request timed out after {self.config.get_timeout_seconds()}s"
            logger.error(err_msg)
            return {
                "success": False,
                "error": err_msg,
                "status": "timeout",
            }
        except Exception as exc:
            logger.error("Network error connecting to Vapi API: %s", exc, exc_info=True)
            return {
                "success": False,
                "error": f"Connection error to Vapi API: {str(exc)}",
            }


class VapiService:
    """
    High-level Vapi service managing outbound escalation calls,
    pre-call eligibility checks (consent, quiet hours, retry limits),
    and idempotent webhook event processing.
    """

    def __init__(
        self,
        storage: StorageRegistry | None = None,
        client: VapiClient | None = None,
    ) -> None:
        self.storage = storage or storage_registry
        self.client = client or VapiClient()

    def dispatch_escalation_call(self, alert: dict[str, Any]) -> dict[str, Any]:
        """
        Evaluate eligibility and dispatch an outbound Vapi phone call for an overdue alert.
        Enforces consent, verified destination, quiet hours, and retry limits.
        """
        alert_id = alert["id"]
        status = alert.get("status", "pending")

        # 1. Alert status check: Stop calls if acknowledged, resolved, or cancelled
        if status in ("acknowledged", "resolved", "cancelled"):
            return {
                "status": "skipped",
                "reason": f"Alert is in terminal or acknowledged status '{status}'.",
            }

        # 2. Check user preferences
        user_id = alert["user_id"]
        pref = self.storage.get_alert_preferences(user_id)
        if not pref.get("phone_consent"):
            return self.storage.record_delivery_attempt(
                alert_id,
                channel="phone",
                status="failed",
                error="Recipient has not granted explicit phone call consent.",
                update_alert_status=False,
            )

        phone_number = pref.get("phone_number")
        if not phone_number or not validate_phone_number(phone_number):
            return self.storage.record_delivery_attempt(
                alert_id,
                channel="phone",
                status="failed",
                error="Recipient phone number is missing or does not match E.164 format.",
                update_alert_status=False,
            )

        # 3. Check quiet hours (unless emergency critical policy)
        is_critical = alert.get("severity", "").lower() in ("critical", "emergency")
        if is_in_quiet_hours(pref) and not is_critical:
            logger.info("Recipient %s is in quiet hours; skipping outbound telephone call", user_id)
            return {
                "status": "skipped",
                "reason": "Quiet hours active for recipient timezone.",
            }

        # 4. Check retry limits & duplicate call in progress
        max_attempts = pref.get("max_attempts", 3)
        history = self.storage.get_alert_history(alert_id)
        phone_attempts = sum(1 for h in history if h.get("channel") == "phone")
        if phone_attempts >= max_attempts:
            logger.info("Alert %s reached max phone retry attempts (%d/%d)", alert_id, phone_attempts, max_attempts)
            return {
                "status": "skipped",
                "reason": f"Maximum phone delivery attempts ({max_attempts}) reached.",
            }

        meta = alert.get("metadata") or {}
        if meta.get("vapi_call_status") in ("queued", "ringing", "in-progress"):
            return {
                "status": "skipped",
                "reason": "An active call is already in progress for this alert.",
            }

        # 5. Check readiness
        if not VapiConfig.is_ready():
            return self.storage.record_delivery_attempt(
                alert_id,
                channel="phone",
                status="failed",
                error="Vapi telephony is disabled or credentials (API key, Phone ID, Assistant ID) are unconfigured.",
                update_alert_status=False,
            )

        # 6. Initiate call
        call_res = self.client.initiate_phone_call(phone_number, alert)
        now_str = datetime.now(timezone.utc).isoformat()
        masked_number = mask_phone_number(phone_number)

        if call_res.get("success"):
            call_id = call_res.get("call_id", "")
            call_status = call_res.get("status", "queued")
            # Update alert metadata with call ID
            self.storage.update_alert_metadata(
                alert_id,
                {
                    "vapi_call_id": call_id,
                    "vapi_call_status": call_status,
                    "vapi_last_call_at": now_str,
                },
            )
            # Record delivery attempt
            delivery_record = self.storage.record_delivery_attempt(
                alert_id,
                channel="phone",
                status="success",
                details={
                    "provider": "vapi",
                    "call_id": call_id,
                    "status": call_status,
                    "recipient": masked_number,
                },
                update_alert_status=False,
            )
            return {
                "status": "initiated",
                "call_id": call_id,
                "call_status": call_status,
                "delivery": delivery_record,
            }
        else:
            err = call_res.get("error", "Unknown Vapi error")
            delivery_record = self.storage.record_delivery_attempt(
                alert_id,
                channel="phone",
                status="failed",
                error=err,
                details={
                    "provider": "vapi",
                    "recipient": masked_number,
                    "error": err,
                },
                update_alert_status=False,
            )
            return {
                "status": "failed",
                "error": err,
                "delivery": delivery_record,
            }

    def process_webhook_callback(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Process official Vapi server event callbacks (status-update, end-of-call-report).
        Handles duplicate webhook deliveries idempotently.
        Matches events to existing alerts using provider call ID.
        Updates call outcomes and stops future escalations if acknowledged.
        Never triggers an outbound call.
        """
        # Extract message object per official Vapi schema
        msg = payload.get("message") if isinstance(payload.get("message"), dict) else payload
        event_type = msg.get("type", "unknown")
        call_obj = msg.get("call") if isinstance(msg.get("call"), dict) else msg
        call_id = call_obj.get("id") or msg.get("callId") or msg.get("id")

        if not call_id:
            return {"status": "ignored", "reason": "No call ID in webhook payload"}

        call_status = call_obj.get("status") or msg.get("status", "ended")
        ended_reason = msg.get("endedReason") or call_obj.get("endedReason")
        duration = msg.get("duration") or call_obj.get("duration")

        # Idempotency check: compute deterministic event ID
        event_id = msg.get("id") or msg.get("eventId")
        if not event_id:
            event_id = f"vapi_{call_id}_{event_type}_{call_status}_{ended_reason or 'none'}"

        check_fn = getattr(self.storage, "is_duplicate_webhook_event", None) or getattr(self.storage, "check_and_record_webhook_event", None)
        if check_fn and check_fn(str(event_id)):
            logger.info("Duplicate Vapi webhook event %s ignored", event_id)
            return {
                "status": "duplicate",
                "message": f"Webhook event {event_id} already processed",
                "call_id": call_id,
                "event_type": event_type,
            }

        # Find corresponding alert
        alert = self.storage.find_alert_by_call_id(call_id)
        if not alert:
            logger.info("Received Vapi callback for untracked call ID %s", call_id)
            return {"status": "ignored", "reason": f"No alert associated with call {call_id}"}

        # Update alert metadata with call lifecycle outcome
        meta_updates = {
            "vapi_call_status": call_status,
            "vapi_ended_reason": ended_reason,
            "vapi_callback_at": datetime.now(timezone.utc).isoformat(),
        }
        if duration is not None:
            meta_updates["vapi_call_duration"] = duration
        self.storage.update_alert_metadata(alert["id"], meta_updates)

        # Match and update existing delivery record, or record lifecycle delivery outcome
        delivery_details = {
            "provider": "vapi",
            "call_id": call_id,
            "event_type": event_type,
            "call_status": call_status,
            "ended_reason": ended_reason,
            "duration": duration,
        }
        updated_delivery = self.storage.update_delivery_by_call_id(
            call_id,
            status="success" if call_status in ("in-progress", "ended", "completed") else "failed",
            details=delivery_details,
        )

        if not updated_delivery:
            self.storage.record_delivery_attempt(
                alert["id"],
                channel="phone",
                status="success" if call_status in ("in-progress", "ended", "completed") else "failed",
                details=delivery_details,
                update_alert_status=False,
            )

        # Check if call indicates acknowledgment
        if ended_reason in ("assistant-acknowledged-alert", "customer-acknowledged") or msg.get("acknowledged"):
            self.storage.acknowledge_alert(
                alert["id"],
                user_id=alert["user_id"],
                note=f"Acknowledged via Vapi phone call {call_id}",
            )

        return {
            "status": "processed",
            "alert_id": alert["id"],
            "call_id": call_id,
            "call_status": call_status,
            "event_type": event_type,
        }


# Singletons
vapi_client = VapiClient()
vapi_service = VapiService()
telephony_service = vapi_service
TelephonyService = VapiService
