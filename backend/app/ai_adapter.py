
from collections.abc import Callable
from typing import Any, Protocol

from app.ai_schemas import AIAnalysisResult


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
