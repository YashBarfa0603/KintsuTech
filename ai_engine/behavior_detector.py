from typing import Any


BEHAVIOR_FIELDS = {"status", "success", "error"}


def detect_behavior_changes(
    baseline: dict[str, Any],
    current: dict[str, Any],
    baseline_status_code: int | None = None,
    current_status_code: int | None = None,
) -> dict[str, Any]:
    """Detect changes in API status indicators and HTTP status codes."""

    changes: list[dict[str, Any]] = []

    # Check HTTP status codes when both are supplied.
    if (
        baseline_status_code is not None
        and current_status_code is not None
        and baseline_status_code != current_status_code
    ):
        changes.append({
            "kind": "http_status_changed",
            "path": "$http_status",
            "old_value": baseline_status_code,
            "new_value": current_status_code,
        })

    def compare(
        old: Any,
        new: Any,
        path: str = "",
    ) -> None:
        if isinstance(old, dict) and isinstance(new, dict):
            all_keys = sorted(set(old) | set(new))

            for key in all_keys:
                child_path = f"{path}.{key}" if path else key

                if key not in old:
                    if key.lower() in BEHAVIOR_FIELDS:
                        changes.append({
                            "kind": "behavior_indicator_added",
                            "path": child_path,
                            "new_value": new[key],
                        })
                    continue

                if key not in new:
                    if key.lower() in BEHAVIOR_FIELDS:
                        changes.append({
                            "kind": "behavior_indicator_removed",
                            "path": child_path,
                            "old_value": old[key],
                        })
                    continue

                if isinstance(old[key], dict) and isinstance(new[key], dict):
                    compare(old[key], new[key], child_path)
                elif (
                    key.lower() in BEHAVIOR_FIELDS
                    and old[key] != new[key]
                ):
                    changes.append({
                        "kind": "behavior_value_changed",
                        "path": child_path,
                        "old_value": old[key],
                        "new_value": new[key],
                    })

        # Lists and ordinary data values are deliberately not
        # interpreted as behavior changes in this first version.

    compare(baseline, current)

    return {
        "has_behavior_changes": bool(changes),
        "behavior_change_count": len(changes),
        "changes": changes,
    }
