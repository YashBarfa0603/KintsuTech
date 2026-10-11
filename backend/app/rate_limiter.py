from collections import deque
from threading import Lock
import os
import time

from fastapi import HTTPException, Request

from app.security import get_client_ip


class InMemoryRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
    Tracks request timestamps per client IP and bucket.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._buckets: dict[str, deque[float]] = {}

    def is_rate_limited(
        self,
        key: str,
        max_requests: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int]:
        """
        Check if key has exceeded max_requests within window_seconds.
        Returns (is_limited, retry_after_seconds).
        """
        now = time.time()
        with self._lock:
            timestamps = self._buckets.setdefault(key, deque())
            cutoff = now - window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= max_requests:
                earliest = timestamps[0]
                retry_after = max(1, int(window_seconds - (now - earliest)))
                return True, retry_after

            timestamps.append(now)
            return False, 0

    def reset(self) -> None:
        """Reset all rate limit tracking."""
        with self._lock:
            self._buckets.clear()


rate_limiter = InMemoryRateLimiter()


def check_rate_limit(
    request: Request,
    bucket: str = "default",
    max_requests: int = 60,
    window_seconds: int = 60,
) -> None:
    """Enforce sliding-window rate limit on request."""
    enabled = os.environ.get("KINTSUTECH_RATE_LIMIT_ENABLED", "true").lower() in ("true", "1")
    if not enabled:
        return

    client_ip = get_client_ip(request)
    key = f"{bucket}:{client_ip}"
    is_limited, retry_after = rate_limiter.is_rate_limited(
        key,
        max_requests=max_requests,
        window_seconds=window_seconds,
    )
    if is_limited:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {bucket}. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def rate_limit_mutations(request: Request) -> None:
    """Rate limit dependency for mutation and administrative endpoints."""
    limit = int(os.environ.get("RATE_LIMIT_MUTATION_PER_MINUTE", "60"))
    check_rate_limit(request, bucket="mutation", max_requests=limit, window_seconds=60)


def rate_limit_webhooks(request: Request) -> None:
    """Rate limit dependency for webhook ingestion endpoints."""
    limit = int(os.environ.get("RATE_LIMIT_WEBHOOK_INGEST_PER_MINUTE", "120"))
    check_rate_limit(request, bucket="webhook_ingest", max_requests=limit, window_seconds=60)
