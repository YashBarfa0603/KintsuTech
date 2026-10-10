
import pytest
from pydantic import ValidationError

from app.integration_schemas import (
    ChangeAnalysisRequest,
    ChangeAnalysisResponse,
)


def test_valid_analysis_request():
    request = ChangeAnalysisRequest(
        service="weather",
        baseline={"temperature": 30},
        current={"temperature": "30"},
    )

    assert request.service == "weather"
    assert request.baseline_status_code is None


def test_request_accepts_optional_http_status_codes():
    request = ChangeAnalysisRequest(
        service="weather",
        baseline={},
        current={},
        baseline_status_code=200,
        current_status_code=503,
    )

    assert request.current_status_code == 503


def test_request_rejects_invalid_http_status_code():
    with pytest.raises(ValidationError):
        ChangeAnalysisRequest(
            service="weather",
            baseline={},
            current={},
            baseline_status_code=99,
        )


def test_request_rejects_unexpected_fields():
    with pytest.raises(ValidationError):
        ChangeAnalysisRequest(
            service="weather",
            baseline={},
            current={},
            unexpected="not allowed",
        )


def test_valid_analysis_response():
    response = ChangeAnalysisResponse(
        service="weather",
        has_changes=True,
        overall_risk="high",
        change_count=1,
        severity_counts={"high": 1, "medium": 0, "low": 0},
        changes=[{"kind": "type_changed", "path": "temperature"}],
    )

    assert response.overall_risk == "high"
    assert response.change_count == 1


def test_response_rejects_unknown_risk_level():
    with pytest.raises(ValidationError):
        ChangeAnalysisResponse(
            service="weather",
            has_changes=True,
            overall_risk="critical",
            change_count=0,
            severity_counts={},
            changes=[],
        )
