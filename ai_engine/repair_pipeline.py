
from typing import Any

from repair_agent import analyze_api_change
from repair_validator import validate_repair


def run_repair_pipeline(
    baseline: dict[str, Any],
    current: dict[str, Any],
    reviewed_adapter: dict[str, Any] | None = None,
    test_cases: list[dict[str, Any]] | None = None,
    change_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run AI reasoning followed by deterministic repair validation.

    The model cannot independently confirm field semantics.
    """

    # Stage 1: Analyze the API change using detector findings and RAG.
    proposal = analyze_api_change(
        baseline=baseline,
        current=current,
        change_report=change_report,
    )

    result = {
        "proposal": proposal.model_dump(),
        "validation": {
            "eligible_for_activation": False,
            "status": "pending_review",
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": [],
        },
    }

    # Stage 2: Require independent review.
    if reviewed_adapter is None:
        result["validation"]["errors"] = [
            "An independently reviewed adapter configuration is required.",
            "Confirm field semantics and units using trusted evidence.",
        ]
        return result

    # Stage 3: Require independently supplied test cases.
    if test_cases is None:
        result["validation"]["errors"] = [
            "Independent regression test cases are required."
        ]
        return result

    # Stage 4: Validate the restricted adapter operation.
    validation = validate_repair(
        proposal=reviewed_adapter,
        test_cases=test_cases,
    )

    result["validation"] = {
        **validation,
        "status": (
            "eligible_for_activation"
            if validation["eligible_for_activation"]
            else "rejected"
        ),
    }

    return result


if __name__ == "__main__":
    import json

    baseline = {"temperature": 28}
    current = {"temp_c": 28}

    output = run_repair_pipeline(
        baseline=baseline,
        current=current,
        change_report={
            "has_changes": True,
            "changes": [
                {"type": "field_removed", "path": "temperature"},
                {"type": "field_added", "path": "temp_c"},
            ],
        },
    )

    print(json.dumps(output, indent=2))
