
from typing import Any


def get_json_type(value: Any) -> str:
    # return the JSON-compatible type of a Python value
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unknown"


def detect_changes(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare two API JSON responses and report schema changes.

    Removed fields and type changes are potentially breaking.
    Added fields are reported separately and are not automatically
    considered safe in every downstream workflow.
    """
    changes: list[dict[str, str]] = []

    def compare(
        old: Any,
        new: Any,
        path: str,
    ) -> None:
        old_type = get_json_type(old)
        new_type = get_json_type(new)

        if old_type != new_type:
            changes.append({
                "kind": "type_changed",
                "path": path,
                "old_type": old_type,
                "new_type": new_type,
            })
            return

        if isinstance(old, dict) and isinstance(new, dict):
            old_keys = set(old)
            new_keys = set(new)

            for key in sorted(old_keys - new_keys):
                changes.append({
                    "kind": "field_removed",
                    "path": f"{path}.{key}" if path else key,
                    "old_type": get_json_type(old[key]),
                })

            for key in sorted(new_keys - old_keys):
                changes.append({
                    "kind": "field_added",
                    "path": f"{path}.{key}" if path else key,
                    "new_type": get_json_type(new[key]),
                })

            for key in sorted(old_keys & new_keys):
                child_path = f"{path}.{key}" if path else key
                compare(old[key], new[key], child_path)

        elif isinstance(old, list) and old and new:
            # Compare representative items to detect common array
            # element type or object-schema changes.
            compare(old[0], new[0], f"{path}[]")

    compare(baseline, current, "")

    breaking_kinds = {"field_removed", "type_changed"}
    breaking_changes = [
        change for change in changes
        if change["kind"] in breaking_kinds
    ]

    return {
        "has_changes": bool(changes),
        "change_count": len(changes),
        "breaking_change_count": len(breaking_changes),
        "changes": changes,
    }
