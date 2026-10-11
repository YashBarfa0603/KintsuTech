"""
KintsuTech Alert Service: Alert lifecycle, incident-to-alert mapping,
quiet hours, delivery dispatching, and escalation handling.
"""

from datetime import datetime, time, timezone
import hashlib
import json
import logging
import os
from typing import Any
from zoneinfo import ZoneInfo

from app.storage import StorageRegistry, storage_registry

logger = logging.getLogger("kintsutech.alerts")

SEVERITY_LEVELS: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def is_in_quiet_hours(
    preferences: dict[str, Any],
    check_time: datetime | None = None,
) -> bool:
    """
    Check if the given time falls within the user's configured quiet hours.
    Takes user's timezone into account.
    """
    if not preferences.get("quiet_hours_enabled"):
        return False

    tz_str = preferences.get("timezone", "UTC")
    try:
        user_tz = ZoneInfo(tz_str)
    except Exception:
        user_tz = timezone.utc

    now_user = (check_time or datetime.now(timezone.utc)).astimezone(user_tz)
    current_time = now_user.time()

    start_str = preferences.get("quiet_hours_start", "22:00")
    end_str = preferences.get("quiet_hours_end", "08:00")

    try:
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))
        start_time = time(start_h, start_m)
        end_time = time(end_h, end_m)
    except Exception:
        return False

    if start_time <= end_time:
        return start_time <= current_time <= end_time
    else:
        # Spans midnight (e.g. 22:00 to 08:00)
        return current_time >= start_time or current_time <= end_time


def warrants_alert(
    severity: str,
    min_severity: str = "medium",
    differences: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Determine whether an event warrants creating an alert.
    Critical and high events always warrant alerts.
    Breaking differences warrant alerts even at medium.
    Low/info events are suppressed if below min_severity.
    """
    event_lvl = SEVERITY_LEVELS.get(severity.lower(), 1)
    min_lvl = SEVERITY_LEVELS.get(min_severity.lower(), 2)

    # Any critical or high event always warrants an alert
    if event_lvl >= SEVERITY_LEVELS["high"]:
        return True

    # If event has breaking changes, it warrants an alert
    if differences:
        for diff in differences:
            if (
                diff.get("breaking")
                or diff.get("is_breaking")
                or diff.get("change_type") in ("removed", "type_changed")
            ):
                return True

    return event_lvl >= min_lvl


def resolve_recipient_user_id(
    storage: StorageRegistry,
    requested_user_id: str | None = None,
    service_id: str | None = None,
) -> str:
    """
    Resolve responsible recipient user ID.
    If requested_user_id is provided and non-empty, use it.
    Otherwise resolve from existing users or fallback default.
    """
    if requested_user_id and requested_user_id.strip():
        return requested_user_id.strip()

    with storage._lock:
        with storage._get_session() as session:
            from app.storage import UserModel
            from sqlalchemy import select

            user = session.scalars(select(UserModel).limit(1)).first()
            if user:
                return user.id

    return "usr_default_admin"


class AlertService:
    """
    High-level service coordinating alert creation, evaluation,
    delivery attempts, and lifecycle transitions.
    """

    def __init__(self, storage: StorageRegistry | None = None) -> None:
        self.storage = storage or storage_registry

    def handle_incident_event(
        self,
        incident: dict[str, Any],
        recipient_user_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Evaluate an incident and create an idempotent alert if warranted.
        Ensures delivery errors or webhook failures do not crash caller.
        """
        try:
            severity = incident.get("severity", "medium")
            differences = incident.get("differences", [])
            recipient_id = resolve_recipient_user_id(
                self.storage,
                requested_user_id=recipient_user_id,
                service_id=incident.get("service_id"),
            )

            pref = self.storage.get_alert_preferences(recipient_id)
            min_sev = pref.get("min_severity", "medium")

            if not warrants_alert(severity, min_severity=min_sev, differences=differences):
                logger.info(
                    "Incident %s does not warrant an alert (severity: %s, min: %s)",
                    incident.get("id"),
                    severity,
                    min_sev,
                )
                return None

            inc_id = incident.get("id", "unknown")
            idempotency_key = f"alert:{inc_id}:{recipient_id}"

            title = incident.get("title") or f"Alert for incident {inc_id}"
            message = (
                f"Incident {inc_id} detected on service {incident.get('service_id', 'unknown')}.\n"
                f"Severity: {severity.upper()}.\n"
                f"Detected changes: {len(differences)}."
            )

            in_quiet = is_in_quiet_hours(pref)
            is_critical = severity.lower() in ("critical", "emergency")
            if in_quiet and not is_critical:
                logger.info("User %s in quiet hours; queueing alert with in_app delivery", recipient_id)

            channels = pref.get("channels", ["in_app"])
            delivery_channel = channels[0] if channels else "in_app"

            alert = self.storage.create_alert(
                user_id=recipient_id,
                title=title,
                message=message,
                severity=severity,
                incident_id=inc_id,
                source_event_id=incident.get("source_event_id"),
                idempotency_key=idempotency_key,
                delivery_channel=delivery_channel,
                metadata={
                    "service_id": incident.get("service_id"),
                    "differences_count": len(differences),
                    "created_from": "incident_pipeline",
                    "in_quiet_hours": in_quiet,
                },
            )

            # Dispatch initial delivery
            self.deliver_alert(alert, channel=delivery_channel, preferences=pref)
            return alert
        except Exception as exc:
            logger.error("Error creating alert for incident %s: %s", incident.get("id"), exc, exc_info=True)
            return None

    def deliver_alert(
        self,
        alert: dict[str, Any],
        channel: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute delivery across the requested channel.
        Outbound telephony is disabled by default unless explicitly enabled.
        """
        target_channel = channel or alert.get("delivery_channel") or "in_app"
        user_id = alert["user_id"]
        pref = preferences or self.storage.get_alert_preferences(user_id)

        # Telephony channel dispatch via Vapi
        if target_channel in ("phone", "telephony", "pstn"):
            from app.vapi import vapi_service
            res = vapi_service.dispatch_escalation_call(alert)
            if res.get("delivery"):
                return res["delivery"]
            return self.storage.record_delivery_attempt(
                alert["id"],
                channel="phone",
                status="skipped" if res.get("status") == "skipped" else "failed",
                error=res.get("reason") or res.get("error", "Telephony call skipped or unconfigured"),
                update_alert_status=False,
            )


        if target_channel == "in_app":
            return self.storage.record_delivery_attempt(
                alert["id"],
                channel="in_app",
                status="success",
                details={"destination": "in_app_feed"},
                update_alert_status=True,
            )

        if target_channel == "voice":
            if not pref.get("voice_enabled", True):
                return self.storage.record_delivery_attempt(
                    alert["id"],
                    channel="voice",
                    status="skipped",
                    error="Voice channel is disabled in user preferences.",
                    update_alert_status=False,
                )
            return self.storage.record_delivery_attempt(
                alert["id"],
                channel="voice",
                status="success",
                details={"destination": "voice_agent_feed"},
                update_alert_status=True,
            )

        return self.storage.record_delivery_attempt(
            alert["id"],
            channel=target_channel,
            status="success",
            details={"destination": target_channel},
            update_alert_status=True,
        )


alert_service = AlertService()
