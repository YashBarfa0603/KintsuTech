from datetime import datetime, timezone
import hashlib
import hmac
import json
from threading import Lock
import time
from typing import Any, Callable
import uuid

import httpx


DEFAULT_WEBHOOK_SECRET = "kintsutech_webhook_secret_dev"


class WebhookManager:
    """
    Manages incoming webhook signature verification, deduplication,
    outgoing event subscriptions, and delivery with retries.
    """

    def __init__(self, secret: str = DEFAULT_WEBHOOK_SECRET) -> None:
        self.secret = secret
        self._lock = Lock()
        self._processed_events: set[str] = set()  # Event deduplication cache
        self._subscriptions: dict[str, dict[str, Any]] = {}  # subscription_id -> sub
        self._delivery_logs: list[dict[str, Any]] = []

    def verify_signature(
        self,
        payload_bytes: bytes,
        signature_header: str | None,
        *,
        secret: str | None = None,
    ) -> bool:
        """
        Verify incoming HMAC-SHA256 signature using constant-time comparison.
        Accepts signature as 'sha256=<hex>' or raw '<hex>'.
        """
        if not signature_header:
            return False

        key = (secret or self.secret).encode("utf-8")
        expected_hex = hmac.new(key, payload_bytes, hashlib.sha256).hexdigest()

        given_hex = signature_header.strip()
        if given_hex.startswith("sha256="):
            given_hex = given_hex[len("sha256=") :]

        return hmac.compare_digest(expected_hex, given_hex)

    def verify_timestamp(
        self,
        timestamp_header: str | None,
        *,
        max_age_seconds: int = 300,
    ) -> bool:
        """
        Validate timestamp freshness to prevent replay attacks.
        Accepts ISO 8601 string or numeric unix timestamp.
        """
        if not timestamp_header:
            return False

        try:
            # Check numeric timestamp
            if timestamp_header.isdigit() or "." in timestamp_header:
                req_time = float(timestamp_header)
            else:
                dt = datetime.fromisoformat(timestamp_header)
                req_time = dt.timestamp()

            now = time.time()
            return abs(now - req_time) <= max_age_seconds
        except Exception:
            return False

    def is_duplicate_event(self, event_id: str) -> bool:
        """Check and record event_id for idempotency."""
        with self._lock:
            if event_id in self._processed_events:
                return True
            self._processed_events.add(event_id)
            return False

    def subscribe(
        self,
        *,
        target_url: str,
        events: list[str],
        secret: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Register an outgoing webhook destination."""
        if not target_url or not target_url.startswith(("http://", "https://")):
            raise ValueError("Valid http or https target_url is required.")

        with self._lock:
            sub_id = f"sub_{uuid.uuid4().hex[:12]}"
            sub = {
                "id": sub_id,
                "target_url": target_url,
                "events": events,
                "secret": secret or self.secret,
                "description": description,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._subscriptions[sub_id] = sub
            return sub

    def list_subscriptions(self) -> list[dict[str, Any]]:
        """List active webhook subscriptions."""
        with self._lock:
            return list(self._subscriptions.values())

    def create_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        service_id: str = "kintsutech",
    ) -> dict[str, Any]:
        """Construct a standardized KintsuTech event envelope."""
        event_id = f"evt_{uuid.uuid4().hex}"
        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "id": event_id,
            "type": event_type,
            "service_id": service_id,
            "timestamp": now_iso,
            "schema_version": "1.0",
            "data": payload,
        }

    def sign_payload(self, payload_bytes: bytes, secret: str | None = None) -> str:
        """Sign outgoing payload with HMAC-SHA256."""
        key = (secret or self.secret).encode("utf-8")
        digest = hmac.new(key, payload_bytes, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def dispatch_event(
        self,
        event: dict[str, Any],
        *,
        client: httpx.Client | None = None,
        max_attempts: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Send event to all matching subscribers with HMAC signature and retries.
        """
        event_type = event.get("type", "")
        payload_bytes = json.dumps(event).encode("utf-8")

        matched_subs = []
        with self._lock:
            for sub in self._subscriptions.values():
                if "*" in sub["events"] or event_type in sub["events"]:
                    matched_subs.append(sub)

        delivery_results = []
        for sub in matched_subs:
            target_url = sub["target_url"]
            sub_secret = sub.get("secret", self.secret)
            sig_header = self.sign_payload(payload_bytes, sub_secret)
            headers = {
                "Content-Type": "application/json",
                "X-KintsuTech-Signature": sig_header,
                "X-KintsuTech-Event": event_type,
                "X-KintsuTech-Delivery": str(uuid.uuid4()),
            }

            status = "failed"
            status_code = None
            error = None

            for attempt in range(1, max_attempts + 1):
                try:
                    if client:
                        resp = client.post(target_url, content=payload_bytes, headers=headers)
                    else:
                        with httpx.Client(timeout=5.0) as default_client:
                            resp = default_client.post(target_url, content=payload_bytes, headers=headers)

                    status_code = resp.status_code
                    if resp.is_success:
                        status = "delivered"
                        break
                except Exception as exc:
                    error = str(exc)
                    if attempt == max_attempts:
                        break

            log_entry = {
                "event_id": event.get("id"),
                "event_type": event_type,
                "subscription_id": sub["id"],
                "target_url": target_url,
                "attempts": attempt,
                "status": status,
                "status_code": status_code,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            with self._lock:
                self._delivery_logs.append(log_entry)

            delivery_results.append(log_entry)

        return delivery_results

    def get_delivery_logs(self) -> list[dict[str, Any]]:
        """Return delivery logs in reverse chronological order."""
        with self._lock:
            return list(reversed(self._delivery_logs))


# Singleton instance
webhook_manager = WebhookManager()
