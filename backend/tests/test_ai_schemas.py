
import pytest
from pydantic import ValidationError

from app.ai_schemas import AIAnalysisResult


def test_valid_ai_analysis_result():
    result = AIAnalysisResult(
        summary="Temperature field changed type.",
        risk_level="high",
        recommendations=["Review API consumers."],
    )

    assert result.risk_level == "high"
    assert result.repair_proposal is None


def test_ai_analysis_result_accepts_repair_proposal():
    result = AIAnalysisResult(
        summary="A compatible field mapping may help.",
        risk_level="medium",
        repair_proposal={"action": "copy_field"},
    )

    assert result.repair_proposal == {"action": "copy_field"}


def test_ai_analysis_result_rejects_unknown_risk():
    with pytest.raises(ValidationError):
        AIAnalysisResult(
            summary="Potential change.",
            risk_level="critical",
        )


def test_ai_analysis_result_rejects_extra_fields():
    with pytest.raises(ValidationError):
        AIAnalysisResult(
            summary="Potential change.",
            risk_level="high",
            unexpected="not allowed",
        )


def test_ai_analysis_result_rejects_empty_summary():
    with pytest.raises(ValidationError):
        AIAnalysisResult(summary="", risk_level="low")
