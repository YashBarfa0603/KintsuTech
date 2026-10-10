
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.change_detector import detect_changes


class APIObserver:
    """Observe API responses and detect changes against a baseline."""

    def __init__(self) -> None:
        self._baselines: dict[str, dict[str, Any]] = {}

    def capture(
        self,
        service: str,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a baseline or compare a new response against it."""
        snapshot = deepcopy(response)

        result_metadata = {
            "service": service,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if service not in self._baselines:
            self._baselines[service] = snapshot

            return {
                **result_metadata,
                "baseline_created": True,
                "has_changes": False,
                "change_count": 0,
                "breaking_change_count": 0,
                "changes": [],
            }

        changes = detect_changes(
            self._baselines[service],
            snapshot,
        )

        return {
            **result_metadata,
            "baseline_created": False,
            **changes,
        }

    def update_baseline(
        self,
        service: str,
        response: dict[str, Any],
    ) -> None:
        """Update a baseline after a change has been verified."""
        self._baselines[service] = deepcopy(response)
