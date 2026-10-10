
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.change_detector import detect_changes
from change_report import build_unified_change_report
from repair_pipeline import run_repair_pipeline


def run_change_workflow(
    baseline: dict[str, Any],
    current: dict[str, Any],
    reviewed_adapter: dict[str, Any] | None = None,
    test_cases: list[dict[str, Any]] | None = None,
    behavior_report: dict[str, Any] | None = None,
    text_diff: list[dict[str, str]] | None = None,
    pagination_reports: list[dict[str, Any]] | None = None,
    rate_limit_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Detect changes, build one report, and invoke the gated repair pipeline."""

    # Stage 1: Detect structural changes deterministically.
    schema_report = detect_changes(
        baseline=baseline,
        current=current,
    )

    # Stage 2: Assemble evidence from all available detectors.
    unified_report = build_unified_change_report(
        schema_report=schema_report,
        behavior_report=behavior_report or {"changes": []},
        text_diff=text_diff or [],
        pagination_reports=pagination_reports or [],
        rate_limit_reports=rate_limit_reports or [],
    )

    # Stage 3: Skip repair analysis only when no findings were detected.
    if not unified_report["has_changes"]:
        return {
            "change_report": unified_report,
            "repair_workflow": {
                "status": "no_changes_detected",
                "proposal": None,
                "validation": None,
            },
        }

    # Stage 4: Send the unified report to the existing repair pipeline.
    pipeline_result = run_repair_pipeline(
        baseline=baseline,
        current=current,
        reviewed_adapter=reviewed_adapter,
        test_cases=test_cases,
        change_report=unified_report,
    )

    return {
        "change_report": unified_report,
        "repair_workflow": pipeline_result,
    }


if __name__ == "__main__":
    baseline = {
        "temperature": 28,
        "humidity": 60,
    }

    current = {
        "temp_c": 28,
        "humidity": 60,
    }

    result = run_change_workflow(
        baseline=baseline,
        current=current,
    )

    print(json.dumps(result, indent=2))
