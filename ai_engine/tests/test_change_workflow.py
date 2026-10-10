
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from change_workflow import run_change_workflow


def test_changed_api_triggers_repair_pipeline():
    with patch(
        "change_workflow.run_repair_pipeline"
    ) as mock_pipeline:
        mock_pipeline.return_value = {
            "proposal": {"change_summary": "Field changed"},
            "validation": {
                "eligible_for_activation": False,
                "status": "pending_review",
                "tests_passed": 0,
                "tests_failed": 0,
                "errors": ["Independent review required."],
            },
        }

        result = run_change_workflow(
            baseline={"temperature": 28},
            current={"temp_c": 28},
        )

    assert result["change_report"]["has_changes"] is True
    assert result["repair_workflow"]["validation"]["status"] == "pending_review"
    mock_pipeline.assert_called_once()


def test_unchanged_api_skips_repair_pipeline():
    with patch(
        "change_workflow.run_repair_pipeline"
    ) as mock_pipeline:
        result = run_change_workflow(
            baseline={"temperature": 28},
            current={"temperature": 28},
        )

    assert result["change_report"]["has_changes"] is False
    assert result["repair_workflow"]["status"] == "no_changes_detected"
    mock_pipeline.assert_not_called()


def test_detector_report_is_forwarded_to_pipeline():
    with patch(
        "change_workflow.run_repair_pipeline"
    ) as mock_pipeline:
        mock_pipeline.return_value = {
            "proposal": {},
            "validation": {
                "eligible_for_activation": False,
                "status": "pending_review",
                "tests_passed": 0,
                "tests_failed": 0,
                "errors": [],
            },
        }

        result = run_change_workflow(
            baseline={"temperature": 28},
            current={"temp_c": 28},
        )

    assert result["change_report"]["has_changes"] is True

    call_kwargs = mock_pipeline.call_args.kwargs
    assert call_kwargs["change_report"] == result["change_report"]
