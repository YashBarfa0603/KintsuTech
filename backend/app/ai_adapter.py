import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_ENGINE_PATH = PROJECT_ROOT / "ai_engine"

if str(AI_ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(AI_ENGINE_PATH))

from change_workflow import run_change_workflow


def _normalize_detected_changes(
    detected_changes: Any,
) -> list[dict[str, Any]]:
    """Accept a list of changes or a detector result dictionary."""
    if isinstance(detected_changes, dict):
        changes = detected_changes.get("changes", [])
    else:
        changes = detected_changes

    if not isinstance(changes, list):
        return []

    return [
        change for change in changes
        if isinstance(change, dict)
    ]


def _risk_level(changes: list[dict[str, Any]]) -> str:
    """Classify API change risk."""
    severities = {
        str(change.get("severity", "")).lower()
        for change in changes
    }

    kinds = {
        str(change.get("kind", "")).lower()
        for change in changes
    }

    if "high" in severities or kinds.intersection(
        {"field_removed", "type_changed"}
    ):
        return "high"

    if "medium" in severities:
        return "medium"

    if changes:
        return "low"

    return "none"


def analyze_changes(
    service: str,
    baseline: dict[str, Any],
    current: dict[str, Any],
    detected_changes: Any,
) -> dict[str, Any]:
    """Adapt the AI engine workflow to the backend contract."""

    if not isinstance(service, str) or not service.strip():
        raise ValueError("service must be a non-empty string.")

    if not isinstance(baseline, dict) or not isinstance(current, dict):
        raise ValueError(
            "baseline and current must be dictionaries."
        )

    supplied_changes = _normalize_detected_changes(
        detected_changes
    )

    workflow_result = run_change_workflow(
        baseline=baseline,
        current=current,
    )

    change_report = workflow_result.get("change_report", {})
    repair_workflow = workflow_result.get("repair_workflow", {})

    workflow_changes = change_report.get("changes", [])

    if not isinstance(workflow_changes, list):
        workflow_changes = []

    # Deduplicate findings by change kind and path.
    all_changes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for change in [*workflow_changes, *supplied_changes]:
        if not isinstance(change, dict):
            continue

        key = (
            str(change.get("kind", "")),
            str(change.get("path", "")),
        )

        if key not in seen:
            seen.add(key)
            all_changes.append(change)

    risk_level = _risk_level(all_changes)

    if not all_changes:
        summary = (
            f"No API changes detected for service '{service}'."
        )
    else:
        summary = (
            f"Detected {len(all_changes)} API change finding(s) "
            f"for service '{service}'. Overall risk: {risk_level}."
        )

    recommendations: list[str] = []

    for change in all_changes:
        path = change.get("path", "unknown")
        kind = change.get("kind", "")

        if kind == "field_removed":
            recommendation = (
                f"Review consumers of '{path}' and determine whether "
                "a backward-compatible replacement is required."
            )
        elif kind == "type_changed":
            recommendation = (
                f"Review parsing and validation for '{path}', "
                "and test all affected consumers."
            )
        elif kind == "field_added":
            recommendation = (
                f"Check whether consumers can handle the new field "
                f"'{path}'."
            )
        else:
            recommendation = (
                f"Review the finding at '{path}' before changing "
                "consumer behavior."
            )

        if recommendation not in recommendations:
            recommendations.append(recommendation)

    proposal = repair_workflow.get("proposal")
    validation = repair_workflow.get("validation") or {}

    result: dict[str, Any] = {
        "summary": summary,
        "risk_level": risk_level,
        "recommendations": recommendations,
    }

    if isinstance(proposal, dict):
        result["repair_proposal"] = {
            **proposal,
            "validation_status": validation.get(
                "status", "pending_review"
            ),
            "eligible_for_activation": validation.get(
                "eligible_for_activation", False
            ),
        }

    return result