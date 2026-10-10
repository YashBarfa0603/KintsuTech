
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any


class APIHealthMonitor:
    """Track API call outcomes, response times, and recent incidents."""

    def __init__(self, max_incidents: int = 100):
        if max_incidents < 1:
            raise ValueError("max_incidents must be at least 1.")

        self._lock = Lock()
        self._max_incidents = max_incidents
        self._services: dict[str, dict[str, Any]] = {}
        self._incidents: deque[dict[str, Any]] = deque(
            maxlen=max_incidents
        )

    def record_success(
        self,
        service: str,
        response_time_ms: float,
    ) -> None:
        """Record a successful API call."""
        self._validate_input(service, response_time_ms)

        with self._lock:
            stats = self._get_or_create_service(service)
            stats["total_calls"] += 1
            stats["successful_calls"] += 1
            stats["response_times_ms"].append(response_time_ms)

    def record_failure(
        self,
        service: str,
        response_time_ms: float,
        error: str,
    ) -> None:
        """Record a failed API call and create an incident."""
        self._validate_input(service, response_time_ms)

        if not isinstance(error, str) or not error.strip():
            raise ValueError("error must be a non-empty string.")

        with self._lock:
            stats = self._get_or_create_service(service)
            stats["total_calls"] += 1
            stats["failed_calls"] += 1
            stats["response_times_ms"].append(response_time_ms)

            self._incidents.append(
                {
                    "service": service,
                    "error": error,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

    def get_service_health(self, service: str) -> dict[str, Any]:
        """Return health statistics for one service."""
        with self._lock:
            stats = self._services.get(service)

            if stats is None:
                return {
                    "service": service,
                    "status": "unknown",
                    "total_calls": 0,
                    "successful_calls": 0,
                    "failed_calls": 0,
                    "failure_rate_percent": 0.0,
                    "average_response_time_ms": 0.0,
                }

            total = stats["total_calls"]
            failures = stats["failed_calls"]
            times = stats["response_times_ms"]

            failure_rate = failures / total * 100 if total else 0.0
            average_time = sum(times) / len(times) if times else 0.0

            return {
                "service": service,
                "status": "degraded" if failures else "healthy",
                "total_calls": total,
                "successful_calls": stats["successful_calls"],
                "failed_calls": failures,
                "failure_rate_percent": round(failure_rate, 2),
                "average_response_time_ms": round(average_time, 2),
            }

    def get_recent_incidents(self) -> list[dict[str, Any]]:
        """Return recent incidents, newest first."""
        with self._lock:
            return list(reversed(self._incidents))

    def _get_or_create_service(self, service: str) -> dict[str, Any]:
        if service not in self._services:
            self._services[service] = {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "response_times_ms": [],
            }

        return self._services[service]

    @staticmethod
    def _validate_input(service: str, response_time_ms: float) -> None:
        if not isinstance(service, str) or not service.strip():
            raise ValueError("service must be a non-empty string.")

        if (
            isinstance(response_time_ms, bool)
            or not isinstance(response_time_ms, (int, float))
            or response_time_ms < 0
        ):
            raise ValueError(
                "response_time_ms must be a non-negative number."
            )
