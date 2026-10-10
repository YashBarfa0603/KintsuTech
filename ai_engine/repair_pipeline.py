
from typing import Any

from repair_agent import analyze_api_change
from repair_validator import validate_repair


def run_repair_pipeline(
    baseline: dict[str, Any],
    current: dict[str, Any],
    reviewed_adapter: dict[str, Any] | None = None,
    test_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Run AI analysis followed by deterministic repair validation.

    reviewed_adapter must be independently reviewed.
    The AI proposal cannot confirm its own field semantics.
    """

    # Stage 1: AI analysis with historical incident retrieval.
    proposal = analyze_api_change(
        baseline=baseline,
        current=current,
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

    # Stage 2: Never infer an executable adapter from AI prose.
    if reviewed_adapter is None:
        result["validation"]["errors"] = [
            "An independently reviewed adapter configuration is required.",
            "Confirm field semantics and units using trusted evidence.",
        ]
        return result

    # Stage 3: Require test cases supplied independently of the LLM.
    if test_cases is None:
        result["validation"]["errors"] = [
            "Independent regression test cases are required."
        ]
        return result

    # Stage 4: Deterministic validation.
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
    baseline = {"temperature": 28}
    current = {"temp_c": 28}

    # No reviewed adapter is supplied, so the pipeline must
    # keep the repair pending rather than trusting the LLM.
    output = run_repair_pipeline(
        baseline=baseline,
        current=current,
    )

    import json

    print(json.dumps(output, indent=2))
