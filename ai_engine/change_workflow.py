
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.change_detector import detect_changes
from repair_pipeline import run_repair_pipeline


def run_change_workflow(
    baseline: dict[str, Any],
    current: dict[str, Any],
    reviewed_adapter: dict[str, Any] | None = None,
    test_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # Stage 1: Detect changes deterministically.
    change_report = detect_changes(
        baseline=baseline,
        current=current,
    )

    # Stage 2: Skip AI analysis if no changes were detected.
    if not change_report["has_changes"]:
        return {
            "change_report": change_report,
            "repair_workflow": {
                "status": "no_changes_detected",
                "proposal": None,
                "validation": None,
            },
        }

    # Stage 3: Pass the detector's actual report into the AI pipeline.
    pipeline_result = run_repair_pipeline(
        baseline=baseline,
        current=current,
        reviewed_adapter=reviewed_adapter,
        test_cases=test_cases,
        change_report=change_report,
    )

    return {
        "change_report": change_report,
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
