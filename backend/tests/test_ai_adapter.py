from unittest.mock import patch

import pytest

from app.ai_adapter import analyze_changes


def test_adapter_maps_workflow_to_backend_contract():
    workflow_result = {
        "change_report": {
            "has_changes": True,
            "changes": [
                {
                    "source": "structural",
                    "kind": "field_removed",
                    "path": "temperature",
                    "old_type": "integer",
                }
            ],
        },
        "repair_workflow": {
            "proposal": {
                "change_summary": "Temperature field was removed.",
                "evidence": ["Field removal was detected."],
                "potential_impact": "Older clients may fail.",
                "proposed_repair": "Review a compatibility adapter.",
                "confidence": 0.9,
                "requires_validation": True,
            },
            "validation": {
                "status": "pending_review",
                "eligible_for_activation": False,
            },
        },
    }

    with patch(
        "app.ai_adapter.run_change_workflow",
        return_value=workflow_result,
    ):
        result = analyze_changes(
            service="weather",
            baseline={"temperature": 30},
            current={"temp_c": 30},
            detected_changes={
                "changes": [
                    {
                        "kind": "field_removed",
                        "path": "temperature",
                        "old_type": "integer",
                    }
                ]
            },
        )

    assert set(result) == {
        "summary",
        "risk_level",
        "recommendations",
        "repair_proposal",
    }
    assert result["risk_level"] == "high"
    assert result["recommendations"]
    assert result["repair_proposal"]["validation_status"] == (
        "pending_review"
    )
    assert result["repair_proposal"]["eligible_for_activation"] is False


def test_adapter_returns_none_risk_when_no_changes():
    with patch(
        "app.ai_adapter.run_change_workflow",
        return_value={
            "change_report": {"has_changes": False, "changes": []},
            "repair_workflow": {
                "status": "no_changes_detected",
                "proposal": None,
                "validation": None,
            },
        },
    ):
        result = analyze_changes(
            service="weather",
            baseline={"temperature": 30},
            current={"temperature": 30},
            detected_changes=[],
        )

    assert result["risk_level"] == "none"
    assert result["recommendations"] == []
    assert "repair_proposal" not in result


def test_adapter_rejects_empty_service():
    with pytest.raises(ValueError, match="service"):
        analyze_changes(
            service="",
            baseline={},
            current={},
            detected_changes=[],
        )
