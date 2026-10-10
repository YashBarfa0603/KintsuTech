
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repair_pipeline import run_repair_pipeline
from schemas import RepairProposal


def fake_proposal():
    return RepairProposal(
        change_summary="A field was removed and another was added.",
        evidence=["temperature disappeared; temp_c appeared."],
        potential_impact="Existing clients may fail.",
        proposed_repair="Confirm field semantics before mapping.",
        confidence=0.5,
    )


@patch("repair_pipeline.analyze_api_change")
def test_pipeline_requires_independent_review(mock_analyze):
    mock_analyze.return_value = fake_proposal()

    result = run_repair_pipeline(
        baseline={"temperature": 28},
        current={"temp_c": 28},
    )

    assert result["validation"]["status"] == "pending_review"
    assert result["validation"]["eligible_for_activation"] is False
    mock_analyze.assert_called_once()


@patch("repair_pipeline.analyze_api_change")
def test_unconfirmed_adapter_is_rejected(mock_analyze):
    mock_analyze.return_value = fake_proposal()

    adapter = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": False,
    }

    result = run_repair_pipeline(
        baseline={"temperature": 28},
        current={"temp_c": 28},
        reviewed_adapter=adapter,
        test_cases=[
            {
                "input": {"temp_c": 28},
                "expected": {
                    "temp_c": 28,
                    "temperature": 28,
                },
            }
        ],
    )

    assert result["validation"]["status"] == "rejected"
    assert result["validation"]["eligible_for_activation"] is False


@patch("repair_pipeline.analyze_api_change")
def test_passing_reviewed_adapter_is_eligible(mock_analyze):
    mock_analyze.return_value = fake_proposal()

    adapter = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }

    result = run_repair_pipeline(
        baseline={"temperature": 28},
        current={"temp_c": 28},
        reviewed_adapter=adapter,
        test_cases=[
            {
                "input": {"temp_c": 28},
                "expected": {
                    "temp_c": 28,
                    "temperature": 28,
                },
            }
        ],
    )

    assert result["validation"]["status"] == "eligible_for_activation"
    assert result["validation"]["eligible_for_activation"] is True
