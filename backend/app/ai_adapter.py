from collections.abc import Callable
from pathlib import Path
import sys
from typing import Any, Protocol

from app.ai_schemas import AIAnalysisResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_ENGINE_PATH = PROJECT_ROOT / "ai_engine"

if str(AI_ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(AI_ENGINE_PATH))

from change_workflow import run_change_workflow


class AIEngine(Protocol):
    def analyze_changes(
        self,
        *,
        service: str,
        baseline: dict[str, Any],
        current: dict[str, Any],
        detected_changes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...


class AIAdapter:
    """Normalizes AI-engine results into the backend response schema."""

    def __init__(
        self,
        engine: AIEngine | Callable[..., dict[str, Any]],
    ) -> None:
        self._engine = engine

    def analyze(
        self,
        *,
        service: str,
        baseline: dict[str, Any],
        current: dict[str, Any],
        detected_changes: list[dict[str, Any]],
        behavior_report: dict[str, Any] | None = None,
        text_diff: list[dict[str, str]] | None = None,
        pagination_reports: list[dict[str, Any]] | None = None,
        rate_limit_reports: list[dict[str, Any]] | None = None,
    ) -> AIAnalysisResult:
        # Support the original backend engine interface.
        if hasattr(self._engine, "analyze_changes"):
            raw_result = self._engine.analyze_changes(
                service=service,
                baseline=baseline,
                current=current,
                detected_changes=detected_changes,
            )
        else:
            # The native workflow detects structural changes itself.
            raw_result = self._engine(
                baseline=baseline,
                current=current,
                behavior_report=behavior_report,
                text_diff=text_diff,
                pagination_reports=pagination_reports,
                rate_limit_reports=rate_limit_reports,
            )

        if not isinstance(raw_result, dict):
            raise ValueError("AI workflow must return a dictionary")

        # Preserve compatibility with existing normalized engine results.
        if (
            "change_report" not in raw_result
            and "repair_workflow" not in raw_result
        ):
            return AIAnalysisResult.model_validate(raw_result)

        change_report = raw_result.get("change_report")
        repair_workflow = raw_result.get("repair_workflow")

        if not isinstance(change_report, dict):
            raise ValueError("AI workflow is missing change_report")

        if not isinstance(repair_workflow, dict):
            raise ValueError("AI workflow is missing repair_workflow")

        validation = repair_workflow.get("validation")
        if not isinstance(validation, dict):
            raise ValueError("AI workflow is missing repair validation")

        changes = change_report.get("changes", [])
        if not isinstance(changes, list):
            raise ValueError("change_report.changes must be a list")

        has_changes = change_report.get("has_changes", False)
        if not isinstance(has_changes, bool):
            raise ValueError("change_report.has_changes must be a boolean")

        breaking_count = change_report.get("breaking_change_count", 0)
        if (
            not isinstance(breaking_count, int)
            or isinstance(breaking_count, bool)
            or breaking_count < 0
        ):
            raise ValueError("breaking_change_count must be a non-negative integer")

        # Deterministic risk mapping based on reported evidence.
        if not has_changes:
            risk_level = "none"
        elif breaking_count > 0:
            risk_level = "high"
        elif any(
            not isinstance(change, dict)
            or change.get("kind") != "field_added"
            for change in changes
        ):
            risk_level = "medium"
        else:
            risk_level = "low"

        proposal = repair_workflow.get("proposal")
        if proposal is not None and not isinstance(proposal, dict):
            raise ValueError("repair_workflow.proposal must be a dictionary or null")

        summary = (
            proposal.get("change_summary")
            if isinstance(proposal, dict)
            else None
        )
        if not isinstance(summary, str) or not summary.strip():
            total = change_report.get("total_change_count", len(changes))
            summary = (
                f"{total} API change(s) detected."
                if has_changes
                else "No API changes detected."
            )

        recommendations: list[str] = []

        if isinstance(proposal, dict):
            for key in ("potential_impact", "proposed_repair"):
                value = proposal.get(key)
                if isinstance(value, str) and value.strip():
                    recommendations.append(value)

        errors = validation.get("errors", [])
        if not isinstance(errors, list):
            raise ValueError("repair validation errors must be a list")

        recommendations.extend(
            error
            for error in errors
            if isinstance(error, str) and error.strip()
        )

        return AIAnalysisResult(
            summary=summary,
            risk_level=risk_level,
            recommendations=list(dict.fromkeys(recommendations)),
            # Keep the original proposal and validation status intact.
            repair_proposal={
                "proposal": proposal,
                "validation": validation,
            },
        )


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
