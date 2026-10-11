"""
KintsuTech Escalation Scheduler & Background Worker.
Processes due alerts, claims distributed worker locks, manages exponential backoff,
and escalates unacknowledged alerts.
"""

import asyncio
from datetime import datetime, timezone
import logging
import os
from typing import Any

from app.alerts import AlertService, alert_service
from app.storage import StorageRegistry, storage_registry

logger = logging.getLogger("kintsutech.scheduler")


class AlertScheduler:
    """
    Reliable background worker for alert delivery retries and escalation.
    Utilizes database-backed atomic claim leases to prevent duplicate processing
    across concurrent workers.
    """

    def __init__(
        self,
        storage: StorageRegistry | None = None,
        service: AlertService | None = None,
        poll_interval_seconds: float | None = None,
        lock_duration_seconds: int = 60,
    ) -> None:
        self.storage = storage or storage_registry
        self.alert_service = service or alert_service

        # Read configuration from env or fall back to defaults
        if poll_interval_seconds is not None:
            self.poll_interval = float(poll_interval_seconds)
        else:
            self.poll_interval = float(os.environ.get("KINTSUTECH_ALERT_POLL_INTERVAL", "10.0"))

        self.lock_duration = lock_duration_seconds
        self._running = False
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._running

    async def poll_once(self, now_iso: str | None = None) -> dict[str, int]:
        """
        Execute a single polling and escalation cycle.
        Can be invoked directly by tests or background tasks.
        """
        now_dt = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
        current_iso = now_dt.isoformat()

        # 1. Claim due alerts using database-backed lock
        claimed_alerts = self.storage.claim_due_alerts(
            lock_duration_seconds=self.lock_duration,
            limit=20,
            now_iso=current_iso,
        )

        processed_count = 0
        for alert in claimed_alerts:
            # Skip if status is already terminal or acknowledged
            if alert["status"] in ("acknowledged", "resolved", "cancelled"):
                continue

            user_id = alert["user_id"]
            pref = self.storage.get_alert_preferences(user_id)
            max_attempts = pref.get("max_attempts", 3)

            # Check attempt limit
            if alert["attempt_count"] >= max_attempts:
                logger.info(
                    "Alert %s exceeded maximum delivery attempts (%d/%d); skipping retry",
                    alert["id"],
                    alert["attempt_count"],
                    max_attempts,
                )
                continue

            # Deliver through configured channel
            channel = alert.get("delivery_channel", "in_app")
            self.alert_service.deliver_alert(alert, channel=channel, preferences=pref)
            processed_count += 1

        # 2. Escalate overdue alerts
        escalated_alerts = self.storage.escalate_due_alerts(
            max_alerts=50,
            now_iso=current_iso,
        )

        return {
            "claimed": len(claimed_alerts),
            "processed": processed_count,
            "escalated": len(escalated_alerts),
        }

    async def _worker_loop(self) -> None:
        """Internal asynchronous loop polling at configured interval."""
        logger.info("AlertScheduler worker loop started (interval: %.1fs)", self.poll_interval)
        while not self._stop_event.is_set():
            try:
                await self.poll_once()
            except Exception as exc:
                logger.error("Error in AlertScheduler polling cycle: %s", exc, exc_info=True)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                pass

        logger.info("AlertScheduler worker loop stopped")

    def start(self) -> bool:
        """
        Start the background worker if alerts are enabled.
        Guards against duplicate worker loops.
        """
        alerts_enabled = os.environ.get("KINTSUTECH_ALERTS_ENABLED", "true").lower() in ("true", "1", "yes")
        if not alerts_enabled:
            logger.info("Alerts are disabled via KINTSUTECH_ALERTS_ENABLED; scheduler not started")
            return False

        if self._running:
            logger.warning("AlertScheduler is already running; duplicate start call ignored")
            return False

        self._running = True
        self._stop_event.clear()
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._worker_loop())
        except RuntimeError:
            # If no running event loop (e.g. running outside async context), worker starts when loop is available
            pass
        return True

    def stop(self) -> None:
        """Gracefully stop the background worker."""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None


alert_scheduler = AlertScheduler()
