from typing import Any


def _classify_change(change: dict[str, Any]) -> dict[str, Any]:
    """Add severity and recommendations to a detected change."""
    kind = change.get("kind")
    path = change.get("path", "unknown")

    if kind == "field_added":
        severity = "low"
        explanation = f"Field '{path}' was added."
        recommendation = (
            "Check whether consumers can handle the new field. "
            "Update documentation if needed."
        )

    elif kind == "field_removed":
        severity = "high"
        explanation = f"Field '{path}' was removed."
        recommendation = (
            "Check consumers that use this field and update "
            "their code or restore the field."
        )

    elif kind == "type_changed":
        severity = "high"
        old_type = change.get("old_type", "unknown")
        new_type = change.get("new_type", "unknown")
        explanation = (
            f"Field '{path}' changed type from "
            f"{old_type} to {new_type}."
        )
        recommendation = (
            "Review parsing and validation logic, then test "
            "all consumers that read this field."
        )

    else:
        severity = "medium"
        explanation = f"Unrecognized change detected at '{path}'."
        recommendation = (
            "Review the change manually before updating consumers."
        )

    return {
        **change,
        "severity": severity,
        "explanation": explanation,
        "recommendation": recommendation,
    }


def _build_analysis(
    changes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the existing backend analysis response."""
    analyzed_changes = [
        _classify_change(change)
        for change in changes
    ]

    severity_order = {"high": 0, "medium": 1, "low": 2}
    analyzed_changes.sort(
        key=lambda item: severity_order[item["severity"]]
    )

    counts = {
        "high": sum(
            item["severity"] == "high"
            for item in analyzed_changes
        ),
        "medium": sum(
            item["severity"] == "medium"
            for item in analyzed_changes
        ),
        "low": sum(
            item["severity"] == "low"
            for item in analyzed_changes
        ),
    }

    if counts["high"]:
        overall_risk = "high"
    elif counts["medium"]:
        overall_risk = "medium"
    elif counts["low"]:
        overall_risk = "low"
    else:
        overall_risk = "none"

    return {
        "has_changes": bool(analyzed_changes),
        "overall_risk": overall_risk,
        "change_count": len(analyzed_changes),
        "severity_counts": counts,
        "changes": analyzed_changes,
    }


def analyze_changes(
    detection_result: dict[str, Any],
) -> dict[str, Any]:
    """Preserve the existing one-argument backend contract."""
    return _build_analysis(
        detection_result.get("changes", [])
    )