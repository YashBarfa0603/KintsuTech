import os
import re
import secrets
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import hmac
import json
from threading import Lock
import time
from typing import Any, Callable
import uuid

import httpx

from app.security import validate_target_url
from app.storage import storage_registry, StorageRegistry


DEFAULT_WEBHOOK_SECRET = os.environ.get("KINTSUTECH_WEBHOOK_SECRET") or ""


def sanitize_error(error_str: str | None, secret: str | None = None) -> str | None:
    """Sanitize error messages to ensure secrets or headers are never leaked."""
    if not error_str:
        return None
    sanitized = str(error_str)
    if secret and secret in sanitized:
        sanitized = sanitized.replace(secret, "[REDACTED]")
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED]", sanitized)
    sanitized = re.sub(r"X-API-Key:\s*[^\s,]+", "X-API-Key: [REDACTED]", sanitized)
    sanitized = re.sub(r"X-KintsuTech-Signature:\s*[^\s,]+", "X-KintsuTech-Signature: [REDACTED]", sanitized)
    return sanitized[:255]


class WebhookManager:
    """
    Manages incoming webhook signature verification, deduplication,
    outgoing event subscriptions, SSRF validation, and reliable delivery with retries.
    Backed by SQLite storage via StorageRegistry.
    """

    def __init__(
        self,
        secret: str | None = None,
        storage: StorageRegistry | None = None,
    ) -> None:
        if secret:
            self.secret = secret
        else:
            env_secret = os.environ.get("KINTSUTECH_WEBHOOK_SECRET")
            self.secret = env_secret if env_secret else secrets.token_hex(32)
        self.storage = storage or storage_registry
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="kintsu_webhook")

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

        effective_secret = secret or self.secret
        if not effective_secret:
            return False

        key = effective_secret.encode("utf-8")
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
        """Check and record event_id for idempotency using persistent storage."""
        return self.storage.is_duplicate_webhook_event(event_id)

    def subscribe(
        self,
        *,
        target_url: str,
        events: list[str],
        secret: str | None = None,
        description: str = "",
        dns_resolver: Callable[[str, int], list[tuple[Any, ...]]] | None = None,
    ) -> dict[str, Any]:
        """Register an outgoing webhook destination after strict SSRF validation."""
        validate_target_url(target_url, dns_resolver=dns_resolver)

        sub_secret = secret or self.secret or secrets.token_hex(32)
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        sub = {
            "id": sub_id,
            "target_url": target_url,
            "events": events,
            "secret": sub_secret,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.storage.create_webhook_subscription(sub)
        sanitized_sub = dict(sub)
        sanitized_sub.pop("secret", None)
        sanitized_sub["secret_configured"] = bool(sub_secret)
        return sanitized_sub

    def list_subscriptions(self) -> list[dict[str, Any]]:
        """List active webhook subscriptions with secrets redacted."""
        return self.storage.list_webhook_subscriptions(include_secret=False)

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
        effective_secret = secret or self.secret
        if not effective_secret:
            raise ValueError("Webhook secret is required to sign payload.")
        key = effective_secret.encode("utf-8")
        digest = hmac.new(key, payload_bytes, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def dispatch_event(
        self,
        event: dict[str, Any],
        *,
        client: httpx.Client | None = None,
        max_attempts: int = 3,
        dns_resolver: Callable[[str, int], list[tuple[Any, ...]]] | None = None,
        backoff_base: float = 0.2,
    ) -> list[dict[str, Any]]:
        """
        Send event to all matching subscribers with HMAC signature and retries.
        Validates target URL immediately before dispatch to mitigate DNS rebinding.
        Enforces follow_redirects=False to prevent redirect-based SSRF bypass.
        Persists each delivery record to SQLite storage.
        """
        event_id = event.get("id")
        if event_id and self.storage.is_duplicate_webhook_event(f"dispatch_{event_id}"):
            return []

        event_type = event.get("type", "")
        payload_bytes = json.dumps(event).encode("utf-8")

        matched_subs = []
        all_subs = self.storage.list_webhook_subscriptions(include_secret=True)
        for sub in all_subs:
            sub_events = sub.get("events", [])
            if "*" in sub_events or event_type in sub_events:
                matched_subs.append(sub)

        delivery_results = []
        timeout_config = httpx.Timeout(connect=2.0, read=3.0, write=3.0, pool=5.0)

        for sub in matched_subs:
            target_url = sub["target_url"]
            sub_secret = sub.get("secret", self.secret)

            # Re-validate destination URL before dispatch to prevent DNS rebinding
            try:
                validate_target_url(target_url, dns_resolver=dns_resolver)
            except ValueError as val_err:
                log_entry = {
                    "delivery_id": f"del_{uuid.uuid4().hex[:12]}",
                    "event_id": event.get("id"),
                    "event_type": event_type,
                    "subscription_id": sub["id"],
                    "target_url": target_url,
                    "attempts": 0,
                    "status": "failed",
                    "status_code": None,
                    "error": sanitize_error(f"SSRF blocked: {val_err}", sub_secret),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self.storage.record_webhook_delivery(log_entry)
                delivery_results.append(log_entry)
                continue

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
            actual_attempts = 0

            bounded_attempts = max(1, min(max_attempts, 5))
            for attempt in range(1, bounded_attempts + 1):
                actual_attempts = attempt
                try:
                    if client:
                        resp = client.post(target_url, content=payload_bytes, headers=headers)
                    else:
                        with httpx.Client(timeout=timeout_config, follow_redirects=False) as default_client:
                            resp = default_client.post(target_url, content=payload_bytes, headers=headers)

                    status_code = resp.status_code
                    if resp.is_success:
                        status = "delivered"
                        error = None
                        break
                    else:
                        error = f"HTTP {resp.status_code}"
                except Exception as exc:
                    error = str(exc)

                # Bounded backoff delay between retry attempts
                if attempt < bounded_attempts and backoff_base > 0:
                    time.sleep(min(backoff_base * (2 ** (attempt - 1)), 2.0))

            log_entry = {
                "delivery_id": f"del_{uuid.uuid4().hex[:12]}",
                "event_id": event.get("id"),
                "event_type": event_type,
                "subscription_id": sub["id"],
                "target_url": target_url,
                "attempts": actual_attempts,
                "status": status,
                "status_code": status_code,
                "error": sanitize_error(error, sub_secret),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self.storage.record_webhook_delivery(log_entry)
            delivery_results.append(log_entry)

        return delivery_results

    def dispatch_event_background(
        self,
        event: dict[str, Any],
        *,
        client: httpx.Client | None = None,
        max_attempts: int = 3,
        dns_resolver: Callable[[str, int], list[tuple[Any, ...]]] | None = None,
        backoff_base: float = 0.2,
    ) -> Future:
        """
        Asynchronously dispatch event to subscribers in a background thread pool.
        Does not block the calling HTTP request.
        """
        return self._executor.submit(
            self.dispatch_event,
            event,
            client=client,
            max_attempts=max_attempts,
            dns_resolver=dns_resolver,
            backoff_base=backoff_base,
        )

    def get_delivery_logs(self) -> list[dict[str, Any]]:
        """Return delivery logs in reverse chronological order from SQLite."""
        return self.storage.list_webhook_deliveries(limit=100)

    def shutdown(self, wait: bool = False) -> None:
        """Shutdown background thread pool executor."""
        self._executor.shutdown(wait=wait)


# Singleton instance
webhook_manager = WebhookManager()
