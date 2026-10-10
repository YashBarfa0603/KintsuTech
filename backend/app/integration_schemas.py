
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChangeAnalysisRequest(BaseModel):
    """Validated input for backend change analysis and AI integration."""

    model_config = ConfigDict(extra="forbid")

    service: str = Field(min_length=1, max_length=100)
    baseline: dict[str, Any]
    current: dict[str, Any]

    baseline_status_code: int | None = Field(
        default=None, ge=100, le=599
    )
    current_status_code: int | None = Field(
        default=None, ge=100, le=599
    )


class ChangeAnalysisResponse(BaseModel):
    """Stable response contract for change analysis."""

    service: str
    has_changes: bool
    overall_risk: Literal["none", "low", "medium", "high"]
    change_count: int = Field(ge=0)
    severity_counts: dict[str, int]
    changes: list[dict[str, Any]]
